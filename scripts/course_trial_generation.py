"""Shared fixed-outline foreground request and reviewed private admission."""

import argparse
import asyncio
from datetime import datetime
import getpass
import hashlib
from pathlib import Path
import sys
import time
from uuid import UUID

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_database_engine
from app.services import course_trial_publication as publication
from app.services import queue_course_revision
from app.services.free_course_snapshots import canonical
from scripts import course_trial_transport as transport_io
from scripts import head_course_deepseek_wire as direct
from scripts.head_course_goal import ROOT, raw_io

STACK = publication.STACK


def package_path(profile):
    return ROOT / "docs/acceptance" / profile.package


def vault_path(profile):
    return Path.home() / ".local/share/edumind" / profile.materials.BATCH


PACKAGE = package_path(STACK)
VAULT = vault_path(STACK)
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


def package_digest(profile=STACK) -> str:
    package = package_path(profile)
    manifest = package / "manifest.json"
    if (package_path(profile) / "request.json").read_bytes() != canonical(
        profile.materials.request()
    ) or any(
        sha((ROOT / name).read_bytes()) != expected
        for name, expected in read(manifest)["files"].items()
    ):
        raise profile.error("PACKAGE_CHANGED")
    return sha(manifest.read_bytes())


def approval_values(profile=STACK):
    return dict(
        manifest_sha256=package_digest(profile),
        batch=profile.materials.BATCH,
        explicit_user_authorization=True,
        **{profile.approval_key: True},
        max_http_requests=1,
        window_seconds=publication.WINDOW_SECONDS,
    )


def check_approval(approval, *, profile=STACK):
    if canonical(approval) != canonical(approval_values(profile)):
        raise profile.error("EXACT_AUTHORIZATION_REQUIRED")


async def database(action, *, fixture, profile=STACK):
    publication.require_database(fixture=fixture, profile=profile)
    engine = create_database_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
            return await action(db)
    finally:
        await engine.dispose()


