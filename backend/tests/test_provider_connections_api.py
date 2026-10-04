"""Real-PG owner/CSRF/version/secret contracts for CRUD and temporary uploads."""

import asyncio
import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import provider_connections as api
from app.core.auth import COOKIE_NAME, token_hash
from app.core.credential_crypto import CredentialKeyring
from app.core.database import create_database_engine
from app.main import app
from app.models.auth import GuestSessionRecord, User
from app.models.provider_connections import ProviderConnection

KEY = "TEST_ONLY_T009_API_SECRET"
DB_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pg = pytest.mark.skipif(not DB_URL, reason="dedicated PostgreSQL URL not set")
ROOT = "/api/providers/connections"
DOC = json.loads((Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml").read_text())


def schema(name):
    def expand(value):
        if isinstance(value, dict):
            if "$ref" in value:
                return expand(DOC["components"]["schemas"][value["$ref"].split("/")[-1]])
            return {k: expand(v) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(v) for v in value]
        return value

    return Draft202012Validator(expand(DOC["components"]["schemas"][name]))


def payload(mode="persistent", **fields):
    value = {
        "provider_type": "openai-compatible",
        "display_name": "synthetic",
        "base_url": "https://provider.test/v1/",
        "credential_mode": mode,
    }
    if mode == "persistent":
        value["secret"] = {"api_key": KEY}
    value.update(fields)
    return value


def upload(version=1, **fields):
    value = {
        "secret": {"api_key": KEY},
        "operation_id": str(uuid4()),
        "purpose": "connection_test",
        "consent": {
            "accepted": True,
            "config_version": version,
            "model_id": "synthetic-model",
            "data_categories": ["probe"],
        },
    }
    value.update(fields)
    return value


def private(response):
    assert response.headers["cache-control"] == "private, no-store"
    assert KEY not in response.text


def guest(client, users):
    response = client.post("/api/auth/guest")
    assert response.status_code == 201
    users.add(UUID(response.json()["user"]["id"]))
    return response.cookies[COOKIE_NAME], {"X-CSRF-Token": response.json()["csrf_token"]}


def restore(client, token):
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, token)


@pytest.fixture
def setup_api(monkeypatch):
    assert DB_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", DB_URL)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    monkeypatch.setenv("EDUMIND_PROVIDER_DEPLOYMENT", "cloud")
    monkeypatch.delenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", raising=False)
    monkeypatch.setenv("EDUMIND_CREDENTIAL_ACTIVE_KEY_ID", "old")
    monkeypatch.setenv(
        "EDUMIND_CREDENTIAL_KEYRING_JSON", json.dumps({"old": base64.b64encode(b"o" * 32).decode()})
    )
    dns = []

    def resolve(host, port):
        dns.append((host, port))
        return ["8.8.8.8"]

    monkeypatch.setattr(api, "resolve_addresses", resolve)

    async def forbid(*args, **kwargs):
        pytest.fail("CRUD/upload invoked an HTTP Provider")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbid)
    users = set()
    with TestClient(app, base_url="https://testserver") as client:
        yield client, users, dns

    async def clean():
        engine = create_database_engine(DB_URL)
        try:
            async with engine.begin() as db:
                await db.execute(
                    delete(ProviderConnection).where(ProviderConnection.user_id.in_(users))
                )
                await db.execute(
                    delete(GuestSessionRecord).where(GuestSessionRecord.user_id.in_(users))
                )
                await db.execute(delete(User).where(User.id.in_(users)))
        finally:
            await engine.dispose()

    asyncio.run(clean())


def test_input_secret_repr_and_invalid_models_hide_values():
    s = api.ProviderSecret(api_key=KEY, api_secret="TEST_SECOND")
    body = api.ConnectionCreate(**payload())
    assert KEY not in repr(s) and KEY not in repr(body)
    assert s.values()["api_key"] == KEY
    with pytest.raises(ValueError) as e:
        api.ProviderSecret(api_key=KEY + "x" * 4096)
    assert KEY not in str(e.value)


