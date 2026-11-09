"""One explicitly approved AIAPI draft, then independent review and private admission."""

import argparse
import asyncio
import getpass
import ipaddress
import json
import signal
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.core.provider_target import TargetPolicy, approve_target
from app.services import head_course_aiapi_content as batch
from app.services import head_course_reuse as reuse
from app.services.free_course_planning import load_inputs
from app.services.free_course_snapshots import (
    SnapshotError,
    SnapshotRepository,
    canonical,
)
from app.services.free_scene_availability import commit_outline
from scripts import head_course_fixed_aiapi as prior
from scripts.head_course_fixed_continuation import cipher
from scripts.head_course_goal import ROOT, database, raw_io, read

VAULT = Path.home() / ".local/share/edumind" / batch.BATCH
READ_TIMEOUT = 300
OTHER_TIMEOUT = 90


def package_digest():
    path = batch.PACKAGE / "manifest.json"
    raw = path.read_bytes()
    manifest = json.loads(raw)
    for name, expected in manifest["package_sha256"].items():
        if batch.sha((batch.PACKAGE / name).read_bytes()) != expected:
            raise SnapshotError("HEAD_AIAPI_PACKAGE_CHANGED")
    for name, expected in manifest["repo_relative_source_sha256"].items():
        if batch.sha((ROOT / name).read_bytes()) != expected:
            raise SnapshotError("HEAD_AIAPI_PACKAGE_CHANGED")
    for name, expected in manifest["runtime_sha256"].items():
        if batch.sha((ROOT / name).read_bytes()) != expected:
            raise SnapshotError("HEAD_AIAPI_ENTRY_CHANGED")
    batch.source()
    return batch.sha(raw)


def save(vault, name, value):
    raw_io.exclusive(vault / name, canonical(value))


def now():
    return datetime.now(timezone.utc)


def remaining(context, minimum=0):
    window = context["execution_window"]
    current = now()
    seconds = (datetime.fromisoformat(window["expires_at"]) - current).total_seconds()
    if (
        current < datetime.fromisoformat(window["starts_at"])
        or seconds <= 0
        or seconds < minimum
    ):
        raise SnapshotError("HEAD_AIAPI_DEADLINE")
    return seconds


def ids(context):
    return tuple(UUID(context[key]) for key in ("owner", "course_id", "operation_id"))


async def operation_context(db, owner, cid, oid):
    batch.require_database(db)
    repo = SnapshotRepository(db, owner)
    op = await repo._operation(cid, oid)
    window = batch.operation_window(op)
    if (
        op.state not in ("queued", "running")
        or op.cancel_requested_at
        or op.deadline_at <= await repo._now()
    ):
        raise SnapshotError("HEAD_AIAPI_OPERATION_STOPPED")
    inputs = await load_inputs(db, owner, cid, oid)
    old, _ = batch.source()
    outline = await batch.outline(repo, cid)
    plan = await repo.get_plan(cid, UUID(outline["plan_id"]))
    batch.bound_payload(inputs, plan["candidate"], old)
    return dict(
        owner=str(owner),
        course_id=str(cid),
        operation_id=str(oid),
        execution_window=window,
        planning_inputs=inputs,
    )


async def prepare_operation(db, owner):
    batch.require_database(db)
    old, _ = batch.source()
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(
        old["original_goal"],
        key=batch.BATCH,
        config=dict(
            prompt_version=batch.materials.FIXED_VERSION, policy_version=batch.BATCH
        ),
        operation_window_seconds=batch.WINDOW_SECONDS,
    )
    cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
    batch.bound_payload(await load_inputs(db, owner, cid, oid), old["plan"], old)
    if (await repo.get_course(cid))["head_version"] is None:
        fence = await repo.acquire_write_fence(cid, oid)
        stored = await repo.store_plan(
            cid,
            fence,
            expected_head=None,
            key=batch.BATCH + ":plan",
            candidate=old["plan"],
        )
        await commit_outline(
            db, owner, cid, fence, plan_id=UUID(stored["plan_id"]), key=batch.BATCH
        )
        op = await repo._fence(cid, fence)
        op.lease_token = op.lease_expires_at = None
    return await operation_context(db, owner, cid, oid)


