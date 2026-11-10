"""One approved foreground request for T119; no planning call, retry or fallback."""

import argparse
import asyncio
from datetime import datetime
import getpass
import hashlib
import ipaddress
from pathlib import Path
import sys
import time
from uuid import UUID

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_database_engine
from app.core.provider_target import TargetPolicy, approve_target
from app.services import stack_course_materials as m
from app.services import stack_course_publication as publication
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import head_course_deepseek_wire as direct
from scripts.head_course_goal import ROOT, raw_io

PACKAGE = ROOT / "docs/acceptance/phase-1.5-stack-lifo-t119"
VAULT = Path.home() / ".local/share/edumind" / m.BATCH
SUCCESS_STOP = b"one request consumed; independently reviewed publication only\n"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def failure_code(error):
    if isinstance(error, (raw_io.wire.PilotError, raw_io.IncompleteEvidence)):
        return str(error)
    return getattr(error, "code", None)


def read(path: Path):
    return raw_io.wire.strict_json(path.read_bytes())


def save(vault, name, value):
    raw_io.exclusive(vault / name, canonical(value))


def package_digest() -> str:
    manifest = PACKAGE / "manifest.json"
    if (PACKAGE / "request.json").read_bytes() != canonical(m.request()) or any(
        sha((ROOT / name).read_bytes()) != expected
        for name, expected in read(manifest)["files"].items()
    ):
        raise SnapshotError("STACK_PACKAGE_CHANGED")
    return sha(manifest.read_bytes())


def approval_values():
    return dict(
        manifest_sha256=package_digest(),
        batch=m.BATCH,
        explicit_user_authorization=True,
        accept_T119_scope_and_batch_C2=True,
        max_http_requests=1,
        window_seconds=1800,
    )


def check_approval(approval):
    if canonical(approval) != canonical(approval_values()):
        raise SnapshotError("STACK_EXACT_AUTHORIZATION_REQUIRED")


async def database(action, *, fixture):
    publication.require_database(fixture=fixture)
    engine = create_database_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
            return await action(db)
    finally:
        await engine.dispose()


async def prepare(vault, owner, approval, *, fixture=False):
    check_approval(approval)
    if not fixture and vault != VAULT:
        raise SnapshotError("STACK_VAULT_REQUIRED")
    vault.mkdir(mode=0o700)
    try:
        ctx = await database(
            lambda db: publication.prepare(db, owner, fixture=fixture), fixture=fixture
        )
        raw_io.exclusive(vault / "raw.key", Fernet.generate_key())
        save(vault, "context.json", ctx)
        save(
            vault,
            "approval.bound.json",
            dict(approval=approval, context_sha256=sha(canonical(ctx))),
        )
        return ctx
    except BaseException:
        raw_io.exclusive(vault / "STOP", b"preparation failed; no send\n")
        raise


def local_gate(vault, *, fixture):
    if (
        (not fixture and vault != VAULT)
        or vault.is_symlink()
        or not vault.is_dir()
        or vault.stat().st_mode & 0o077
    ):
        raise SnapshotError("STACK_VAULT_REQUIRED")
    key = vault / "raw.key"
    if key.is_symlink() or key.stat().st_mode & 0o077:
        raise SnapshotError("STACK_RAW_KEY")
    ctx = read(vault / "context.json")
    approval = read(vault / "approval.bound.json")
    check_approval(approval["approval"])
    if approval["context_sha256"] != sha(canonical(ctx)) or ctx["evidence_kind"] != (
        "offline_fixture" if fixture else "actual_provider_response"
    ):
        raise SnapshotError("STACK_CONTEXT_BINDING")
    return ctx, Fernet(key.read_bytes())


def require_time(ctx, minimum):
    start = datetime.fromisoformat(ctx["starts_at"]).timestamp()
    end = datetime.fromisoformat(ctx["expires_at"]).timestamp()
    now = time.time()
    if (
        end - start != publication.WINDOW_SECONDS
        or not start <= now < end
        or end - now < minimum
    ):
        raise SnapshotError("STACK_WINDOW_CLOSED")