@pg
def test_crud_safe_queries_versions_and_delete_replay(setup_api, caplog):
    client, users, dns = setup_api
    _, headers = guest(client, users)
    created = client.post(ROOT, json=payload(), headers=headers)
    assert created.status_code == 201
    private(created)
    schema("ProviderConnection").validate(created.json())
    cid = created.json()["id"]
    assert created.json()["base_url"] == "https://provider.test/v1"
    assert created.json()["config_version"] == 1 and created.json()["credential_state"] == "present"
    before = len(dns)
    listed = client.get(ROOT)
    read = client.get(ROOT + "/" + cid)
    private(listed)
    private(read)
    assert listed.json() == {"items": [read.json()]} and len(dns) == before
    renamed = client.patch(
        ROOT + "/" + cid, json={"display_name": "renamed"}, headers={**headers, "If-Match": "1"}
    )
    private(renamed)
    assert renamed.status_code == 200
    assert renamed.json()["config_version"] == 2 and renamed.json()["credential_state"] == "present"
    conflict = client.patch(
        ROOT + "/" + cid, json={"secret": {"api_key": KEY}}, headers={**headers, "If-Match": "1"}
    )
    private(conflict)
    assert conflict.status_code == 409 and conflict.json()["code"] == "VERSION_CONFLICT"
    for _ in range(2):
        deleted = client.delete(ROOT + "/" + cid, headers={**headers, "If-Match": "2"})
        private(deleted)
        assert deleted.status_code == 204 and deleted.content == b""
    wrong = client.delete(ROOT + "/" + cid, headers={**headers, "If-Match": "3"})
    private(wrong)
    assert wrong.status_code == 409
    missing = client.get(ROOT + "/" + cid)
    private(missing)
    assert missing.status_code == 404
    assert client.get(ROOT).json() == {"items": []}
    assert KEY not in caplog.text

    async def check():
        engine = create_database_engine(DB_URL)
        try:
            async with async_sessionmaker(engine)() as db:
                row = await db.get(ProviderConnection, UUID(cid))
                assert row.deleted and not row.enabled and row.encrypted_api_key is None
                assert row.credential_key_id is None and row.config_version == 3
        finally:
            await engine.dispose()

    asyncio.run(check())


@pg
def test_create_disabled_target_change_and_key_clear(setup_api):
    client, users, _ = setup_api
    _, headers = guest(client, users)
    out = client.post(ROOT, json=payload(enabled=False), headers=headers)
    assert out.status_code == 201 and out.json()["enabled"] is False
    cid = out.json()["id"]
    changed = client.patch(
        ROOT + "/" + cid,
        json={"base_url": "https://new.test/v1", "enabled": True},
        headers={**headers, "If-Match": "1"},
    )
    assert changed.status_code == 200 and changed.json()["credential_state"] == "missing"
    version = 2
    for patch, state in [({"secret": {"api_key": KEY}}, "present"), ({"secret": None}, "missing")]:
        out = client.patch(
            ROOT + "/" + cid, json=patch, headers={**headers, "If-Match": str(version)}
        )
        private(out)
        assert out.status_code == 200 and out.json()["credential_state"] == state
        version += 1
    changed = client.patch(
        ROOT + "/" + cid,
        json={"provider_type": "ollama", "credential_mode": "none"},
        headers={**headers, "If-Match": str(version)},
    )
    assert changed.status_code == 200 and changed.json()["credential_state"] == "missing"
    assert changed.json()["provider_type"] == "ollama"


@pg
def test_cross_owner_and_originating_session_isolation_precede_key_read(setup_api, monkeypatch):
    client, users, dns = setup_api
    token_a, headers_a = guest(client, users)
    out = client.post(ROOT, json=payload(), headers=headers_a)
    cid = out.json()["id"]
    _, headers_b = guest(client, users)

    def forbid():
        pytest.fail("foreign request loaded the master keyring")

    monkeypatch.setattr(CredentialKeyring, "from_environment", forbid)
    before = len(dns)
    assert client.get(ROOT).json() == {"items": []}
    replies = [
        client.get(ROOT + "/" + cid),
        client.patch(
            ROOT + "/" + cid,
            json={"secret": {"api_key": KEY}},
            headers={**headers_b, "If-Match": "1"},
        ),
        client.delete(ROOT + "/" + cid, headers={**headers_b, "If-Match": "1"}),
        client.post(ROOT + "/" + cid + "/temporary-credentials", json=upload(), headers=headers_b),
    ]
    for response in replies:
        private(response)
        assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    assert len(dns) == before
    restore(client, token_a)
    assert client.get(ROOT + "/" + cid).status_code == 200