def approval_fields(vault):
    context = read(vault / "context.json")
    return dict(
        batch=batch.BATCH,
        response_rule=batch.VERSION,
        endpoint=batch.ENDPOINT,
        max_http_requests=1,
        package_sha256=package_digest(),
        entry_sha256=batch.sha(Path(__file__).read_bytes()),
        request_sha256=batch.REQUEST_SHA,
        context_sha256=batch.sha((vault / "context.json").read_bytes()),
        execution_window=context["execution_window"],
    )


def approved(vault):
    if vault.is_symlink() or not vault.is_dir() or vault.stat().st_mode & 0o077:
        raise SnapshotError("HEAD_AIAPI_VAULT")
    path = vault / "approval.json"
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
        raise SnapshotError("HEAD_AIAPI_APPROVAL_REQUIRED")
    raw = path.read_bytes()
    expected = dict(
        **approval_fields(vault), explicit_user_authorization=True, accept_batch_C2=True
    )
    if canonical(batch.wire.strict_json(raw)) != canonical(expected):
        raise SnapshotError("HEAD_AIAPI_APPROVAL_BINDING")
    return batch.sha(raw)


def current_context(vault, approval_sha, *, minimum=0):
    if approved(vault) != approval_sha:
        raise SnapshotError("HEAD_AIAPI_APPROVAL_CHANGED")
    context = read(vault / "context.json")
    if (
        asyncio.run(database(lambda db: operation_context(db, *ids(context))))
        != context
    ):
        raise SnapshotError("HEAD_AIAPI_OPERATION_BINDING")
    remaining(context, minimum)
    return context


@contextmanager
def absolute_deadline(context):
    def expire(signum, frame):
        raise SnapshotError("HEAD_AIAPI_DEADLINE")

    seconds = remaining(context)
    previous = signal.signal(signal.SIGALRM, expire)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def receive(vault, target, raw_request, key, context, transport):
    ip = ipaddress.ip_address(target.connect_ip)
    host = f"[{ip}]" if ip.version == 6 else str(ip)
    with (
        absolute_deadline(context),
        httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(OTHER_TIMEOUT, read=READ_TIMEOUT),
            trust_env=False,
            follow_redirects=False,
        ) as client,
        client.stream(
            "POST",
            f"https://{host}:443/v1/responses",
            content=raw_request,
            extensions={"sni_hostname": target.hostname},
            headers={
                "Host": target.hostname,
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
            },
        ) as response,
    ):
        headers = dict(
            http_status=response.status_code,
            encoding=response.headers.get("content-encoding", "identity"),
            media_type=response.headers.get("content-type", "")
            .split(";", 1)[0]
            .strip()
            .lower(),
        )
        save(vault, "draft.headers.json", headers)
        raw = raw_io.collect(response, vault / "draft.raw.enc", cipher(vault))
    if raw_io.decrypt(vault / "draft.raw.enc", cipher(vault)) != raw:
        raise SnapshotError("HEAD_AIAPI_EVIDENCE_INCOMPLETE")
    save(
        vault,
        "draft.body.json",
        dict(
            **headers, raw_sha256=batch.sha(raw), raw_bytes=len(raw), body_complete=True
        ),
    )
    if key.encode() in raw:
        raise SnapshotError("HEAD_AIAPI_CREDENTIAL_ECHO")
    check_receipt(headers)
    return raw


def check_receipt(headers):
    if headers["http_status"] != 200:
        raise SnapshotError(f"HEAD_AIAPI_HTTP_{headers['http_status']}")
    if (
        headers["encoding"] != "identity"
        or headers["media_type"] == "text/event-stream"
    ):
        raise SnapshotError("HEAD_AIAPI_ENCODING")


