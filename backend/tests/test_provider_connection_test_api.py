"""Explicit probe API with real owner storage and strictly mocked outbound HTTP."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_provider_connections_api import (
    KEY,
    ROOT,
    guest,
    payload,
    pg,
    private,
    restore,
    schema,
    setup_api,  # noqa: F401 -- shared real-PG lifecycle fixture
    upload,
)

from app.api import provider_probe as api
from app.core.auth import token_hash
from app.core.credential_crypto import CredentialFailure
from app.core.database import create_database_engine
from app.main import app
from app.models.auth import GuestSessionRecord
from app.services import provider_probe as service

ORIGINAL_SEND = httpx.AsyncClient.send


class Budget:
    def __init__(self, deny_attempt=False):
        self.preflights = []
        self.attempts = []
        self.deny_attempt = deny_attempt

    async def preflight(self, request):
        self.preflights.append(request)

    async def authorize_attempt(self, request):
        self.attempts.append(request)
        if self.deny_attempt:
            raise CredentialFailure("BUDGET_NOT_AUTHORIZED")


def probe(**fields):
    value = {k: v for k, v in upload().items() if k not in {"secret", "purpose"}}
    value.update(fields)
    return value


def output(text="OK", usage=True):
    body = {
        "model": "synthetic-model",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 7, "completion_tokens": 1}
    return body


@pytest.fixture
def probe_api(setup_api, monkeypatch):  # noqa: F811 -- imported pytest fixture
    client, users, dns = setup_api
    monkeypatch.setattr(httpx.AsyncClient, "send", ORIGINAL_SEND)
    budget = Budget()
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=output())

    overrides = app.dependency_overrides.copy()
    app.dependency_overrides[api.probe_budget] = lambda: budget
    app.dependency_overrides[api.probe_transport] = lambda: httpx.MockTransport(handler)
    try:
        yield client, users, dns, budget, sent
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)


def create(client, headers, **fields):
    response = client.post(ROOT, headers=headers, json=payload(**fields))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def call(client, cid, headers, body=None):
    return client.post(ROOT + "/" + cid + "/test", headers=headers, json=body or probe())


@pg
@pytest.mark.parametrize("mode", ["persistent", "temporary", "none"])
def test_default_budget_denies_without_http_or_consuming_handle(probe_api, mode):
    client, users, _, budget, sent = probe_api
    _, headers = guest(client, users)
    cid = create(client, headers, mode=mode)
    body = probe()
    if mode == "temporary":
        secret = upload(operation_id=body["operation_id"])
        receipt = client.post(
            ROOT + "/" + cid + "/temporary-credentials", headers=headers, json=secret
        )
        assert receipt.status_code == 201
        body["temporary_handle"] = receipt.json()["handle"]
    app.dependency_overrides.pop(api.probe_budget)
    denied = call(client, cid, headers, body)
    private(denied)
    assert denied.status_code == 403 and denied.json()["code"] == "BUDGET_NOT_AUTHORIZED"
    assert not sent and not budget.attempts
    app.dependency_overrides[api.probe_budget] = lambda: budget
    accepted = call(client, cid, headers, body)
    assert accepted.status_code == 200, accepted.text
    assert len(sent) == 1 and len(budget.attempts) == 1
    if mode == "temporary":
        replay = call(client, cid, headers, body)
        assert replay.status_code == 503 and len(sent) == 1


@pg
@pytest.mark.parametrize("usage", [True, False])
def test_one_fixed_prompt_actual_target_unknown_capabilities_and_no_echo(probe_api, caplog, usage):
    client, users, _, budget, sent = probe_api
    _, headers = guest(client, users)
    cid = create(client, headers)

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=output(KEY, usage))

    app.dependency_overrides[api.probe_transport] = lambda: httpx.MockTransport(handler)
    result = call(client, cid, headers)
    private(result)
    assert result.status_code == 200, result.text
    schema("ProviderProbeResult").validate(result.json())
    value = result.json()
    assert value["target"] == "https://provider.test/v1"
    assert value["is_local"] is False and value["model_id"] == "synthetic-model"
    assert value["connection_id"] == cid and value["config_version"] == 1
    assert value["requests"] == 1
    assert value["usage"] == ({"input_tokens": 7, "output_tokens": 1} if usage else None)
    assert value["capabilities"]["source"] == "unknown"
    assert all(
        value["capabilities"][k] is None
        for k in (
            "streaming",
            "structured_output",
            "tool_calling",
            "vision",
            "embedding",
            "tts",
            "asr",
        )
    )
    assert "may contact" in result.headers["x-provider-probe-notice"]
    assert len(sent) == len(budget.preflights) == len(budget.attempts) == 1
    wire = json.loads(sent[0].content)
    assert sent[0].url.path == "/v1/chat/completions"
    assert wire == {
        "model": "synthetic-model",
        "messages": [{"role": "user", "content": "Reply only with OK."}],
        "max_tokens": 8,
        "temperature": 0,
        "stream": False,
    }
    # Trace/HTTPX strips the transient secret header after send, even in Mock tests.
    assert "authorization" not in sent[0].headers and KEY not in caplog.text
    assert budget.attempts[0].purpose == "connection_test"


@pg
def test_native_ollama_only_exact_local_whitelist(probe_api, monkeypatch):
    client, users, _, budget, sent = probe_api
    monkeypatch.setenv("EDUMIND_PROVIDER_DEPLOYMENT", "local")
    monkeypatch.setenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", "127.0.0.1:11434")
    _, headers = guest(client, users)
    cid = create(
        client, headers, mode="none", provider_type="ollama", base_url="http://127.0.0.1:11434"
    )

    def handler(request):
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "model": "synthetic-model",
                "message": {"role": "assistant", "content": "OK"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 7,
                "eval_count": 1,
            },
        )

    app.dependency_overrides[api.probe_transport] = lambda: httpx.MockTransport(handler)
    result = call(client, cid, headers)
    assert result.status_code == 200, result.text
    assert result.json()["target"] == "http://127.0.0.1:11434"
    assert sent[0].url.path == "/api/chat"
    assert result.json()["is_local"] is True and len(sent) == len(budget.attempts) == 1
    wire = json.loads(sent[0].content)
    assert wire["options"] == {"num_predict": 8, "temperature": 0}
    assert wire["stream"] is False and "format" not in wire


@pg
@pytest.mark.parametrize(
    "kind",
    [
        "owner",
        "csrf",
        "version",
        "consent",
        "categories",
        "disabled",
        "missing",
        "extra",
        "null_handle",
        "invalid_model",
    ],
)
def test_rejections_before_budget_and_network(probe_api, kind):
    client, users, _, budget, sent = probe_api
    _, headers = guest(client, users)
    cid = create(client, headers, enabled=kind != "disabled")
    body = probe()
    expected = 409
    if kind == "owner":
        _, headers = guest(client, users)
        expected = 404
    elif kind == "csrf":
        headers = {}
        expected = 403
    elif kind == "version":
        body["consent"]["config_version"] = 2
    elif kind == "consent":
        body["consent"]["accepted"] = False
    elif kind == "categories":
        body["consent"]["data_categories"] = ["learning_goal"]
    elif kind == "disabled":
        expected = 503
    elif kind == "missing":
        assert (
            client.patch(
                ROOT + "/" + cid, headers={**headers, "If-Match": "1"}, json={"secret": None}
            ).status_code
            == 200
        )
        body["consent"]["config_version"] = 2
        expected = 503
    elif kind == "extra":
        body["prompt"] = KEY
        expected = 422
    elif kind == "null_handle":
        body["temporary_handle"] = None
        expected = 422
    elif kind == "invalid_model":
        body["consent"]["model_id"] = "model\n" + KEY
        expected = 422
    result = call(client, cid, headers, body)
    private(result)
    assert result.status_code == expected, result.text
    assert not budget.preflights and not budget.attempts and not sent


@pg
def test_missing_cookie_and_expired_session_cannot_send(probe_api):
    client, users, _, budget, sent = probe_api
    token, headers = guest(client, users)
    cid = create(client, headers)
    client.cookies.clear()
    out = call(client, cid, headers)
    assert out.status_code == 401 and not sent and not budget.preflights
    restore(client, token)
    from test_provider_connections_api import DB_URL

    async def expire():
        engine = create_database_engine(DB_URL)
        try:
            async with async_sessionmaker(engine)() as db, db.begin():
                await db.execute(
                    update(GuestSessionRecord)
                    .where(GuestSessionRecord.token_hash == token_hash(token))
                    .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                )
        finally:
            await engine.dispose()

    asyncio.run(expire())
    out = call(client, cid, headers)
    assert out.status_code == 401 and not sent and not budget.preflights


@pg
def test_dns_rebinding_and_attempt_budget_denial_before_key_send(probe_api, monkeypatch):
    from app.api import provider_connections

    client, users, _, budget, sent = probe_api
    _, headers = guest(client, users)
    cid = create(client, headers)
    monkeypatch.setattr(provider_connections, "resolve_addresses", lambda *args: ["127.0.0.1"])
    rejected = call(client, cid, headers)
    assert rejected.status_code == 422 and rejected.json()["code"] == "INVALID_TARGET"
    assert not sent and not budget.attempts
    monkeypatch.setattr(provider_connections, "resolve_addresses", lambda *args: ["8.8.8.8"])
    budget.deny_attempt = True
    rejected = call(client, cid, headers)
    assert rejected.status_code == 403 and not sent and len(budget.attempts) == 1


@pg
def test_actual_target_classification_is_fresh_not_saved_dns(probe_api, monkeypatch):
    from app.api import provider_connections

    client, users, _, _, sent = probe_api
    monkeypatch.setenv("EDUMIND_PROVIDER_DEPLOYMENT", "local")
    monkeypatch.setenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", "127.0.0.1:443")
    _, headers = guest(client, users)
    cid = create(client, headers)
    assert client.get(ROOT + "/" + cid).json()["is_local"] is False
    monkeypatch.setattr(provider_connections, "resolve_addresses", lambda *args: ["127.0.0.1"])
    out = call(client, cid, headers)
    assert out.status_code == 200 and out.json()["is_local"] is True
    assert len(sent) == 1 and sent[0].url.host == "127.0.0.1"


@pg
def test_other_live_session_of_same_owner_cannot_probe(probe_api):
    from test_provider_connections_api import DB_URL

    from app.core.auth import csrf_for_token

    client, users, _, budget, sent = probe_api
    original, headers = guest(client, users)
    cid = create(client, headers)
    other = uuid4().hex + uuid4().hex

    async def add_session():
        engine = create_database_engine(DB_URL)
        try:
            async with async_sessionmaker(engine)() as db, db.begin():
                auth = await db.get(GuestSessionRecord, token_hash(original))
                now = datetime.now(timezone.utc)
                db.add(
                    GuestSessionRecord(
                        token_hash=token_hash(other),
                        user_id=auth.user_id,
                        created_at=now,
                        expires_at=now + timedelta(hours=2),
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(add_session())
    restore(client, other)
    assert client.get("/api/auth/session").status_code == 200
    out = call(client, cid, {"X-CSRF-Token": csrf_for_token(other)})
    assert out.status_code == 404 and not budget.preflights and not sent


@pg
def test_missing_master_key_and_deleted_connection_do_not_send(probe_api, monkeypatch):
    client, users, _, budget, sent = probe_api
    _, headers = guest(client, users)
    cid = create(client, headers)
    monkeypatch.delenv("EDUMIND_CREDENTIAL_KEYRING_JSON")
    out = call(client, cid, headers)
    private(out)
    assert out.status_code == 503 and out.json()["code"] == "CONFIGURATION_MISSING"
    assert not sent and len(budget.attempts) == 1
    assert client.delete(ROOT + "/" + cid, headers={**headers, "If-Match": "1"}).status_code == 204
    out = call(client, cid, headers)
    assert out.status_code == 404 and not sent and len(budget.attempts) == 1


@pg
@pytest.mark.parametrize("mutation", ["operation", "model", "purpose"])
def test_temporary_handle_exact_binding(probe_api, mutation):
    client, users, _, budget, sent = probe_api
    _, headers = guest(client, users)
    cid = create(client, headers, mode="temporary")
    secret = upload()
    if mutation == "purpose":
        secret["purpose"] = "model_refresh"
    receipt = client.post(ROOT + "/" + cid + "/temporary-credentials", headers=headers, json=secret)
    assert receipt.status_code == 201
    body = probe(operation_id=secret["operation_id"], temporary_handle=receipt.json()["handle"])
    if mutation == "operation":
        body["operation_id"] = str(uuid4())
    elif mutation == "model":
        body["consent"]["model_id"] = "other-model"
    out = call(client, cid, headers, body)
    private(out)
    assert out.status_code == 503 and not sent and not budget.attempts


@pg
@pytest.mark.parametrize(
    "upstream,status,code",
    [
        (401, 502, "AUTHENTICATION_FAILED"),
        (429, 429, "RATE_LIMITED"),
        (503, 503, "TEMPORARILY_UNAVAILABLE"),
        (200, 502, "INVALID_OUTPUT"),
    ],
)
def test_error_cleaning_and_no_retry(probe_api, caplog, upstream, status, code):
    client, users, _, budget, sent = probe_api
    _, headers = guest(client, users)
    cid = create(client, headers)

    def handler(request):
        sent.append(request)
        return httpx.Response(upstream, text=KEY)

    app.dependency_overrides[api.probe_transport] = lambda: httpx.MockTransport(handler)
    out = call(client, cid, headers)
    private(out)
    assert out.status_code == status and out.json()["code"] == code
    assert out.json()["retryable"] is False
    assert len(sent) == len(budget.attempts) == 1 and KEY not in caplog.text


class WaitingBody(httpx.AsyncByteStream):
    closed = False

    async def __aiter__(self):
        await asyncio.Event().wait()
        yield b"unreachable"

    async def aclose(self):
        self.closed = True


@pg
def test_absolute_deadline_closes_response_and_consumes_temporary_once(probe_api, monkeypatch):
    client, users, _, budget, sent = probe_api
    _, headers = guest(client, users)
    cid = create(client, headers, mode="temporary")
    secret = upload()
    receipt = client.post(ROOT + "/" + cid + "/temporary-credentials", headers=headers, json=secret)
    body = probe(operation_id=secret["operation_id"], temporary_handle=receipt.json()["handle"])
    stream = WaitingBody()

    def handler(request):
        sent.append(request)
        return httpx.Response(200, stream=stream)

    monkeypatch.setattr(service, "PROBE_TIMEOUT_SECONDS", 0.5)
    app.dependency_overrides[api.probe_transport] = lambda: httpx.MockTransport(handler)
    out = call(client, cid, headers, body)
    private(out)
    assert out.status_code == 504 and out.json()["code"] == "TIMEOUT"
    assert stream.closed and len(sent) == len(budget.attempts) == 1
    replay = call(client, cid, headers, body)
    assert replay.status_code == 503 and len(sent) == 1
