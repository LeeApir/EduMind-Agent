"""Envelope integrity plus actual PG isolation, expiry, rotation and races."""

import asyncio
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.credential_crypto import (
    CredentialFailure,
    CredentialKeyring,
    decrypt_secret,
    encrypt_secret,
    rewrap_secret,
)
from app.core.database import create_database_engine
from app.models.auth import GuestSessionRecord, User
from app.models.provider_connections import ProviderConnection
from app.services.provider_connections import (
    CredentialIdentity,
    ProviderConnectionStore,
    clean_expired_credentials,
)

SECRET = {"api_key": "TEST_ONLY_PHASE1_SECRET_NEVER_REAL", "api_secret": "TEST_ONLY_SECOND_SECRET"}
OLD = CredentialKeyring("old", {"old": b"o" * 32})
NEW = CredentialKeyring("new", {"old": b"o" * 32, "new": b"n" * 32})
URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pg = pytest.mark.skipif(not URL, reason="isolated PostgreSQL URL not set")


def test_envelope_integrity_rotation_randomness_and_safe_repr() -> None:
    context = b"owner/connection/session/target/version/expiry"
    a = encrypt_secret(SECRET, context, OLD)
    b = encrypt_secret(SECRET, context, OLD)
    assert a != b and SECRET["api_key"].encode() not in a
    assert decrypt_secret(a, context, OLD) == SECRET
    rotated = rewrap_secret(a, context, NEW)
    assert json.loads(rotated)["ciphertext"] == json.loads(a)["ciphertext"]
    assert json.loads(rotated)["wrap_nonce"] != json.loads(a)["wrap_nonce"]
    assert decrypt_secret(rotated, context, NEW) == SECRET
    for ring, aad in [(OLD, context), (NEW, context + b"other-owner")]:
        with pytest.raises(CredentialFailure) as failure:
            decrypt_secret(rotated, aad, ring)
        assert SECRET["api_key"] not in str(failure.value)
    assert "oooooooo" not in repr(OLD)


@pytest.mark.parametrize(
    "field", ["v", "alg", "kid", "nonce", "ciphertext", "wrap_nonce", "wrapped_key"]
)
def test_tampered_envelopes_fail_closed(field: str) -> None:
    raw = json.loads(encrypt_secret(SECRET, b"context", OLD))
    raw[field] = "invalid"
    with pytest.raises(CredentialFailure):
        decrypt_secret(json.dumps(raw).encode(), b"context", OLD)


def test_invalid_config_and_payload_do_not_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUMIND_CREDENTIAL_ACTIVE_KEY_ID", "missing")
    monkeypatch.setenv("EDUMIND_CREDENTIAL_KEYRING_JSON", SECRET["api_key"])
    with pytest.raises(CredentialFailure) as failure:
        CredentialKeyring.from_environment()
    assert failure.value.code == "CONFIGURATION_MISSING"
    assert SECRET["api_key"] not in str(failure.value)
    monkeypatch.setenv("EDUMIND_CREDENTIAL_ACTIVE_KEY_ID", "old")
    monkeypatch.setenv(
        "EDUMIND_CREDENTIAL_KEYRING_JSON", json.dumps({"old": base64.b64encode(b"o" * 32).decode()})
    )
    assert CredentialKeyring.from_environment().active_id == "old"
    for secret in [{"api_key": "x" * 4097}, {"password": SECRET["api_key"]}, {"api_key": ""}]:
        with pytest.raises(CredentialFailure):
            encrypt_secret(secret, b"context", OLD)


async def identity(factory: async_sessionmaker) -> CredentialIdentity:
    async with factory() as db, db.begin():
        user = User(id=uuid4(), is_guest=True)
        db.add(user)
        await db.flush()
        digest = uuid4().hex + uuid4().hex
        now = datetime.now(timezone.utc)
        db.add(
            GuestSessionRecord(
                token_hash=digest,
                user_id=user.id,
                created_at=now,
                expires_at=now + timedelta(hours=2),
            )
        )
        return CredentialIdentity(user.id, digest)


