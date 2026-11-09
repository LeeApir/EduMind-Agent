"""T111 continuation using the reviewed archived plan and one foreground request per stage."""

import argparse
import getpass
import hashlib
import ipaddress
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
import httpx  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402

from app.core.provider_target import TargetPolicy, approve_target  # noqa: E402
from app.services import head_course_materials as materials  # noqa: E402
from app.services import head_course_reuse as reuse  # noqa: E402
from app.services.free_course_snapshots import SnapshotError, canonical, digest  # noqa: E402
from scripts import head_course_goal as original  # noqa: E402

VAULT = Path.home() / ".local/share/edumind/head-fixed-continuation-r02"
ARCHIVE = ROOT / "docs/acceptance/phase-1.5-head-fixed-live-r01"
APPROVAL = ROOT / "docs/acceptance/phase-1.5-head-fixed-continuation-r02/approval.json"
BATCH = "head-fixed-continuation-r02"
STAGES = ("draft", "followup")
SOURCE_PACKAGE = "41d2eeb692834b1eacc15327d2f5f0e75e15e9773d8990e6ce48921268bb6de3"
SOURCE_PLAN = "0997615bbdb35b96df95904d4d4d1730d08a94a2f797091c04a48e484a6452ee"
read = original.read
raw_io = original.raw_io


def sha(data):
    return hashlib.sha256(data).hexdigest()


def cipher(vault):
    key = vault / "raw.key"
    if key.is_symlink() or not key.is_file() or key.stat().st_mode & 0o077:
        raise SnapshotError("CONTINUATION_RAW_KEY_UNSAFE")
    return Fernet(key.read_bytes())


def source_payload():
    original.PACKAGE = original.FIXED_PACKAGE
    vault = original.FIXED_VAULT
    if original.package_digest() != SOURCE_PACKAGE:
        raise SnapshotError("CONTINUATION_SOURCE_PACKAGE")
    if (
        not (vault / "STOP").is_file()
        or (vault / "ACTIVE").exists()
        or sorted(p.name for p in vault.glob("*.attempt.json")) != ["plan.attempt.json"]
        or read(vault / "plan.attempt.json")["evidence_kind"]
        != "actual_provider_response"
    ):
        raise SnapshotError("CONTINUATION_SOURCE_STOP")
    plan = original.verify_saved(vault, "plan", cipher(vault))["plan"]
    review = read(ARCHIVE / "plan-review.json")
    payload = materials.content_payload(
        read(vault / "context.json")["planning_inputs"], plan
    )
    if (
        digest("head-plan", plan=plan) != SOURCE_PLAN
        or review["plan_digest"] != SOURCE_PLAN
        or review["verdict"] != "pass"
        or not review["independent_evaluator"]
        or review["planning_basis_binding"] != payload["planning_basis"]["binding"]
        or read(ARCHIVE / "plan.body.json") != read(vault / "plan.body.json")
        or read(vault / "plan.binding.json")["payload"] != payload
    ):
        raise SnapshotError("CONTINUATION_SOURCE_REVIEW")
    return payload


def gate(vault, payload, stage):
    if stage not in STAGES or (
        vault.is_symlink() or not vault.is_dir() or vault.stat().st_mode & 0o077
    ):
        raise SnapshotError("CONTINUATION_VAULT")
    if (vault / "STOP").exists():
        raise SnapshotError("CONTINUATION_STOPPED")
    approved = read(APPROVAL)
    if (
        approved["batch"] != BATCH
        or approved["explicit_user_authorization"] is not True
        or approved["additional_http_limit"] != 2
        or approved["historical_http"] != 1
        or approved["r01_package_sha256"] != SOURCE_PACKAGE
        or approved["r01_plan_digest"] != SOURCE_PLAN
        or approved["runner_sha256"] != sha(Path(__file__).read_bytes())
        or approved["plan_review_sha256"]
        != sha((ARCHIVE / "plan-review.json").read_bytes())
        or approved["draft_request_sha256"] != sha(canonical(materials.body(payload)))
    ):
        raise SnapshotError("CONTINUATION_APPROVAL")
    attempts = sorted(p.name for p in vault.glob("*.attempt.json"))
    if attempts != ([] if stage == "draft" else ["draft.attempt.json"]):
        raise SnapshotError("CONTINUATION_STAGE_ORDER_OR_BUDGET")
    return sha(APPROVAL.read_bytes())


def rebuild(vault, stage, payload, request, *, parent=None, review=None):
    raw = raw_io.decrypt(vault / f"{stage}.raw.enc", cipher(vault))
    if read(vault / f"{stage}.body.json") != dict(
        http_status=200, raw_bytes=len(raw), raw_sha256=sha(raw), body_complete=True
    ):
        raise SnapshotError("CONTINUATION_BODY_BINDING")
    attempt = read(vault / f"{stage}.attempt.json")
    if (
        attempt["batch"] != BATCH
        or attempt["stage"] != stage
        or attempt["approval_sha256"] != sha(APPROVAL.read_bytes())
        or attempt["request_sha256"] != sha(canonical(request))
        or (vault / f"{stage}.request.json").read_bytes() != canonical(request)
    ):
        raise SnapshotError("CONTINUATION_ATTEMPT_BINDING")
    return reuse.record(
        payload,
        request,
        raw,
        raw_io,
        evidence_kind=attempt["evidence_kind"],
        parent=parent,
        review=review,
    )