def check_context(ctx, *, fixture, minimum=0):
    require_time(ctx, minimum)
    owner, cid, oid = (UUID(ctx[k]) for k in ("owner", "course_id", "operation_id"))
    current = asyncio.run(
        database(
            lambda db: publication.context(db, owner, cid, oid, fixture=fixture),
            fixture=fixture,
        )
    )
    if current != ctx:
        raise SnapshotError("STACK_CONTEXT_BINDING")


def observe(ctx, raw, body_receipt):
    if body_receipt != dict(
        http_status=200,
        encoding="identity",
        raw_sha256=sha(raw),
        raw_bytes=len(raw),
        complete=True,
    ):
        raise SnapshotError("STACK_HTTP_OR_EVIDENCE")
    result, observation = direct.observe_generation(m.request(), raw)
    receipt = dict(
        request_sha256=sha(canonical(m.request())),
        **body_receipt,
        observation=observation,
        usage=dict(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        ),
    )
    return publication.candidate(ctx, dict(result.value), receipt)


def send(vault, *, transport=None, key=None):
    if transport is not None and not isinstance(transport, httpx.MockTransport):
        raise SnapshotError("STACK_OFFLINE_TRANSPORT")
    fixture = transport is not None
    ctx, cipher = local_gate(vault, fixture=fixture)
    if any(
        (vault / name).exists() for name in ("STOP", "HALT", "generate.attempt.json")
    ):
        raise SnapshotError("STACK_BATCH_STOPPED")
    raw_io.exclusive(vault / "ACTIVE", b"one foreground request; stale means unknown\n")
    try:
        check_context(ctx, fixture=fixture, minimum=direct.IO_TIMEOUT)
        req = (PACKAGE / "request.json").read_bytes()
        if len(req) > 131072:
            raise SnapshotError("STACK_REQUEST_SIZE")
        if not fixture and (key is not None or not sys.stdin.isatty()):
            raise SnapshotError("STACK_TTY_REQUIRED")
        if key is None:
            key = getpass.getpass("Current DeepSeek API key (not saved): ")
        if not key or "\n" in key or "\r" in key:
            raise SnapshotError("STACK_KEY")
        target = approve_target(
            direct.ENDPOINT,
            policy=TargetPolicy(),
            **({"resolver": lambda h, p: ["93.184.216.34"]} if fixture else {}),
        )
        ip = ipaddress.ip_address(target.connect_ip)
        host = f"[{ip}]" if ip.version == 6 else str(ip)
        check_context(ctx, fixture=fixture, minimum=direct.IO_TIMEOUT)
        if (vault / "STOP").exists() or (vault / "HALT").exists():
            raise SnapshotError("STACK_BATCH_STOPPED")
        raw_io.exclusive(vault / "generate.request.json", req)
        save(
            vault,
            "generate.attempt.json",
            dict(
                request_sha256=sha(req),
                context_sha256=sha(canonical(ctx)),
                state="attempted_result_unknown",
                evidence_kind=ctx["evidence_kind"],
            ),
        )
        with (
            httpx.Client(
                transport=transport,
                timeout=direct.IO_TIMEOUT,
                trust_env=False,
                follow_redirects=False,
            ) as client,
            client.stream(
                "POST",
                f"https://{host}:443/responses",
                content=req,
                extensions={"sni_hostname": target.hostname},
                headers={
                    "Host": target.hostname,
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
            ) as response,
        ):
            status = response.status_code
            encoding = response.headers.get("content-encoding", "identity")
            save(
                vault,
                "generate.headers.json",
                dict(http_status=status, encoding=encoding),
            )
            raw = raw_io.collect(response, vault / "generate.raw.enc", cipher)
        body_receipt = dict(
            http_status=status,
            encoding=encoding,
            raw_sha256=sha(raw),
            raw_bytes=len(raw),
            complete=True,
        )
        if raw_io.decrypt(vault / "generate.raw.enc", cipher) != raw:
            raise SnapshotError("STACK_RAW_MISMATCH")
        save(vault, "generate.body.json", body_receipt)
        if key in raw.decode(errors="replace"):
            raise SnapshotError("STACK_KEY_ECHO")
        if (vault / "STOP").exists() or (vault / "HALT").exists():
            raise SnapshotError("STACK_BATCH_STOPPED")
        check_context(ctx, fixture=fixture)
        c = observe(ctx, raw, body_receipt)
        save(vault, "generate.candidate.json", c)
        raw_io.exclusive(vault / "STOP", SUCCESS_STOP)
        (vault / "ACTIVE").unlink()
        return c
    except BaseException as error:
        if not (vault / "STOP").exists():
            raw_io.exclusive(
                vault / "STOP", b"failed or unknown; preserve original; no retry\n"
            )
        save(
            vault,
            "generate.failure.json",
            dict(
                error_type=type(error).__name__,
                code=failure_code(error),
                attempted=(vault / "generate.attempt.json").exists(),
            ),
        )
        raise


def replay(vault, *, fixture=False):
    ctx, cipher = local_gate(vault, fixture=fixture)
    expected_attempt = dict(
        request_sha256=sha(canonical(m.request())),
        context_sha256=sha(canonical(ctx)),
        state="attempted_result_unknown",
        evidence_kind=ctx["evidence_kind"],
    )
    if (
        (vault / "STOP").read_bytes() != SUCCESS_STOP
        or (vault / "ACTIVE").exists()
        or (vault / "generate.failure.json").exists()
        or read(vault / "generate.attempt.json") != expected_attempt
        or (vault / "generate.request.json").read_bytes() != canonical(m.request())
    ):
        raise SnapshotError("STACK_SAVED_BINDING")
    receipt = read(vault / "generate.body.json")
    if read(vault / "generate.headers.json") != {
        key: receipt[key] for key in ("http_status", "encoding")
    }:
        raise SnapshotError("STACK_SAVED_BINDING")
    c = observe(ctx, raw_io.decrypt(vault / "generate.raw.enc", cipher), receipt)
    if c != read(vault / "generate.candidate.json"):
        raise SnapshotError("STACK_SAVED_BINDING")
    return c


def publish(vault, *, fixture=False):
    if (vault / "HALT").exists():
        raise SnapshotError("STACK_BATCH_STOPPED")
    c = replay(vault, fixture=fixture)
    review = read(vault / "review.json")
    result = asyncio.run(
        database(lambda db: publication.publish(db, c, review), fixture=fixture)
    )
    save(vault, "published.json", result)
    return result


async def stop(vault):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.services.free_course_recovery import Recovery

    ctx, _ = local_gate(vault, fixture=False)
    if not (vault / "HALT").exists():
        raw_io.exclusive(vault / "HALT", b"operator stopped batch; block publication\n")
    if not (vault / "STOP").exists():
        raw_io.exclusive(vault / "STOP", b"operator stopped batch; no send\n")
    publication.require_database()
    engine = create_database_engine()
    try:
        owner, cid, oid = (UUID(ctx[k]) for k in ("owner", "course_id", "operation_id"))
        return await Recovery(async_sessionmaker(engine)).cancel(
            owner, cid, oid, key=m.BATCH
        )
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("inspect", "prepare", "send", "replay", "publish", "stop")
    )
    parser.add_argument("--owner", type=UUID)
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "inspect":
            print(
                canonical(
                    dict(
                        manifest_sha256=package_digest(),
                        batch=m.BATCH,
                        request_sha256=sha(canonical(m.request())),
                        max_http_requests=1,
                        explicit_user_authorization=False,
                    )
                ).decode()
            )
        elif args.action == "prepare":
            if not args.owner or not args.approval:
                parser.error("prepare requires --owner and --approval")
            print(
                canonical(
                    asyncio.run(prepare(VAULT, args.owner, read(args.approval)))
                ).decode()
            )
        elif args.action == "send":
            print(send(VAULT)["candidate_digest"])
        elif args.action == "replay":
            print(replay(VAULT)["candidate_digest"])
        elif args.action == "stop":
            print(canonical(asyncio.run(stop(VAULT))).decode())
        else:
            print(canonical(publish(VAULT)).decode())
    except (Exception, KeyboardInterrupt) as error:
        print(
            "Stopped or refused; preserve evidence.",
            type(error).__name__,
            failure_code(error),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