def store(
    factory: async_sessionmaker, ring: CredentialKeyring | None = OLD
) -> ProviderConnectionStore:
    return ProviderConnectionStore(factory, ring, resolver=lambda host, port: ["8.8.8.8"])


async def create(s: ProviderConnectionStore, who: CredentialIdentity) -> UUID:
    view = await s.create(
        who,
        provider_type="openai-compatible",
        display_name="test",
        base_url="https://provider.example/v1/",
        mode="persistent",
        secret=SECRET,
    )
    assert not {"secret", "encrypted_api_key", "originating_session_hash", "user_id"} & set(view)
    return UUID(str(view["id"]))


@pg
def test_actual_pg_owner_restart_versions_deletion_and_no_plaintext(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def run() -> None:
        engine = create_database_engine(URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            owner, other = await identity(factory), await identity(factory)
            s = store(factory)
            cid = await create(s, owner)
            assert await store(factory).decrypt(owner, cid, 1) == SECRET
            with pytest.raises(CredentialFailure, match="unavailable") as failure:
                await s.read(other, cid)
            assert failure.value.code == "NOT_FOUND"
            async with factory() as db:
                row = await db.get(ProviderConnection, cid)
                assert row is not None and row.encrypted_api_key is not None
                assert SECRET["api_key"].encode() not in row.encrypted_api_key
                assert SECRET["api_secret"].encode() not in row.encrypted_api_key
                old_blob = row.encrypted_api_key
            updated = await s.replace(owner, cid, 1, display_name="renamed")
            assert updated["config_version"] == 2
            assert await s.decrypt(owner, cid, 2) == SECRET
            with pytest.raises(CredentialFailure) as conflict:
                await s.replace(owner, cid, 1, secret=SECRET)
            assert conflict.value.code == "VERSION_CONFLICT"
            await s.replace(owner, cid, 2, base_url="https://another.example/v1")
            with pytest.raises(CredentialFailure) as missing:
                await s.decrypt(owner, cid, 3)
            assert missing.value.code == "CREDENTIAL_MISSING"
            await s.replace(owner, cid, 3, secret=SECRET)
            async with factory() as db:
                row = await db.get(ProviderConnection, cid)
                assert row is not None and row.encrypted_api_key != old_blob
            # Deleting does not need KEKs, and repeated original version is idempotent.
            await store(factory, None).delete(owner, cid, 4)
            await store(factory, None).delete(owner, cid, 4)
            with pytest.raises(CredentialFailure):
                await s.decrypt(owner, cid, 5)
            async with factory() as db:
                row = await db.get(ProviderConnection, cid)
                assert row is not None and row.deleted and row.encrypted_api_key is None
                assert row.credential_key_id is None
                assert await db.get(User, owner.user_id) is not None
            assert SECRET["api_key"] not in caplog.text and SECRET["api_secret"] not in caplog.text
        finally:
            await engine.dispose()

    asyncio.run(run())


@pg
def test_actual_pg_expiry_missing_parent_and_keyless_cleanup() -> None:
    async def run() -> None:
        engine = create_database_engine(URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            owner, missing_parent = await identity(factory), await identity(factory)
            first, second = (
                await create(store(factory), owner),
                await create(store(factory), missing_parent),
            )
            async with factory() as db, db.begin():
                await db.execute(
                    update(GuestSessionRecord)
                    .where(GuestSessionRecord.token_hash == owner.session_hash)
                    .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                )
                await db.execute(
                    delete(GuestSessionRecord).where(
                        GuestSessionRecord.token_hash == missing_parent.session_hash
                    )
                )
            assert await clean_expired_credentials(factory) >= 2
            assert await clean_expired_credentials(factory) == 0
            for who, cid in [(owner, first), (missing_parent, second)]:
                with pytest.raises(CredentialFailure) as failure:
                    await store(factory, None).decrypt(who, cid, 1)
                assert failure.value.code == "UNAUTHORIZED"
                async with factory() as db:
                    row = await db.get(ProviderConnection, cid)
                    assert row is not None and row.encrypted_api_key is None and not row.enabled
                    assert await db.get(User, who.user_id) is not None
        finally:
            await engine.dispose()

    asyncio.run(run())


@pg
def test_actual_pg_concurrent_update_and_resumable_rotation() -> None:
    async def run() -> None:
        engine = create_database_engine(URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            owner = await identity(factory)
            s = store(factory)
            cid = await create(s, owner)
            results = await asyncio.gather(
                s.replace(owner, cid, 1, secret={"api_key": "TEST_ONLY_A"}),
                s.replace(owner, cid, 1, secret={"api_key": "TEST_ONLY_B"}),
                return_exceptions=True,
            )
            assert sum(isinstance(r, dict) for r in results) == 1
            assert (
                sum(
                    isinstance(r, CredentialFailure) and r.code == "VERSION_CONFLICT"
                    for r in results
                )
                == 1
            )
            second = await create(s, owner)
            before = await s.decrypt(owner, cid, 2)
            rotating = store(factory, NEW)
            assert await rotating.rotate_batch(limit=1) == (1, 0)
            await store(factory, NEW).rotate_batch(limit=100)
            assert await store(factory, NEW).rotate_batch() == (0, 0)
            assert await rotating.decrypt(owner, cid, 2) == before
            assert await rotating.decrypt(owner, second, 1) == SECRET
            await s.delete(owner, second, 1)
            assert await rotating.rotate_batch() == (0, 0)
            async with factory() as db:
                row = await db.get(ProviderConnection, second)
                assert row is not None and row.encrypted_api_key is None
            # A corrupt old envelope remains intact and is not reported rotated.
            broken = await create(s, owner)
            async with factory() as db, db.begin():
                row = await db.get(ProviderConnection, broken)
                assert row is not None
                row.encrypted_api_key = b"not-a-valid-envelope"
            assert await rotating.rotate_batch() == (0, 1)
            async with factory() as db:
                row = await db.get(ProviderConnection, broken)
                assert row is not None and row.encrypted_api_key == b"not-a-valid-envelope"
            racing = await create(s, owner)
            await asyncio.gather(rotating.rotate_batch(), s.delete(owner, racing, 1))
            async with factory() as db:
                row = await db.get(ProviderConnection, racing)
                assert row is not None and row.deleted and row.encrypted_api_key is None
        finally:
            await engine.dispose()

    asyncio.run(run())


@pg
def test_missing_master_key_keeps_metadata_and_zero_probe() -> None:
    async def run() -> None:
        engine = create_database_engine(URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            owner = await identity(factory)
            cid = await create(store(factory), owner)
            no_keys = ProviderConnectionStore(
                factory, None, resolver=lambda *args: pytest.fail("DNS should not be reached")
            )
            assert (await no_keys.read(owner, cid))["id"] == str(cid)
            with pytest.raises(CredentialFailure) as failure:
                await create(no_keys, owner)
            assert failure.value.code == "CONFIGURATION_MISSING"
            with pytest.raises(CredentialFailure):
                await no_keys.decrypt(owner, cid, 1)
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_cleanup_loop_interval_and_safe_failures(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app.core import credential_cleanup

    calls = []

    async def fail(factory: object) -> int:
        calls.append("cleanup")
        raise RuntimeError(SECRET["api_key"])

    async def sleep(delay: float) -> None:
        calls.append(delay)
        raise asyncio.CancelledError()

    monkeypatch.setattr(credential_cleanup, "clean_expired_credentials", fail)
    monkeypatch.setattr(credential_cleanup.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(credential_cleanup.cleanup_loop(None))
    assert calls == ["cleanup", 60]
    assert "cleanup unavailable" in caplog.text
    assert SECRET["api_key"] not in caplog.text