def send(vault, *, transport=None, key=None):
    offline = isinstance(transport, httpx.MockTransport)
    if not offline and (
        transport is not None
        or vault != VAULT
        or key is not None
        or not sys.stdin.isatty()
    ):
        raise SnapshotError("HEAD_AIAPI_FOREGROUND_REQUIRED")
    approval_sha = approved(vault)
    if any(
        (vault / name).exists() for name in ("ACTIVE", "STOP", "draft.attempt.json")
    ):
        raise SnapshotError("HEAD_AIAPI_ALREADY_STOPPED")
    lock = vault / "ACTIVE"
    raw_io.exclusive(lock, b"one foreground draft; unresolved means stop\n")
    try:
        context = current_context(vault, approval_sha, minimum=READ_TIMEOUT)
        old, request = batch.source()
        payload = batch.bound_payload(context["planning_inputs"], old["plan"], old)
        target = approve_target(
            batch.ENDPOINT,
            policy=TargetPolicy(),
            **({"resolver": lambda host, port: ["93.184.216.34"]} if offline else {}),
        )
        if key is None:
            key = getpass.getpass("Current AIAPI API key (not saved): ")
        if not key or not key.isascii() or any(char.isspace() for char in key):
            raise SnapshotError("HEAD_AIAPI_KEY_INVALID")
        if (vault / "STOP").exists():
            raise SnapshotError("HEAD_AIAPI_ALREADY_STOPPED")
        raw_request = (batch.PACKAGE / "request.json").read_bytes()
        if batch.sha(raw_request) != batch.REQUEST_SHA or len(raw_request) > 131072:
            raise SnapshotError("HEAD_AIAPI_REQUEST_BINDING")
        current_context(vault, approval_sha, minimum=READ_TIMEOUT)
        evidence_kind = "offline_fixture" if offline else "actual_provider_response"
        raw_io.exclusive(vault / "draft.request.json", raw_request)
        save(
            vault,
            "draft.attempt.json",
            dict(
                approval_sha256=approval_sha,
                request_sha256=batch.REQUEST_SHA,
                endpoint=batch.ENDPOINT,
                evidence_kind=evidence_kind,
                started_at=now().isoformat(),
            ),
        )
        if (vault / "STOP").exists():
            raise SnapshotError("HEAD_AIAPI_ALREADY_STOPPED")
        remaining(context, READ_TIMEOUT)
        raw = receive(vault, target, raw_request, key, context, transport)
        current_context(vault, approval_sha)
        rec = batch.record(payload, request, raw, evidence_kind)
        if key in canonical(rec["candidate"]["raw_output"]).decode():
            raise SnapshotError("HEAD_AIAPI_CREDENTIAL_ECHO")
        save(vault, "draft.record.json", rec)
        save(vault, "STOP", {"reason": "awaiting_independent_review"})
    except BaseException as error:
        failure = prior.error_record(error)
        failure["body_complete"] = (vault / "draft.body.json").is_file()
        failure["response_bytes_received"] = None
        raw_path = vault / "draft.raw.enc"
        if raw_path.is_file() and not failure["body_complete"]:
            try:
                partial = raw_io.decrypt(raw_path, cipher(vault))
            except (OSError, ValueError, InvalidToken):
                pass
            else:
                failure.update(
                    response_bytes_received=len(partial),
                    partial_sha256=batch.sha(partial),
                )
        save(vault, "failure.json", failure)
        if not (vault / "STOP").exists():
            save(vault, "STOP", {"reason": "failure_or_unknown"})
        raise
    lock.unlink()
    return rec


