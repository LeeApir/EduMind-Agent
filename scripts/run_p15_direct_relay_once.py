"""One direct synthetic generation explicitly requested by user; never count or retry."""

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.p15_candidate_compatibility import evidence, parse, redact_check  # noqa: E402
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, Refused, digest  # noqa: E402
from run_p15_candidate_compatibility import bounded_resolver  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-direct-relay-once-d01"
OUTPUT = Path("/tmp/edumind-p15-direct-relay-once-d01")
BATCH = "p15-direct-relay-once-d01"
LIMITS = Limits(1, 4096, 16, 10000, 40)
URL = "https://www.cbbb.fun/v1"
BODY_SHA = "cc45e19ba242760b756bca579ee80e45c6dd93e35c351ed6128a8bef7e459422"


def load(base=BASE, root=ROOT):
    raw = (base / "manifest.json").read_bytes()
    manifest = parse(raw)
    assert manifest["batch_id"] == BATCH and manifest["limits"] == asdict(LIMITS)
    for name, sha in manifest["sha256"].items():
        path = root / name
        assert path.resolve().is_relative_to(root.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    assert hashlib.sha256((base / "request.json").read_bytes()).hexdigest() == BODY_SHA
    return hashlib.sha256(raw).hexdigest()


def gate(base=BASE, root=ROOT):
    package = load(base, root)
    grant = parse((base / "execution-authorization.json").read_bytes())
    assert grant["package_sha256"] == package and grant["batch_id"] == BATCH
    assert grant["limits"] == asdict(LIMITS) and grant["scope"] == "PHASE-1.5-T038"
    assert (
        grant["direct_generation_only"] is True
        and grant["skip_count_explicitly_requested"] is True
    )
    assert grant["new_manifest_independently_human_reviewed"] is False
    assert (
        grant["evidence_ref"]
        and grant["authorization_basis"]
        == "latest_explicit_single_direct_generation_instruction"
    )
    return package, grant


def credential(root=ROOT):
    wanted = {
        "EDUMIND_PROVIDER_BASE_URL",
        "EDUMIND_PROVIDER_MODEL",
        "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT",
        "EDUMIND_PROVIDER_API_KEY",
    }
    values = {}
    for line in (root / ".env").read_text().splitlines():
        name, sep, value = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        if not sep or name not in wanted:
            continue
        if name in values:
            raise Refused("AMBIGUOUS_CONFIG")
        value = value.strip()
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise Refused("INVALID_QUOTING")
            value = value[1:-1]
        values[name] = value
    if (
        values.get("EDUMIND_PROVIDER_BASE_URL") != URL
        or values.get("EDUMIND_PROVIDER_MODEL") != "gpt-6-luna"
        or values.get("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT")
        != "responses_json_schema"
    ):
        raise Refused("IDENTITY_CHANGED")
    key = values.get("EDUMIND_PROVIDER_API_KEY", "")
    if len(key) < 16 or not key.isascii() or any(ch.isspace() for ch in key):
        raise Refused("KEY_MISSING")
    return key


def observe(body, reply):
    assert isinstance(reply, dict)
    ins = reply.get("instructions")
    systems = [m for m in body["input"] if m["role"] == "system"]
    joined = "\n\n".join(m["content"] for m in systems)
    usage = reply.get("usage") if isinstance(reply.get("usage"), dict) else {}
    numbers = {
        k: usage.get(k) if type(usage.get(k)) is int else None
        for k in ("input_tokens", "output_tokens", "total_tokens")
    }
    valid_numbers = all(type(v) is int and v >= 0 for v in numbers.values())
    checks = dict(
        completed=reply.get("object") == "response"
        and reply.get("status") == "completed"
        and reply.get("error") is None,
        model_matches=reply.get("model") == "gpt-6-luna",
        storage_and_tier=reply.get("store") is False
        and reply.get("service_tier") == "default",
        instructions_unchanged=ins is None or ins == systems or ins == joined,
        output_cap_echo_matches=reply.get("max_output_tokens") == 16,
        usage_arithmetic=valid_numbers
        and numbers["input_tokens"] + numbers["output_tokens"]
        == numbers["total_tokens"],
        reported_output_within_cap=valid_numbers and numbers["output_tokens"] <= 16,
        reported_input_within_local_hold=valid_numbers
        and numbers["input_tokens"] <= 4096,
        schema_echo_matches=reply.get("text", {}).get("format")
        == body["text"]["format"],
    )
    text = []
    valid_output = isinstance(reply.get("output"), list)
    for item in reply.get("output", []) if valid_output else []:
        if not isinstance(item, dict):
            valid_output = False
            continue
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            valid_output = False
            continue
        for block in item.get("content", []):
            if (
                not isinstance(block, dict)
                or block.get("type") != "output_text"
                or not isinstance(block.get("text"), str)
            ):
                valid_output = False
            else:
                text.append(block["text"])
    try:
        value = parse("".join(text))
        Draft202012Validator(body["text"]["format"]["schema"]).validate(value)
        checks["fixed_ok_and_full_schema"] = valid_output and value == {"result": "OK"}
    except Exception:
        checks["fixed_ok_and_full_schema"] = False
    return dict(
        checks=checks,
        provider_reported_usage=numbers,
        count_equivalence_tested=False,
        count_call_sent=False,
        instructions_chars=len(ins) if isinstance(ins, str) else None,
        unrequested_suffix_chars=len(ins) - len(joined)
        if isinstance(ins, str) and ins.startswith(joined)
        else None,
        unrequested_suffix_sha256=hashlib.sha256(
            ins[len(joined) :].encode()
        ).hexdigest()
        if isinstance(ins, str) and ins.startswith(joined)
        else None,
    )


async def run(base, output, package, grant, key, target_factory, transport_factory):
    raw = (base / "request.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == BODY_SHA
    redact_check(raw, key)
    output.mkdir(mode=0o700, exist_ok=False)
    ledger = Ledger(output / "ledger.sqlite")
    summary = dict(
        batch_id=BATCH,
        package_sha256=package,
        http_dispatch_markers=0,
        model_dispatch_markers=0,
        count_equivalence_tested=False,
        count_call_sent=False,
        course_generation_authorized=False,
        T038_completed=False,
        actual_invoice=None,
        actual_currency=None,
        local_planning_cap_usd="0.01",
        outcome="blocked_unknown",
        observation=None,
    )
    try:
        ledger.start(
            BATCH, package, LIMITS, grant, pinned_approval_sha256=digest(grant)
        )
        ledger.reserve(
            BATCH,
            package,
            "direct-model",
            input_max=4096,
            output_max=16,
            fee_max=10000,
            seconds=40,
        )
        try:
            async with asyncio.timeout(39):
                target = await asyncio.to_thread(target_factory)
                assert target.url == URL
                from app.services.deepseek_responses import _wire_target

                url, host = _wire_target(target)
                async with httpx.AsyncClient(
                    transport=transport_factory(),
                    trust_env=False,
                    follow_redirects=False,
                    timeout=29,
                ) as client:
                    ledger.mark_sent(BATCH, package, "direct-model")
                    evidence(
                        output / "dispatch.json",
                        dict(
                            method="POST",
                            public_url=URL + "/responses",
                            body_sha256=BODY_SHA,
                        ),
                    )
                    summary.update(http_dispatch_markers=1, model_dispatch_markers=1)
                    request = client.build_request(
                        "POST",
                        url,
                        content=raw,
                        headers={
                            "Host": host,
                            "Authorization": "Bearer " + key,
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                    )
                    request.extensions["sni_hostname"] = target.hostname
                    async with asyncio.timeout(29):
                        response = await client.send(
                            request, stream=True, follow_redirects=False
                        )
                        try:
                            summary["http_status"] = response.status_code
                            evidence(
                                output / "status.json",
                                dict(http_status=response.status_code),
                            )
                            data = bytearray()
                            async for chunk in response.aiter_bytes(chunk_size=65536):
                                data.extend(chunk)
                                if len(data) > 2097152:
                                    raise Refused("READ_LIMIT")
                        finally:
                            await response.aclose()
                raw_response = bytes(data)
                redact_check(raw_response, key)
                evidence(output / "response.json", raw_response)
                if summary["http_status"] == 200:
                    summary["observation"] = observe(parse(raw), parse(raw_response))
                    summary["outcome"] = (
                        "direct_response_observed"
                        if all(summary["observation"]["checks"].values())
                        else "response_contract_issues_observed"
                    )
                else:
                    summary["outcome"] = "http_failure"
                with ledger.transaction():
                    ledger.guard(BATCH, package)
        except BaseException:
            summary["outcome"] = "transport_or_evidence_unknown"
        ledger.halt(
            BATCH,
            "human_pause"
            if summary["outcome"] == "direct_response_observed"
            else "provider_contract_failure",
        )
        # No independent count or invoice proof: retain the whole local hold even with HTTP200.
        ledger.settle(BATCH, "direct-model", outcome="unknown")
        summary["local_accounting"] = ledger.usage(BATCH)
        ledger.record(BATCH, "direct_observation", summary)
        evidence(output / "summary.json", summary)
        return summary
    finally:
        ledger.close()


def execute():
    package, grant = gate()
    if OUTPUT.exists():
        raise Refused("NO_RESTART")
    key = credential()
    from app.core.provider_target import ProviderTargetGuard, TargetPolicy

    return asyncio.run(
        run(
            BASE,
            OUTPUT,
            package,
            grant,
            key,
            lambda: ProviderTargetGuard(
                URL, TargetPolicy(), resolver=bounded_resolver
            ).approve_base(),
            lambda: httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.check:
            print("DIRECT_PACKAGE_VERIFIED_NO_CALLS " + load())
        else:
            result = execute()
            print(
                json.dumps(
                    {
                        "outcome": result["outcome"],
                        "http_status": result.get("http_status"),
                    }
                )
            )
            if result["outcome"] != "direct_response_observed":
                raise SystemExit(2)
    except Exception:
        raise SystemExit("REFUSED_OR_STOPPED; no retry") from None