@pg
@pytest.mark.parametrize(
    "invalid", ["no-cookie", "csrf-missing", "csrf-wrong", "origin", "expired"]
)
def test_auth_csrf_and_expiry_deny_before_keyring_or_dns(invalid, setup_api, monkeypatch):
    client, users, dns = setup_api
    token, headers = guest(client, users)
    if invalid == "no-cookie":
        client.cookies.clear()
    elif invalid == "csrf-missing":
        headers = {}
    elif invalid == "csrf-wrong":
        headers = {"X-CSRF-Token": "wrong"}
    elif invalid == "origin":
        headers["Origin"] = "https://foreign.test"
    elif invalid == "expired":

        async def expire():
            engine = create_database_engine(DB_URL)
            try:
                async with engine.begin() as db:
                    await db.execute(
                        update(GuestSessionRecord)
                        .where(GuestSessionRecord.token_hash == token_hash(token))
                        .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                    )
            finally:
                await engine.dispose()

        asyncio.run(expire())

    def forbid():
        pytest.fail("unauthorized request loaded the master keyring")

    monkeypatch.setattr(CredentialKeyring, "from_environment", forbid)
    response = client.post(ROOT, json=payload(), headers=headers)
    private(response)
    assert response.status_code == (401 if invalid in {"no-cookie", "expired"} else 403)
    assert not dns


@pg
@pytest.mark.parametrize(
    "change",
    [
        {"user_id": str(uuid4())},
        {"originating_session_hash": KEY},
        {"is_local": True},
        {"credential_mode": "persistent", "secret": None},
        {"credential_mode": "none"},
        {"credential_mode": "temporary"},
        {"secret": {"api_key": 123}},
        {"secret": {"api_key": KEY, "headers": {"Authorization": KEY}}},
        {"secret": {"api_key": ""}},
        {"secret": {"api_key": KEY, "api_secret": None}},
        {"enabled": 1},
        {"provider_type": "unregistered"},
    ],
)
def test_invalid_creation_fixed_errors_no_secret_echo(change, setup_api):
    client, users, _ = setup_api
    _, headers = guest(client, users)
    response = client.post(ROOT, json=payload(**change), headers=headers)
    private(response)
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"
    assert client.get(ROOT).json() == {"items": []}


@pg
@pytest.mark.parametrize("version", [None, "0", "-1", "1.0", '"1"', "*", "01"])
def test_invalid_if_match_does_not_modify(version, setup_api):
    client, users, _ = setup_api
    _, headers = guest(client, users)
    cid = client.post(ROOT, json=payload(), headers=headers).json()["id"]
    if version is not None:
        headers = {**headers, "If-Match": version}
    for method in ("patch", "delete"):
        response = (
            client.patch(ROOT + "/" + cid, json={"display_name": "change"}, headers=headers)
            if method == "patch"
            else client.delete(ROOT + "/" + cid, headers=headers)
        )
        private(response)
        assert response.status_code == 422
    assert client.get(ROOT + "/" + cid).json()["config_version"] == 1


@pg
def test_missing_keyring_read_delete_health_and_catalog_survive(setup_api, monkeypatch):
    client, users, _ = setup_api
    _, headers = guest(client, users)
    cid = client.post(ROOT, json=payload(), headers=headers).json()["id"]
    monkeypatch.delenv("EDUMIND_CREDENTIAL_KEYRING_JSON")
    assert client.get("/health").status_code == 200
    assert client.get("/api/catalog").status_code == 200
    assert client.get("/api/runtime").json() == {"mode": "catalog_only"}
    assert client.get(ROOT + "/" + cid).status_code == 200
    assert client.get(ROOT).status_code == 200
    for response in [
        client.post(ROOT, json=payload(), headers=headers),
        client.patch(
            ROOT + "/" + cid,
            json={"secret": {"api_key": KEY}},
            headers={**headers, "If-Match": "1"},
        ),
    ]:
        private(response)
        assert response.status_code == 503
        assert response.json()["code"] == "CONFIGURATION_MISSING"
    assert client.delete(ROOT + "/" + cid, headers={**headers, "If-Match": "1"}).status_code == 204


