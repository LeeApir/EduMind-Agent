"""No background calls; bounded Mock list refresh, real version-bound PG snapshots."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_provider_connection_test_api import (
    WaitingBody,
    create,
    probe,
    probe_api,  # noqa: F401 -- shared fixture chain
)
from test_provider_connections_api import (
    DB_URL,
    KEY,
    ROOT,
    guest,
    pg,
    private,
    restore,
    schema,
    setup_api,  # noqa: F401 -- transitive pytest fixture
    upload,  # noqa: F401
)

from app.api import provider_model_catalog as api
from app.core.auth import token_hash
from app.core.credential_crypto import CredentialFailure
from app.core.database import create_database_engine
from app.core.provider_factory import build_connection_provider_gateway
from app.main import app
from app.models.provider_model_snapshots import ProviderModelSnapshot
from app.services import provider_model_catalog as service
from app.services.provider_connection_dispatch import (
    ConnectionConsent,
    ConnectionRoute,
    DispatchRequest,
)
from app.services.provider_connections import CredentialIdentity, ProviderConnectionStore
from app.services.provider_gateway import ChatMessage, ProviderError, ProviderErrorCode, TextRequest


def list_body(*models):
    return {"object": "list", "data": [{"id": model, "object": "model"} for model in models]}


@pytest.fixture
def catalog_api(probe_api):  # noqa: F811 -- imported fixture
    client, users, dns, budget, sent = probe_api

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=list_body("private-model"))

    app.dependency_overrides[api.model_refresh_budget] = lambda: budget
    app.dependency_overrides[api.model_refresh_transport] = lambda: httpx.MockTransport(handler)
    yield client, users, dns, budget, sent


def refresh(client, cid, headers, body=None):
    return client.post(ROOT + "/" + cid + "/models/refresh", json=body or probe(), headers=headers)


def cached(client, cid):
    return client.get(ROOT + "/" + cid + "/models")


@pytest.mark.parametrize("provider_type", ["openai-compatible", "ollama"])
def test_metadata_explicit_declarations_not_names(provider_type):
    field = "name" if provider_type == "ollama" else "id"
    key = "models" if provider_type == "ollama" else "data"
    parsed = service.model_metadata(
        {
            key: [
                {field: "super-vision-tools-json-model", "secret": KEY, "capabilities": ["vision"]},
                {
                    field: "declared",
                    "edumind_capabilities": {
                        "streaming": True,
                        "structured_output": False,
                        "vision": None,
                    },
                },
            ]
        },
        provider_type,
    )
    assert parsed[0]["capabilities"]["source"] == "unknown"
    assert all(parsed[0]["capabilities"][flag] is None for flag in service.FLAGS)
    assert parsed[1]["capabilities"]["source"] == "declared"
    assert parsed[1]["capabilities"]["streaming"] is True
    assert parsed[1]["capabilities"]["structured_output"] is False
    assert (
        KEY not in json.dumps(parsed)
        and parsed[0]["capabilities"]["version"] == service.CAPABILITY_VERSION
    )


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"data": {}},
        {"data": [None]},
        {"data": [{"id": ""}]},
        {"data": [{"id": "a\n"}]},
        {"data": [{"id": "x" * 161}]},
        {"data": [{"id": "same"}, {"id": "same"}]},
        {"data": [{"id": "m", "edumind_capabilities": {"streaming": 1}}]},
        {"data": [{"id": "m", "edumind_capabilities": {"source": "verified"}}]},
        {"data": [{"id": "m"}] * 1001},
    ],
)
def test_reject_malformed_or_unbounded_metadata(body):
    with pytest.raises(ProviderError) as error:
        service.model_metadata(body, "openai-compatible")
    assert error.value.code is ProviderErrorCode.INVALID_OUTPUT


def test_maximum_and_empty_are_explicit_bounded_snapshots():
    assert service.model_metadata(list_body(), "openai-compatible") == []
    assert (
        len(service.model_metadata(list_body(*(str(i) for i in range(1000))), "openai-compatible"))
        == 1000
    )


@pg
def test_static_catalog_and_empty_get_are_network_and_key_free(catalog_api, monkeypatch):
    client, users, dns, budget, sent = catalog_api
    assert client.get("/api/providers/catalog").status_code == 401
    _, headers = guest(client, users)
    cid = create(client, headers)
    before = len(dns)
    monkeypatch.delenv("EDUMIND_CREDENTIAL_KEYRING_JSON")
    types = client.get("/api/providers/catalog")
    private(types)
    assert types.json() == {
        "types": ["anthropic", "gemini", "ollama", "openai-compatible", "spark"]
    }
    out = cached(client, cid)
    private(out)
    schema("ProviderModelList").validate(out.json())
    assert out.json() == {
        "connection_id": cid,
        "config_version": 1,
        "models": [],
        "refreshed_at": None,
    }
    assert not sent and not budget.preflights and len(dns) == before
    assert client.get("/api/runtime").json() == {"mode": "catalog_only"}


@pg
def test_explicit_once_get_sanitizes_persists_restart_and_version(catalog_api, caplog):
    client, users, _, budget, sent = catalog_api
    token, headers = guest(client, users)
    cid = create(client, headers)
    out = refresh(client, cid, headers)
    private(out)
    assert out.status_code == 200, out.text
    schema("ProviderModelList").validate(out.json())
    assert len(sent) == len(budget.attempts) == 1
    assert sent[0].method == "GET" and sent[0].url.path == "/v1/models" and sent[0].content == b""
    assert "authorization" not in sent[0].headers
    assert budget.attempts[0].purpose == "model_refresh"
    assert "may contact" in out.headers["x-provider-probe-notice"]
    assert cached(client, cid).json() == out.json() and len(sent) == 1
    with TestClient(app, base_url="https://testserver") as restarted:
        restore(restarted, token)
        assert cached(restarted, cid).json() == out.json()
    assert KEY not in caplog.text
    assert (
        client.patch(
            ROOT + "/" + cid, headers={**headers, "If-Match": "1"}, json={"display_name": "new"}
        ).status_code
        == 200
    )
    assert cached(client, cid).json() == {
        "connection_id": cid,
        "config_version": 2,
        "models": [],
        "refreshed_at": None,
    }
    stale = refresh(client, cid, headers)
    assert stale.status_code == 409 and len(sent) == 1


@pg
@pytest.mark.parametrize(
    "mutation",
    ["budget", "owner", "csrf", "categories", "consent", "missing", "disabled", "unsupported"],
)
def test_rejection_before_outbound(catalog_api, mutation):
    client, users, _, budget, sent = catalog_api
    _, headers = guest(client, users)
    cid = create(
        client,
        headers,
        enabled=mutation != "disabled",
        provider_type="anthropic" if mutation == "unsupported" else "openai-compatible",
    )
    body = probe()
    expected = 409
    if mutation == "budget":
        app.dependency_overrides.pop(api.model_refresh_budget)
        expected = 403
    elif mutation == "owner":
        _, headers = guest(client, users)
        assert cached(client, cid).status_code == 404
        expected = 404
    elif mutation == "csrf":
        headers = {}
        expected = 403
    elif mutation == "categories":
        body["consent"]["data_categories"] = ["learning_goal"]
    elif mutation == "consent":
        body["consent"]["accepted"] = False
    elif mutation == "missing":
        assert (
            client.patch(
                ROOT + "/" + cid, headers={**headers, "If-Match": "1"}, json={"secret": None}
            ).status_code
            == 200
        )
        body["consent"]["config_version"] = 2
        expected = 503
    elif mutation == "disabled":
        expected = 503
    elif mutation == "unsupported":
        expected = 422
    out = refresh(client, cid, headers, body)
    private(out)
    assert out.status_code == expected, out.text
    assert not sent and not budget.attempts


@pg
@pytest.mark.parametrize(
    "failure",
    ["rate", "upstream", "invalid", "secret_echo", "large", "too_many", "redirect", "timeout"],
)
def test_failure_preserves_old_snapshot_without_retry(catalog_api, monkeypatch, failure, caplog):
    client, users, _, budget, sent = catalog_api
    _, headers = guest(client, users)
    cid = create(client, headers)
    old = refresh(client, cid, headers)
    assert old.status_code == 200
    stream = WaitingBody()

    def handler(request):
        sent.append(request)
        if failure == "rate":
            return httpx.Response(429, text=KEY)
        if failure == "upstream":
            return httpx.Response(503, text=KEY)
        if failure == "invalid":
            return httpx.Response(200, text='{"data": [], "data": []}')
        if failure == "secret_echo":
            return httpx.Response(200, json=list_body("prefix" + KEY))
        if failure == "large":
            return httpx.Response(200, content=b" " * (service.MAX_LIST_BYTES + 1))
        if failure == "too_many":
            return httpx.Response(200, json=list_body(*(str(i) for i in range(1001))))
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://foreign.test/"})
        return httpx.Response(200, stream=stream)

    app.dependency_overrides[api.model_refresh_transport] = lambda: httpx.MockTransport(handler)
    if failure == "timeout":
        monkeypatch.setattr(service, "REFRESH_TIMEOUT_SECONDS", 0.5)
    out = refresh(client, cid, headers)
    private(out)
    assert out.status_code == {"rate": 429, "upstream": 503, "redirect": 422, "timeout": 504}.get(
        failure, 502
    ), out.text
    assert len(sent) == len(budget.attempts) == 2
    assert cached(client, cid).json() == old.json() and KEY not in caplog.text
    if failure == "timeout":
        assert stream.closed


@pg
def test_ollama_temporary_refresh_and_no_download(catalog_api, monkeypatch):
    client, users, _, budget, sent = catalog_api
    monkeypatch.setenv("EDUMIND_PROVIDER_DEPLOYMENT", "local")
    monkeypatch.setenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", "127.0.0.1:11434")
    _, headers = guest(client, users)
    cid = create(
        client, headers, mode="temporary", provider_type="ollama", base_url="http://127.0.0.1:11434"
    )
    secret = upload(purpose="model_refresh")
    receipt = client.post(ROOT + "/" + cid + "/temporary-credentials", headers=headers, json=secret)
    assert receipt.status_code == 201
    body = probe(operation_id=secret["operation_id"], temporary_handle=receipt.json()["handle"])

    def handler(request):
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "local-model:tag",
                        "model": "local-model:tag",
                        "digest": KEY,
                        "details": {"family": "llama"},
                    }
                ]
            },
        )

    app.dependency_overrides[api.model_refresh_transport] = lambda: httpx.MockTransport(handler)
    app.dependency_overrides.pop(api.model_refresh_budget)
    assert refresh(client, cid, headers, body).status_code == 403
    app.dependency_overrides[api.model_refresh_budget] = lambda: budget
    out = refresh(client, cid, headers, body)
    private(out)
    assert out.status_code == 200 and out.json()["models"][0]["id"] == "local-model:tag"
    assert out.json()["models"][0]["capabilities"]["source"] == "unknown"
    assert len(sent) == 1 and sent[0].url.path == "/api/tags" and sent[0].method == "GET"
    assert refresh(client, cid, headers, body).status_code == 503 and len(sent) == 1


@pg
def test_cached_capability_resolution_unknown_rejects_before_network(catalog_api, monkeypatch):
    client, users, _, _, sent = catalog_api
    token, headers = guest(client, users)
    cid = create(client, headers)
    assert refresh(client, cid, headers).status_code == 200
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def check():
        engine = create_database_engine(DB_URL)
        try:
            store = ProviderConnectionStore(async_sessionmaker(engine), None)
            identity = CredentialIdentity(next(iter(users)), token_hash(token))
            route = ConnectionRoute(UUID(cid), 1, "private-model", frozenset({"learning_goal"}))
            caps = await service.resolve_capabilities(store, identity, route)
            assert caps.streaming is None and caps.structured_output is None
            request = DispatchRequest(
                identity, route, ConnectionConsent(route, True), caps, uuid4()
            )

            async def forbid(request):
                pytest.fail("unknown streaming capability reached send/budget")

            async with build_connection_provider_gateway(store, request, forbid) as gateway:
                with pytest.raises(ProviderError) as e:
                    async for _ in gateway.stream_text(
                        TextRequest((ChatMessage("user", "synthetic"),))
                    ):
                        pytest.fail("unknown streaming produced output")
                assert e.value.code is ProviderErrorCode.CAPABILITY_UNAVAILABLE
            missing = ConnectionRoute(UUID(cid), 1, "missing-model", route.data_categories)
            with pytest.raises(ProviderError):
                await service.resolve_capabilities(store, identity, missing)
        finally:
            await engine.dispose()

    asyncio.run(check())
    assert len(sent) == 1


@pg
def test_explicit_declared_capabilities_bind_owned_version(catalog_api):
    client, users, _, _, sent = catalog_api
    token, headers = guest(client, users)
    cid = create(client, headers)

    def handler(request):
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "declared",
                        "edumind_capabilities": {"streaming": True, "structured_output": False},
                    }
                ]
            },
        )

    app.dependency_overrides[api.model_refresh_transport] = lambda: httpx.MockTransport(handler)
    out = refresh(client, cid, headers)
    assert (
        out.status_code == 200 and out.json()["models"][0]["capabilities"]["source"] == "declared"
    )

    async def check():
        engine = create_database_engine(DB_URL)
        try:
            store = ProviderConnectionStore(async_sessionmaker(engine), None)
            owner = CredentialIdentity(next(iter(users)), token_hash(token))
            route = ConnectionRoute(UUID(cid), 1, "declared", frozenset({"learning_goal"}))
            caps = await service.resolve_capabilities(store, owner, route)
            assert caps.streaming is True and caps.structured_output is False
            assert caps.version == service.CAPABILITY_VERSION and caps.connection_id == UUID(cid)
            with pytest.raises(CredentialFailure):
                await service.resolve_capabilities(
                    store, CredentialIdentity(uuid4(), token_hash(token)), route
                )
            with pytest.raises(CredentialFailure) as e:
                await service.resolve_capabilities(
                    store, owner, ConnectionRoute(UUID(cid), 2, "declared", route.data_categories)
                )
            assert e.value.code == "VERSION_CONFLICT"
        finally:
            await engine.dispose()

    asyncio.run(check())
    assert len(sent) == 1


@pg
def test_dns_change_rejected_before_list_authorization(catalog_api, monkeypatch):
    from app.api import provider_connections

    client, users, _, budget, sent = catalog_api
    _, headers = guest(client, users)
    cid = create(client, headers)
    monkeypatch.setattr(
        provider_connections, "resolve_addresses", lambda *args: ["169.254.169.254"]
    )
    out = refresh(client, cid, headers)
    private(out)
    assert out.status_code == 422 and out.json()["code"] == "INVALID_TARGET"
    assert not sent and not budget.attempts and cached(client, cid).json()["refreshed_at"] is None


@pg
def test_config_change_during_fetch_cannot_publish_new_snapshot(catalog_api):
    client, users, _, _, sent = catalog_api
    _, headers = guest(client, users)
    cid = create(client, headers)
    assert refresh(client, cid, headers).status_code == 200
    started, proceed = Event(), Event()

    class PausedBody(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            started.set()
            await asyncio.to_thread(proceed.wait, 3)
            yield json.dumps(list_body("new-model")).encode()

        async def aclose(self):
            self.closed = True

    stream = PausedBody()

    def handler(request):
        sent.append(request)
        return httpx.Response(200, stream=stream)

    app.dependency_overrides[api.model_refresh_transport] = lambda: httpx.MockTransport(handler)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(refresh, client, cid, headers)
        assert started.wait(3)
        try:
            changed = client.patch(
                ROOT + "/" + cid,
                headers={**headers, "If-Match": "1"},
                json={"display_name": "changed"},
            )
            assert changed.status_code == 200
        finally:
            proceed.set()
        out = future.result(timeout=5)
    assert out.status_code in {409, 503}, out.text
    assert stream.closed and cached(client, cid).json()["models"] == []

    async def check():
        engine = create_database_engine(DB_URL)
        try:
            async with async_sessionmaker(engine)() as db:
                snapshot = await db.get(ProviderModelSnapshot, UUID(cid))
                assert snapshot.config_version == 1 and snapshot.models[0]["id"] == "private-model"
        finally:
            await engine.dispose()

    asyncio.run(check())
