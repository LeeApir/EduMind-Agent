"""One new T111 AIAPI draft request with a 300-second read timeout."""

import argparse
import getpass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
import httpx  # noqa: E402

from app.core.provider_target import TargetPolicy, approve_target  # noqa: E402
from app.services.free_course_snapshots import SnapshotError, canonical  # noqa: E402
from app.services import head_course_reuse as reuse  # noqa: E402
from scripts import head_course_fixed_aiapi as prior  # noqa: E402

BATCH = "head-fixed-aiapi-r05"
ARCHIVE = ROOT / "docs/acceptance/phase-1.5-head-fixed-aiapi-r05"
VAULT = prior.VAULT.with_name(BATCH)
STAGE = "draft"
READ_TIMEOUT = 300
OTHER_TIMEOUT = 90
read, save, sha, raw_io = prior.read, prior.save, prior.sha, prior.raw_io


def source():
    _, payload, requests = prior.inputs()
    request = requests["draft1"]
    body = canonical(request)
    manifest_path = prior.ARCHIVE / "originals-manifest.json"
    manifest = read(manifest_path)
    files = manifest["files"]
    if (
        manifest["vault"] != str(prior.VAULT)
        or not {"STOP", "ACTIVE", "draft1.attempt.json", "failure.json"} <= files.keys()
        or any(
            sha((prior.VAULT / name).read_bytes()) != expected
            for name, expected in files.items()
        )
        or read(prior.ARCHIVE / "approval.json") != prior.approval(requests)
        or read(prior.VAULT / "failure.json")
        != dict(code="ReadTimeout", error_type="ReadTimeout", stage="draft1")
        or any(prior.VAULT.glob("draft*.headers.json"))
        or (prior.ARCHIVE / "draft1.request.json").read_bytes() != body
        or (prior.VAULT / "draft1.request.json").read_bytes() != body
        or read(prior.VAULT / "draft1.attempt.json")["request_sha256"] != sha(body)
    ):
        raise SnapshotError("AIAPI_DRAFT_SOURCE_CHANGED")
    approval = dict(
        batch=BATCH,
        user_authorization="继续",
        request_sha256=sha(body),
        maximum_requests=1,
        prior_allowance_inherited=0,
        endpoint=prior.ENDPOINT,
        model=prior.MODEL,
        read_timeout_seconds=READ_TIMEOUT,
        other_timeout_seconds=OTHER_TIMEOUT,
        runner_sha256=sha(Path(__file__).read_bytes()),
        source_originals_manifest_sha256=sha(manifest_path.read_bytes()),
        source_batch=prior.BATCH,
        source_plan_digest=prior.prior.SOURCE_PLAN,
    )
    return payload, request, approval


def evaluate(payload, request, raw):
    _, observation = prior.message(request, raw)
    try:
        result, _, recovery, strict_failure = reuse.observe(
            request, raw, prior.ADAPTER, allow_recovery=True, source_batch=BATCH
        )
        return dict(
            status="awaiting_independent_review",
            observation=observation,
            candidate=reuse.candidate(payload, result.value, recovery=recovery),
            strict_failure=strict_failure,
        )
    except (SnapshotError, prior.wire.PilotError, ValueError) as error:
        return dict(
            status="rejected_local",
            observation=observation,
            **prior.error_record(error),
        )


def run(vault, *, transport=None):
    payload, request, expected = source()
    manifest = ARCHIVE / "approval.json"
    approved = sha(manifest.read_bytes())
    if (
        read(manifest) != expected
        or vault.is_symlink()
        or not vault.is_dir()
        or vault.stat().st_mode & 0o077
        or sorted(path.name for path in vault.iterdir()) != ["raw.key"]
        or not sys.stdin.isatty()
    ):
        raise SnapshotError("AIAPI_DRAFT_APPROVAL_VAULT_OR_TTY")
    lock = vault / "ACTIVE"
    raw_io.exclusive(lock, b"one foreground request; unresolved means stop\n")
    try:
        encryption = prior.prior.cipher(vault)
        options = (
            {"resolver": lambda host, port: ["93.184.216.34"]} if transport else {}
        )
        target = approve_target(prior.ENDPOINT, policy=TargetPolicy(), **options)
        key = getpass.getpass("Current AIAPI API key (not saved): ")
        if len(key) < 12 or not key.isascii() or any(char.isspace() for char in key):
            raise SnapshotError("AIAPI_KEY_INVALID")
        if (vault / "STOP").exists() or sha(manifest.read_bytes()) != approved:
            raise SnapshotError("AIAPI_DRAFT_STOP_OR_APPROVAL_CHANGED")
        timeout = httpx.Timeout(OTHER_TIMEOUT, read=READ_TIMEOUT)
        kind = "offline_fixture" if transport else "actual_provider_attempt"
        with httpx.Client(
            transport=transport,
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            raw = prior.dispatch(
                client, target, vault, STAGE, request, key, encryption, approved, kind
            )
        result = evaluate(payload, request, raw)
        if key in canonical(result).decode():
            raise SnapshotError("AIAPI_CREDENTIAL_ECHO")
        save(vault / "draft.result.json", result)
        save(
            vault / "STOP",
            dict(reason="sole_response_completed", stopped_at=prior.timestamp()),
        )
        lock.unlink()
        return result["status"]
    except BaseException as error:
        save(vault / "failure.json", prior.error_record(error))
        if not (vault / "STOP").exists():
            save(
                vault / "STOP",
                dict(reason="failure_or_unknown", stopped_at=prior.timestamp()),
            )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "run"))
    if parser.parse_args().action == "inspect":
        print(canonical(source()[2]).decode())
        return
    try:
        status = run(VAULT)
    except BaseException:
        print("STOPPED or refused. Preserve originals.", file=sys.stderr)
        raise SystemExit(2) from None
    print(f"Draft: HTTP 200, {status}. Batch stopped. Preserve originals.")


if __name__ == "__main__":
    main()
