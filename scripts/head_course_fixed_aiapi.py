"""Replay the three archived T111 samples against the user-selected AIAPI route."""

import argparse
from datetime import datetime, timezone
import getpass
import ipaddress
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
import httpx  # noqa: E402

from app.core.provider_target import TargetPolicy, approve_target  # noqa: E402
from app.services.free_course_snapshots import SnapshotError, canonical, digest  # noqa: E402
from app.services.provider_gateway import StructuredResult, TokenUsage  # noqa: E402
from scripts import head_course_fixed_continuation as prior  # noqa: E402
from scripts import head_course_fixed_repeat as repeat  # noqa: E402

BATCH = "head-fixed-aiapi-r04"
ENDPOINT = "https://aiapi.world/v1/responses"
MODEL = "gpt-6.1-sol"
STAGES = ("plan", "draft1", "draft2")
VAULT = Path.home() / ".local/share/edumind" / BATCH
ARCHIVE = ROOT / "docs/acceptance/phase-1.5-head-fixed-aiapi-r04"
read, raw_io, sha = prior.read, prior.raw_io, prior.sha
wire = raw_io.wire


def inputs():
    payload, draft, draft_bytes = repeat.inputs()
    archived_plan = prior.ARCHIVE / "plan.request.json"
    context = read(prior.ARCHIVE / "context.json")["planning_inputs"]
    plan = prior.original.planning_body(context)
    if (
        archived_plan.read_bytes() != canonical(plan)
        or (prior.original.FIXED_VAULT / "plan.request.json").read_bytes()
        != canonical(plan)
        or (
            ROOT / "docs/acceptance/phase-1.5-head-fixed-repeat-r03/repeat.request.json"
        ).read_bytes()
        != draft_bytes
    ):
        raise SnapshotError("AIAPI_SOURCE_REQUEST_CHANGED")
    return (
        context,
        payload,
        {
            stage: dict(plan if stage == "plan" else draft, model=MODEL)
            for stage in STAGES
        },
    )


def approval(requests):
    return dict(
        batch=BATCH,
        user_authorization="使用 https://aiapi.world/v1 的 gpt-6.1-sol 重测这三个",
        endpoint=ENDPOINT,
        model=MODEL,
        maximum_requests=3,
        stages=list(STAGES),
        runner_sha256=sha(Path(__file__).read_bytes()),
        source_package_sha256=prior.SOURCE_PACKAGE,
        draft_source_plan_digest=prior.SOURCE_PLAN,
        request_sha256={
            stage: sha(canonical(request)) for stage, request in requests.items()
        },
        wall_clock_deadline=None,
        per_request_timeout_seconds=90,
        prior_allowance_inherited=0,
    )