@pg
def test_patch_race_only_one_version_wins_and_restart_keeps_safe_metadata(setup_api):
    client, users, _ = setup_api
    token, headers = guest(client, users)
    cid = client.post(ROOT, json=payload(), headers=headers).json()["id"]

    def patch(name):
        return client.patch(
            ROOT + "/" + cid, json={"display_name": name}, headers={**headers, "If-Match": "1"}
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(patch, ["first", "second"]))
    assert sorted(r.status_code for r in replies) == [200, 409]
    for r in replies:
        private(r)
    with TestClient(app, base_url="https://testserver") as restarted:
        restore(restarted, token)
        read = restarted.get(ROOT + "/" + cid)
        private(read)
        assert read.status_code == 200 and read.json()["config_version"] == 2


@pg
def test_temporary_receipt_limits_revoke_and_never_persist(setup_api):
    client, users, _ = setup_api
    token, headers = guest(client, users)
    cid = client.post(ROOT, json=payload("temporary"), headers=headers).json()["id"]
    receipts = []
    for _ in range(4):
        out = client.post(
            ROOT + "/" + cid + "/temporary-credentials", json=upload(), headers=headers
        )
        private(out)
        assert out.status_code == 201
        schema("TemporaryCredentialReceipt").validate(out.json())
        expiry = datetime.fromisoformat(out.json()["expires_at"])
        assert 0 < (expiry - datetime.now(timezone.utc)).total_seconds() <= 300
        assert out.json()["handle"] not in out.request.url.path
        receipts.append(out.json())
    out = client.post(ROOT + "/" + cid + "/temporary-credentials", json=upload(), headers=headers)
    private(out)
    assert out.status_code == 503 and out.json()["code"] == "CREDENTIAL_UNAVAILABLE"
    assert client.get(ROOT + "/" + cid).json()["credential_state"] == "missing"
    renamed = client.patch(
        ROOT + "/" + cid, json={"display_name": "renewed"}, headers={**headers, "If-Match": "1"}
    )
    assert renamed.status_code == 200
    new = client.post(ROOT + "/" + cid + "/temporary-credentials", json=upload(2), headers=headers)
    assert new.status_code == 201  # all four old handles were retired by version update
    with TestClient(app, base_url="https://testserver") as restarted:
        restore(restarted, token)
        assert restarted.get(ROOT + "/" + cid).json()["credential_state"] == "missing"

    async def check():
        engine = create_database_engine(DB_URL)
        try:
            async with async_sessionmaker(engine)() as db:
                row = await db.get(ProviderConnection, UUID(cid))
                assert row.encrypted_api_key is None and row.credential_key_id is None
        finally:
            await engine.dispose()

    asyncio.run(check())


@pg
@pytest.mark.parametrize(
    "change,code",
    [
        (
            {
                "consent": {
                    "accepted": False,
                    "config_version": 1,
                    "model_id": "m",
                    "data_categories": ["probe"],
                }
            },
            "CONSENT_REQUIRED",
        ),
        (
            {
                "consent": {
                    "accepted": True,
                    "config_version": 2,
                    "model_id": "m",
                    "data_categories": ["probe"],
                }
            },
            "VERSION_CONFLICT",
        ),
        (
            {
                "consent": {
                    "accepted": True,
                    "config_version": 1,
                    "model_id": "m",
                    "data_categories": ["learning_goal"],
                }
            },
            "CONSENT_REQUIRED",
        ),
    ],
)
def test_temporary_consent_bound_to_actual_version_and_probe(change, code, setup_api):
    client, users, _ = setup_api
    _, headers = guest(client, users)
    cid = client.post(ROOT, json=payload("temporary"), headers=headers).json()["id"]
    response = client.post(
        ROOT + "/" + cid + "/temporary-credentials", json=upload(**change), headers=headers
    )
    private(response)
    assert response.status_code == 409 and response.json()["code"] == code


@pg
def test_invalid_target_is_safe_and_no_network_probe(setup_api):
    client, users, dns = setup_api
    _, headers = guest(client, users)
    out = client.post(
        ROOT,
        json=payload(base_url="https://" + KEY + "@example.test/v1?secret=" + KEY),
        headers=headers,
    )
    private(out)
    assert out.status_code == 422 and out.json()["code"] == "INVALID_TARGET"
    assert not dns and client.get(ROOT).json() == {"items": []}