def stage_request(vault, stage, payload):
    first = materials.body(payload)
    if stage == "draft":
        return "draft", first, None, None
    draft = rebuild(vault, "draft", payload, first)
    if draft != read(vault / "draft.record.json"):
        raise SnapshotError("CONTINUATION_DRAFT_CHANGED")
    review = read(vault / "draft-review.json")
    if review["verdict"] == "needs_revision":
        parent = draft["candidate"]
        return "reviewed_revision", reuse.revision_body(parent, review), parent, review
    # A real independent pass supports an independent repeat of the same initial request.
    reuse.validate_final([draft], review, payload, raw_io)
    return "independent_repeat", first, None, review


def send(vault, stage, *, transport=None, key=None):
    payload = source_payload()
    approval_sha = gate(vault, payload, stage)
    lock = vault / "ACTIVE"
    raw_io.exclusive(lock, b"single foreground request; unresolved means stop\n")
    try:
        encryption = cipher(vault)
        kind, request, parent, review = stage_request(vault, stage, payload)
        body = canonical(request)
        if len(body) > 131072:
            raise SnapshotError("CONTINUATION_REQUEST_SIZE")
        target = approve_target(
            "https://api.deepseek.com/responses",
            policy=TargetPolicy(),
            **(
                {"resolver": lambda h, p: ["93.184.216.34"]}
                if transport is not None
                else {}
            ),
        )
        ip = ipaddress.ip_address(target.connect_ip)
        host = f"[{ip}]" if ip.version == 6 else str(ip)
        if key is None:
            if not sys.stdin.isatty():
                raise SnapshotError("CONTINUATION_TTY_REQUIRED")
            key = getpass.getpass("Current DeepSeek API key (not saved): ")
        if not key or "\n" in key or "\r" in key:
            raise SnapshotError("CONTINUATION_KEY_INVALID")
        if gate(vault, payload, stage) != approval_sha or stage_request(
            vault, stage, payload
        ) != (kind, request, parent, review):
            raise SnapshotError("CONTINUATION_INPUT_CHANGED")
        raw_io.exclusive(vault / f"{stage}.request.json", body)
        raw_io.exclusive(
            vault / f"{stage}.attempt.json",
            canonical(
                dict(
                    batch=BATCH,
                    stage=stage,
                    kind=kind,
                    request_sha256=sha(body),
                    approval_sha256=approval_sha,
                    source_plan_digest=SOURCE_PLAN,
                    review_sha256=None if review is None else sha(canonical(review)),
                    evidence_kind="offline_fixture"
                    if transport is not None
                    else "actual_provider_response",
                    started_at=datetime.now(timezone.utc).isoformat(),
                    state="attempted_unknown",
                )
            ),
        )
        with httpx.Client(
            transport=transport, timeout=90, trust_env=False, follow_redirects=False
        ) as client:
            with client.stream(
                "POST",
                f"https://{host}:443/responses",
                content=body,
                extensions={"sni_hostname": target.hostname},
                headers={
                    "Host": target.hostname,
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
            ) as response:
                status = response.status_code
                encoding = response.headers.get("content-encoding", "identity")
                raw = raw_io.collect(response, vault / f"{stage}.raw.enc", encryption)
        raw_io.exclusive(
            vault / f"{stage}.body.json",
            canonical(
                dict(
                    http_status=status,
                    raw_bytes=len(raw),
                    raw_sha256=sha(raw),
                    body_complete=True,
                )
            ),
        )
        if (vault / "STOP").exists() or sha(APPROVAL.read_bytes()) != approval_sha:
            raise SnapshotError("CONTINUATION_STOP_OR_APPROVAL_CHANGED")
        if (
            status != 200
            or encoding != "identity"
            or key in raw.decode(errors="replace")
        ):
            raise SnapshotError("CONTINUATION_HTTP_ENCODING_OR_CREDENTIAL_ECHO")
        record = rebuild(
            vault,
            stage,
            payload,
            request,
            parent=parent,
            review=review if parent else None,
        )
        raw_io.exclusive(vault / f"{stage}.record.json", canonical(record))
        if stage == "followup":
            raw_io.exclusive(vault / "STOP", b"two continuation attempts complete\n")
        lock.unlink()
        return record
    except BaseException as error:
        raw_io.exclusive(
            vault / f"{stage}.failure.json",
            canonical(
                dict(
                    stage=stage,
                    error_type=type(error).__name__,
                    code=getattr(
                        error,
                        "code",
                        str(error)
                        if isinstance(error, raw_io.wire.PilotError)
                        else None,
                    ),
                )
            ),
        )
        if not (vault / "STOP").exists():
            raw_io.exclusive(vault / "STOP", b"failed or unknown; preserve originals\n")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("inspect", *STAGES))
    args = parser.parse_args()
    if args.stage == "inspect":
        payload = source_payload()
        print(
            canonical(
                dict(
                    batch=BATCH,
                    plan_digest=SOURCE_PLAN,
                    draft_request_sha256=sha(canonical(materials.body(payload))),
                )
            ).decode()
        )
        return
    if any(
        k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL", "DEEPSEEK", "OPENAI"))
        for k in os.environ
    ):
        parser.error("Use a clean terminal environment")
    try:
        send(VAULT, args.stage)
    except BaseException:
        print(
            "STOPPED or refused. Preserve originals and report this status.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print("Step complete. Preserve originals.")


if __name__ == "__main__":
    main()