def review_input(vault):
    if (
        (vault / "ACTIVE").exists()
        or (vault / "failure.json").exists()
        or read(vault / "STOP") != {"reason": "awaiting_independent_review"}
    ):
        raise SnapshotError("HEAD_AIAPI_DRAFT_NOT_REVIEWABLE")
    approval_sha = approved(vault)
    context = read(vault / "context.json")
    rec = read(vault / "draft.record.json")
    attempt = read(vault / "draft.attempt.json")
    started = datetime.fromisoformat(attempt["started_at"])
    window = context["execution_window"]
    raw = raw_io.decrypt(vault / "draft.raw.enc", cipher(vault))
    headers = read(vault / "draft.headers.json")
    check_receipt(headers)
    if (
        read(vault / "draft.body.json")
        != dict(
            **headers, raw_sha256=batch.sha(raw), raw_bytes=len(raw), body_complete=True
        )
        or attempt["approval_sha256"] != approval_sha
        or attempt["request_sha256"] != batch.REQUEST_SHA
        or attempt["endpoint"] != batch.ENDPOINT
        or started < datetime.fromisoformat(window["starts_at"])
        or (datetime.fromisoformat(window["expires_at"]) - started).total_seconds()
        < READ_TIMEOUT
        or batch.sha((vault / "draft.request.json").read_bytes()) != batch.REQUEST_SHA
    ):
        raise SnapshotError("HEAD_AIAPI_ATTEMPT_BINDING")
    old, request = batch.source()
    payload = batch.bound_payload(context["planning_inputs"], old["plan"], old)
    if rec != batch.record(payload, request, raw, attempt["evidence_kind"]):
        raise SnapshotError("HEAD_AIAPI_RECORD_BINDING")
    return dict(context=context, records=[rec]), batch.review_binding(context, rec)


def publish(vault, review_file):
    if (vault / "publication.failure.json").exists():
        raise SnapshotError("HEAD_AIAPI_PUBLICATION_STOPPED")
    chain, _ = review_input(vault)
    remaining(chain["context"])
    review = batch.wire.strict_json(review_file.read_bytes())
    raw_io.exclusive(vault / "final-review.json", canonical(review))
    try:
        result = asyncio.run(
            database(
                lambda db: reuse.publish(
                    db, *ids(chain["context"]), dict(**chain, final_review=review)
                )
            )
        )
    except BaseException as error:
        save(vault, "publication.failure.json", prior.error_record(error))
        raise
    save(vault, "published.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("inspect")
    prepare = actions.add_parser("prepare")
    prepare.add_argument("--owner", type=UUID, required=True)
    actions.add_parser("approval-fields")
    actions.add_parser("send")
    actions.add_parser("review-input")
    publication = actions.add_parser("publish")
    publication.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "inspect":
        result = dict(
            batch=batch.BATCH,
            package_sha256=package_digest(),
            request_sha256=batch.REQUEST_SHA,
            entry_sha256=batch.sha(Path(__file__).read_bytes()),
        )
    elif args.action == "prepare":
        package_digest()
        VAULT.mkdir(mode=0o700)
        save_key = VAULT / "raw.key"
        raw_io.exclusive(save_key, Fernet.generate_key())
        context = asyncio.run(database(lambda db: prepare_operation(db, args.owner)))
        save(VAULT, "context.json", context)
        result = approval_fields(VAULT)
    elif args.action == "approval-fields":
        result = approval_fields(VAULT)
    elif args.action == "send":
        record = send(VAULT)
        result = dict(candidate_digest=record["candidate"]["candidate_digest"])
    elif args.action == "review-input":
        chain, binding = review_input(VAULT)
        save(
            VAULT,
            "review-input.json",
            dict(
                aiapi_binding=binding,
                candidate=chain["records"][0]["candidate"],
            ),
        )
        result = dict(path=str(VAULT / "review-input.json"), aiapi_binding=binding)
    else:
        result = publish(VAULT, args.review)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (SnapshotError, OSError, ValueError, httpx.HTTPError) as error:
        sys.exit(prior.error_record(error)["code"])