async def prepare(vault, owner, approval, *, fixture=False, profile=STACK):
    check_approval(approval, profile=profile)
    if not fixture and vault != vault_path(profile):
        raise profile.error("VAULT_REQUIRED")
    vault.mkdir(mode=0o700)
    try:
        ctx = await database(
            lambda db: publication.prepare(db, owner, fixture=fixture, profile=profile),
            fixture=fixture,
            profile=profile,
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


def local_gate(vault, *, fixture, profile=STACK):
    if (
        (not fixture and vault != vault_path(profile))
        or vault.is_symlink()
        or not vault.is_dir()
        or vault.stat().st_mode & 0o077
    ):
        raise profile.error("VAULT_REQUIRED")
    key = vault / "raw.key"
    if key.is_symlink() or key.stat().st_mode & 0o077:
        raise profile.error("RAW_KEY")
    ctx = read(vault / "context.json")
    approval = read(vault / "approval.bound.json")
    check_approval(approval["approval"], profile=profile)
    if approval["context_sha256"] != sha(canonical(ctx)) or ctx["evidence_kind"] != (
        "offline_fixture" if fixture else "actual_provider_response"
    ):
        raise profile.error("CONTEXT_BINDING")
    return ctx, Fernet(key.read_bytes())


def require_time(ctx, minimum, *, profile=STACK):
    start = datetime.fromisoformat(ctx["starts_at"]).timestamp()
    end = datetime.fromisoformat(ctx["expires_at"]).timestamp()
    now = time.time()
    if (
        end - start != publication.WINDOW_SECONDS
        or not start <= now < end
        or end - now < minimum
    ):
        raise profile.error("WINDOW_CLOSED")


def check_context(ctx, *, fixture, minimum=0, profile=STACK):
    require_time(ctx, minimum, profile=profile)
    owner, cid, oid = (UUID(ctx[k]) for k in ("owner", "course_id", "operation_id"))
    current = asyncio.run(
        database(
            lambda db: publication.context(
                db, owner, cid, oid, fixture=fixture, profile=profile
            ),
            fixture=fixture,
            profile=profile,
        )
    )
    if current != ctx:
        raise profile.error("CONTEXT_BINDING")


def observe(ctx, raw, body_receipt, *, profile=STACK):
    if body_receipt != dict(
        http_status=200,
        encoding="identity",
        raw_sha256=sha(raw),
        raw_bytes=len(raw),
        complete=True,
    ):
        raise profile.error("HTTP_OR_EVIDENCE")
    request = profile.materials.request()
    result, observation = direct.observe_generation(request, raw)
    receipt = dict(
        request_sha256=sha(canonical(request)),
        **body_receipt,
        observation=observation,
        usage=dict(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        ),
    )
    output = dict(result.value)
    if profile is publication.QUEUE_REVISION:
        output = queue_course_revision.merge(output)
    return publication.candidate(ctx, output, receipt, profile=profile)


def send(vault, *, transport=None, key=None, profile=STACK):
    if transport is not None and not isinstance(transport, httpx.MockTransport):
        raise profile.error("OFFLINE_TRANSPORT")
    fixture = transport is not None
    ctx, cipher = local_gate(vault, fixture=fixture, profile=profile)
    if any(
        (vault / name).exists() for name in ("STOP", "HALT", "generate.attempt.json")
    ):
        raise profile.error("BATCH_STOPPED")
    raw_io.exclusive(vault / "ACTIVE", b"one foreground request; stale means unknown\n")
    try:
        check_context(ctx, fixture=fixture, minimum=direct.IO_TIMEOUT, profile=profile)
        req = (package_path(profile) / "request.json").read_bytes()
        if len(req) > 131072:
            raise profile.error("REQUEST_SIZE")
        if not fixture and (key is not None or not sys.stdin.isatty()):
            raise profile.error("TTY_REQUIRED")
        if key is None:
            key = getpass.getpass("Current DeepSeek API key (not saved): ")
        if not key or "\n" in key or "\r" in key:
            raise profile.error("KEY")
        target = transport_io.resolve_target(transport)
        check_context(ctx, fixture=fixture, minimum=direct.IO_TIMEOUT, profile=profile)
        if (vault / "STOP").exists() or (vault / "HALT").exists():
            raise profile.error("BATCH_STOPPED")
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
        status, encoding, raw = transport_io.send_and_seal(
            target,
            key,
            req,
            vault / "generate.raw.enc",
            cipher,
            transport=transport,
            headers_path=vault / "generate.headers.json",
        )
        body_receipt = dict(
            http_status=status,
            encoding=encoding,
            raw_sha256=sha(raw),
            raw_bytes=len(raw),
            complete=True,
        )
        if raw_io.decrypt(vault / "generate.raw.enc", cipher) != raw:
            raise profile.error("RAW_MISMATCH")
        save(vault, "generate.body.json", body_receipt)
        if key in raw.decode(errors="replace"):
            raise profile.error("KEY_ECHO")
        if (vault / "STOP").exists() or (vault / "HALT").exists():
            raise profile.error("BATCH_STOPPED")
        check_context(ctx, fixture=fixture, profile=profile)
        c = observe(ctx, raw, body_receipt, profile=profile)
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


def replay(vault, *, fixture=False, profile=STACK):
    ctx, cipher = local_gate(vault, fixture=fixture, profile=profile)
    expected_attempt = dict(
        request_sha256=sha(canonical(profile.materials.request())),
        context_sha256=sha(canonical(ctx)),
        state="attempted_result_unknown",
        evidence_kind=ctx["evidence_kind"],
    )
    if (
        (vault / "STOP").read_bytes() != SUCCESS_STOP
        or (vault / "ACTIVE").exists()
        or (vault / "generate.failure.json").exists()
        or read(vault / "generate.attempt.json") != expected_attempt
        or (vault / "generate.request.json").read_bytes()
        != canonical(profile.materials.request())
    ):
        raise profile.error("SAVED_BINDING")
    receipt = read(vault / "generate.body.json")
    if read(vault / "generate.headers.json") != {
        key: receipt[key] for key in ("http_status", "encoding")
    }:
        raise profile.error("SAVED_BINDING")
    c = observe(
        ctx,
        raw_io.decrypt(vault / "generate.raw.enc", cipher),
        receipt,
        profile=profile,
    )
    if c != read(vault / "generate.candidate.json"):
        raise profile.error("SAVED_BINDING")
    return c


def publish(vault, *, fixture=False, profile=STACK):
    if (vault / "HALT").exists():
        raise profile.error("BATCH_STOPPED")
    c = replay(vault, fixture=fixture, profile=profile)
    review = read(vault / "review.json")
    result = asyncio.run(
        database(
            lambda db: publication.publish(db, c, review, profile=profile),
            fixture=fixture,
            profile=profile,
        )
    )
    save(vault, "published.json", result)
    return result


async def stop(vault, *, profile=STACK):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.services.free_course_recovery import Recovery

    ctx, _ = local_gate(vault, fixture=False, profile=profile)
    if not (vault / "HALT").exists():
        raw_io.exclusive(vault / "HALT", b"operator stopped batch; block publication\n")
    if not (vault / "STOP").exists():
        raw_io.exclusive(vault / "STOP", b"operator stopped batch; no send\n")
    publication.require_database(profile=profile)
    engine = create_database_engine()
    try:
        owner, cid, oid = (UUID(ctx[k]) for k in ("owner", "course_id", "operation_id"))
        return await Recovery(async_sessionmaker(engine)).cancel(
            owner, cid, oid, key=profile.materials.BATCH
        )
    finally:
        await engine.dispose()


def legacy_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("inspect", "prepare", "send", "replay", "publish", "stop")
    )
    parser.add_argument("--owner", type=UUID)
    parser.add_argument("--approval", type=Path)
    return run(parser, parser.parse_args(), STACK)


def run(parser, args, profile):
    vault = vault_path(profile)
    try:
        if args.action == "inspect":
            print(
                canonical(
                    dict(
                        manifest_sha256=package_digest(profile),
                        batch=profile.materials.BATCH,
                        request_sha256=sha(canonical(profile.materials.request())),
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
                    asyncio.run(
                        prepare(vault, args.owner, read(args.approval), profile=profile)
                    )
                ).decode()
            )
        elif args.action == "send":
            print(send(vault, profile=profile)["candidate_digest"])
        elif args.action == "replay":
            print(replay(vault, profile=profile)["candidate_digest"])
        elif args.action == "stop":
            print(canonical(asyncio.run(stop(vault, profile=profile))).decode())
        else:
            print(canonical(publish(vault, profile=profile)).decode())
    except (Exception, KeyboardInterrupt) as error:
        print(
            "Stopped or refused; preserve evidence.",
            type(error).__name__,
            failure_code(error),
            file=sys.stderr,
        )
        return 1
    return 0