@pg
def test_another_valid_session_of_same_owner_cannot_take_connection(setup_api):
    from app.core.auth import csrf_for_token

    client, users, _ = setup_api
    original, headers = guest(client, users)
    cid = client.post(ROOT, json=payload(), headers=headers).json()["id"]
    other_token = uuid4().hex + uuid4().hex

    async def add_session():
        engine = create_database_engine(DB_URL)
        try:
            async with async_sessionmaker(engine)() as db, db.begin():
                auth = await db.get(GuestSessionRecord, token_hash(original))
                now = datetime.now(timezone.utc)
                db.add(
                    GuestSessionRecord(
                        token_hash=token_hash(other_token),
                        user_id=auth.user_id,
                        created_at=now,
                        expires_at=now + timedelta(hours=2),
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(add_session())
    restore(client, other_token)
    assert client.get("/api/auth/session").status_code == 200
    assert client.get(ROOT).json() == {"items": []}
    for response in [
        client.get(ROOT + "/" + cid),
        client.delete(
            ROOT + "/" + cid, headers={"X-CSRF-Token": csrf_for_token(other_token), "If-Match": "1"}
        ),
    ]:
        private(response)
        assert response.status_code == 404


@pg
@pytest.mark.parametrize("action", ["create", "patch"])
def test_session_expired_during_dns_cannot_commit_credentials(action, setup_api, monkeypatch):
    from threading import Event

    client, users, _ = setup_api
    token, headers = guest(client, users)
    cid = client.post(ROOT, json=payload(), headers=headers).json()["id"]
    entered = Event()
    release = Event()

    def wait_dns(host, port):
        entered.set()
        assert release.wait(5), "test did not release DNS gate"
        return ["8.8.8.8"]

    monkeypatch.setattr(api, "resolve_addresses", wait_dns)

    async def expire_and_check(check=False):
        engine = create_database_engine(DB_URL)
        try:
            async with engine.begin() as db:
                if check:
                    count = await db.execute(
                        select(ProviderConnection.config_version).where(
                            ProviderConnection.user_id.in_(users)
                        )
                    )
                    assert list(count.scalars()) == [1]
                else:
                    await db.execute(
                        update(GuestSessionRecord)
                        .where(GuestSessionRecord.token_hash == token_hash(token))
                        .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                    )
        finally:
            await engine.dispose()

    def modify():
        if action == "create":
            return client.post(ROOT, json=payload(), headers=headers)
        return client.patch(
            ROOT + "/" + cid,
            json={"secret": {"api_key": KEY}},
            headers={**headers, "If-Match": "1"},
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(modify)
        try:
            assert entered.wait(3)
            asyncio.run(expire_and_check())
        finally:
            release.set()
        response = future.result(timeout=3)
    private(response)
    assert response.status_code == 401 and response.json()["code"] == "UNAUTHORIZED"
    asyncio.run(expire_and_check(check=True))


@pg
def test_list_bound_is_one_hundred_safe_owner_records(setup_api):
    client, users, _ = setup_api
    token, headers = guest(client, users)
    cid = client.post(ROOT, json=payload("none"), headers=headers).json()["id"]

    async def fill():
        engine = create_database_engine(DB_URL)
        try:
            async with async_sessionmaker(engine)() as db, db.begin():
                row = await db.get(ProviderConnection, UUID(cid))
                for index in range(101):
                    db.add(
                        ProviderConnection(
                            id=uuid4(),
                            user_id=row.user_id,
                            originating_session_hash=token_hash(token),
                            provider_type=row.provider_type,
                            display_name=f"synthetic-{index}",
                            base_url=row.base_url,
                            is_local=False,
                            enabled=True,
                            deleted=False,
                            config_version=1,
                            credential_version=1,
                            credential_mode="none",
                            credential_expires_at=row.credential_expires_at,
                            created_at=row.created_at,
                            updated_at=row.updated_at,
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(fill())
    response = client.get(ROOT)
    private(response)
    assert response.status_code == 200 and len(response.json()["items"]) == 100
    for item in response.json()["items"]:
        schema("ProviderConnection").validate(item)


@pg
def test_storage_error_is_fixed_and_never_echoes_sql_secret(setup_api, monkeypatch, caplog):
    from sqlalchemy.exc import SQLAlchemyError

    client, users, _ = setup_api
    guest(client, users)

    async def fail(*args):
        raise SQLAlchemyError(KEY)

    monkeypatch.setattr(api.ProviderConnectionStore, "list", fail)
    response = client.get(ROOT)
    private(response)
    assert response.status_code == 503 and response.json()["code"] == "TEMPORARILY_UNAVAILABLE"
    assert KEY not in caplog.text