def message(request, raw):
    """Check the relay envelope before classifying model content failures."""
    reply = wire.strict_json(raw)
    if (
        type(reply) is not dict
        or reply.get("model") != MODEL
        or reply.get("status") != "completed"
        or reply.get("error") is not None
        or reply.get("incomplete_details") is not None
        or reply.get("store") is not False
        or reply.get("tools") not in (None, [])
    ):
        raise SnapshotError("AIAPI_ENVELOPE")
    usage = reply.get("usage")
    counts = (
        [usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")]
        if type(usage) is dict
        else []
    )
    if (
        len(counts) != 3
        or any(type(n) is not int or n < 0 for n in counts)
        or counts[0] + counts[1] != counts[2]
        or counts[0] > 139264
        or counts[1] > request["max_output_tokens"]
    ):
        raise SnapshotError("AIAPI_USAGE")
    details = usage.get("output_tokens_details")
    if details is not None and (
        type(details) is not dict
        or type(details.get("reasoning_tokens")) is not int
        or not 0 <= details["reasoning_tokens"] <= counts[1]
    ):
        raise SnapshotError("AIAPI_REASONING_USAGE")
    expected = request["input"][0]["content"]
    echo = reply.get("instructions")
    if echo not in (None, expected, expected + wire.SUFFIX):
        raise SnapshotError("AIAPI_INSTRUCTIONS")
    reasoning = reply.get("reasoning")
    if reasoning is not None and type(reasoning) is not dict:
        raise SnapshotError("AIAPI_REASONING_ECHO")
    output = reply.get("output")
    if type(output) is not list or len(output) != 1 or type(output[0]) is not dict:
        raise SnapshotError("AIAPI_OUTPUT")
    item = output[0]
    if (
        item.get("type") != "message"
        or item.get("role") != "assistant"
        or item.get("status") != "completed"
        or set(item) - {"type", "role", "status", "id", "content", "phase"}
        or ("phase" in item and item["phase"] != "final_answer")
    ):
        raise SnapshotError("AIAPI_MESSAGE")
    content = item.get("content")
    if type(content) is not list or len(content) != 1 or type(content[0]) is not dict:
        raise SnapshotError("AIAPI_CONTENT")
    part = content[0]
    if (
        part.get("type") != "output_text"
        or set(part) - {"type", "text", "annotations", "logprobs"}
        or part.get("annotations") not in (None, [])
        or part.get("logprobs") not in (None, [])
        or type(part.get("text")) is not str
        or not part["text"].strip()
    ):
        raise SnapshotError("AIAPI_CONTENT")
    effort = reasoning.get("effort") if reasoning else None
    return part["text"], dict(
        reported_model=MODEL,
        instruction_echo="missing"
        if echo is None
        else "exact"
        if echo == expected
        else "known_suffix",
        reasoning_echo=effort,
        reasoning_tokens=details["reasoning_tokens"] if details else None,
        max_output_tokens_echo=reply.get("max_output_tokens"),
        temperature_echo=reply.get("temperature"),
        message_phase=item.get("phase"),
        input_tokens=counts[0],
        output_tokens=counts[1],
    )


def observe_generation(request, raw):
    value, observation = message(request, raw)
    value = wire.strict_json(value)
    wire.check_schema(value, request["text"]["format"]["schema"])
    return StructuredResult(
        value,
        MODEL,
        TokenUsage(observation["input_tokens"], observation["output_tokens"]),
    ), observation


ADAPTER = SimpleNamespace(wire=wire, observe_generation=observe_generation)


def evaluate(stage, context, payload, request, raw):
    _, observation = message(request, raw)
    try:
        result, _, recovery, strict_failure = prior.reuse.observe(
            request, raw, ADAPTER, allow_recovery=stage != "plan", source_batch=BATCH
        )
        if stage == "plan":
            mapping = prior.original.plan_wire.mapping_record(result.value, context)
            plan = prior.original.plan_wire.to_local(result.value, context)["plan"]
            if plan is None:
                raise SnapshotError("HEAD_PLANNING_CLARIFICATION_STOP")
            new_payload = prior.materials.content_payload(context, plan)
            return dict(
                status="awaiting_independent_review",
                observation=observation,
                model_output=result.value,
                plan=plan,
                mapping=mapping,
                plan_digest=digest("head-plan", plan=plan),
                planning_basis_binding=new_payload["planning_basis"]["binding"],
            )
        return dict(
            status="awaiting_independent_review",
            observation=observation,
            candidate=prior.reuse.candidate(payload, result.value, recovery=recovery),
            strict_failure=strict_failure,
        )
    except (SnapshotError, wire.PilotError, ValueError) as error:
        return dict(
            status="rejected_local", observation=observation, **error_record(error)
        )


def error_record(error):
    if isinstance(error, (SnapshotError, wire.PilotError)):
        code = str(error)
    else:
        code = type(error).__name__
    return dict(error_type=type(error).__name__, code=code)


def save(path, value):
    raw_io.exclusive(path, canonical(value))


def timestamp():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def dispatch(client, target, vault, stage, request, key, encryption, approved, kind):
    body = canonical(request)
    raw_io.exclusive(vault / f"{stage}.request.json", body)
    save(
        vault / f"{stage}.attempt.json",
        dict(
            stage=stage,
            started_at=timestamp(),
            endpoint=ENDPOINT,
            model=MODEL,
            approval_sha256=approved,
            request_sha256=sha(body),
            evidence_kind=kind,
        ),
    )
    ip = ipaddress.ip_address(target.connect_ip)
    host = f"[{ip}]" if ip.version == 6 else str(ip)
    with client.stream(
        "POST",
        f"https://{host}:443/v1/responses",
        content=body,
        extensions={"sni_hostname": target.hostname},
        headers={
            "Host": target.hostname,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept-Encoding": "identity",
        },
    ) as response:
        save(vault / f"{stage}.headers.json", dict(http_status=response.status_code))
        encoding = response.headers.get("content-encoding", "identity")
        raw = raw_io.collect(response, vault / f"{stage}.raw.enc", encryption)
    save(
        vault / f"{stage}.body.json",
        dict(
            http_status=response.status_code,
            raw_sha256=sha(raw),
            raw_bytes=len(raw),
            body_complete=True,
        ),
    )
    if (
        key.encode() in raw
        or raw_io.decrypt(vault / f"{stage}.raw.enc", encryption) != raw
    ):
        raise SnapshotError("AIAPI_CREDENTIAL_ECHO_OR_ORIGINAL_MISMATCH")
    if response.status_code != 200:
        raise SnapshotError("AIAPI_HTTP_" + str(response.status_code))
    if encoding != "identity":
        raise SnapshotError("AIAPI_RESPONSE_ENCODING")
    return raw


def run(vault, *, transport=None):
    context, payload, requests = inputs()
    if (
        vault.is_symlink()
        or not vault.is_dir()
        or vault.stat().st_mode & 0o077
        or sorted(p.name for p in vault.iterdir()) != ["raw.key"]
        or not sys.stdin.isatty()
    ):
        raise SnapshotError("AIAPI_VAULT_OR_TTY")
    manifest = ARCHIVE / "approval.json"
    expected = approval(requests)
    approved = sha(manifest.read_bytes())
    if read(manifest) != expected or any(
        (ARCHIVE / f"{slot}.request.json").read_bytes() != canonical(requests[slot])
        for slot in ("plan", "draft1")
    ):
        raise SnapshotError("AIAPI_APPROVAL_CHANGED")
    lock = vault / "ACTIVE"
    raw_io.exclusive(lock, b"single foreground batch; unresolved means stop\n")
    stage = "preflight"
    try:
        encryption = prior.cipher(vault)
        options = (
            {"resolver": lambda host, port: ["93.184.216.34"]} if transport else {}
        )
        target = approve_target(ENDPOINT, policy=TargetPolicy(), **options)
        kind = "offline_fixture" if transport else "actual_provider_attempt"
        key = getpass.getpass("Current AIAPI API key (not saved): ")
        if len(key) < 12 or not key.isascii() or any(c.isspace() for c in key):
            raise SnapshotError("AIAPI_KEY_INVALID")
        with httpx.Client(
            transport=transport, timeout=90, trust_env=False, follow_redirects=False
        ) as client:
            for stage, request in requests.items():
                if (vault / "STOP").exists() or sha(manifest.read_bytes()) != approved:
                    raise SnapshotError("AIAPI_STOP_OR_APPROVAL_CHANGED")
                raw = dispatch(
                    client,
                    target,
                    vault,
                    stage,
                    request,
                    key,
                    encryption,
                    approved,
                    kind,
                )
                result = evaluate(stage, context, payload, request, raw)
                if key in canonical(result).decode():
                    raise SnapshotError("AIAPI_CREDENTIAL_ECHO")
                save(vault / f"{stage}.result.json", result)
                print(f"{stage}: HTTP 200, {result['status']}", flush=True)
        save(
            vault / "STOP",
            dict(reason="three_samples_completed", stopped_at=timestamp()),
        )
        lock.unlink()
    except BaseException as error:
        save(vault / "failure.json", dict(stage=stage, **error_record(error)))
        if not (vault / "STOP").exists():
            save(
                vault / "STOP",
                dict(reason="failure_or_unknown", stopped_at=timestamp()),
            )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "run"))
    args = parser.parse_args()
    if args.action == "inspect":
        print(canonical(approval(inputs()[2])).decode())
        return
    try:
        run(VAULT)
    except BaseException:
        print(
            "STOPPED or refused. Preserve originals and report this status.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print("Three samples complete. Preserve originals.")


if __name__ == "__main__":
    main()
