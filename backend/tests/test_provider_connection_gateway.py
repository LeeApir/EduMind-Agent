"""Mock HTTP protocol failures and real-PG send/revocation races, no model calls."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.credential_crypto import CredentialFailure, CredentialKeyring
from app.core.database import create_database_engine
from app.core.provider_factory import build_connection_provider_gateway
from app.core.provider_target import TargetPolicy
from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.models.auth import GuestSessionRecord, User
from app.models.provider_connections import ProviderConnection
from app.services.openai_compatible import OpenAICompatibleAdapter
from app.services.provider_connection_dispatch import (
    ConnectionConsent,
    ConnectionOperation,
    ConnectionRoute,
    DispatchRequest,
    ModelCapabilities,
)
from app.services.provider_connections import CredentialIdentity, ProviderConnectionStore
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    TextRequest,
)
from app.services.temporary_credentials import TemporaryCredentialService

KEY = "TEST_ONLY_CONNECTION_GATEWAY_KEY"
PROMPT = TextRequest((ChatMessage("user", "synthetic teaching context"),))
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer"],
    "properties": {"answer": {"type": "integer"}},
}
DB_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pg = pytest.mark.skipif(not DB_URL, reason="dedicated PostgreSQL URL not set")


def request_for(owner=None, cid=None, *, purpose="generation", categories=None):
    owner = owner or CredentialIdentity(uuid4(), uuid4().hex)
    cid = cid or uuid4()
    route = ConnectionRoute(cid, 1, "selected-model", categories or frozenset({"learning_goal"}))
    caps = ModelCapabilities(cid, 1, "selected-model", "declared-test-v1", True, True)
    return DispatchRequest(owner, route, ConnectionConsent(route, True), caps, uuid4(), purpose)


def result(text="ok", **fields):
    raw = {
        "model": "selected-model",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}
        ],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2},
    }
    raw.update(fields)
    return raw


def frame(delta=None, finish=None):
    return (
        "data: "
        + json.dumps(
            {
                "model": "selected-model",
                "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}],
            }
        )
        + "\n\n"
    )


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class Harness(ConnectionOperation):
    """Adapter-only HTTP harness; PG authority is verified separately below."""

    def __init__(self, handler, request=None):
        self.request = request or request_for()
        self.handler = handler
        self.calls = []

    def _check(self):
        pass

    @asynccontextmanager
    async def send(self, body, *, stream=False):
        self.calls.append(body)
        async with httpx.AsyncClient(transport=httpx.MockTransport(self.handler)) as client:
            response = await client.send(
                client.build_request("POST", "https://8.8.8.8/v1/chat/completions", json=body),
                stream=True,
            )
            try:
                yield response
            finally:
                await response.aclose()


def test_chat_text_and_selected_wire_fields():
    async def run():
        harness = Harness(lambda r: httpx.Response(200, json=result()))
        adapter = OpenAICompatibleAdapter(harness)
        response = await adapter.generate_text(PROMPT)
        assert response.text == "ok" and response.model_id == "selected-model"
        assert response.usage.input_tokens == 4 and response.usage.output_tokens == 2
        assert harness.calls == [
            {
                "model": "selected-model",
                "messages": [{"role": "user", "content": "synthetic teaching context"}],
                "max_tokens": 4096,
                "stream": False,
            }
        ]

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["json_schema", "json_object", "text_json"])
def test_selected_structured_mode_is_explicit_and_locally_checked(mode):
    async def run():
        req = request_for()
        req = replace(req, capabilities=replace(req.capabilities, structured_transport=mode))
        h = Harness(lambda r: httpx.Response(200, json=result('{"answer":3}')), req)
        response = await OpenAICompatibleAdapter(h).generate_structured(
            StructuredRequest(PROMPT, SCHEMA)
        )
        assert response.value == {"answer": 3}
        body = h.calls[0]
        if mode == "text_json":
            assert "response_format" not in body and "JSON" in body["messages"][0]["content"]
        else:
            assert body["response_format"]["type"] == mode
        if mode == "json_schema":
            assert body["response_format"]["json_schema"]["schema"] == SCHEMA
            assert body["response_format"]["json_schema"]["strict"] is True

    asyncio.run(run())


@pytest.mark.parametrize(
    "text",
    [
        '{"answer":"wrong"}',
        '{"answer":3,"extra":1}',
        '{"answer":NaN}',
        '{"answer":3,"answer":4}',
        '```json\n{"answer":3}\n```',
        "[]",
        '{"answer":3} trailing',
    ],
)
def test_structured_invalid_json_or_schema_never_published(text):
    async def run():
        h = Harness(lambda r: httpx.Response(200, json=result(text)))
        with pytest.raises(ProviderError) as failure:
            await OpenAICompatibleAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
        assert failure.value.code is ProviderErrorCode.INVALID_OUTPUT and len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "status,code",
    [
        (301, "INVALID_TARGET"),
        (401, "AUTHENTICATION_FAILED"),
        (403, "AUTHENTICATION_FAILED"),
        (429, "RATE_LIMITED"),
        (400, "CAPABILITY_UNAVAILABLE"),
        (503, "TEMPORARILY_UNAVAILABLE"),
        (504, "TIMEOUT"),
    ],
)
def test_safe_statuses_ignore_vendor_secret_body(status, code, caplog):
    async def run():
        h = Harness(
            lambda r: httpx.Response(status, text=KEY, headers={"Location": "http://127.0.0.1/"})
        )
        with pytest.raises(ProviderError) as failure:
            await OpenAICompatibleAdapter(h).generate_text(PROMPT)
        assert failure.value.code.value == code
        assert KEY not in str(failure.value) and KEY not in caplog.text and len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "raw",
    [
        result(""),
        result(choices=[]),
        result(model=""),
        result(usage={"prompt_tokens": True}),
        result(
            choices=[
                {
                    "index": True,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ]
        ),
        result(
            choices=[
                {
                    "index": 0,
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": "partial"},
                }
            ]
        ),
        result(
            choices=[
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok", "tool_calls": [{}]},
                }
            ]
        ),
    ],
)
def test_malformed_or_incomplete_text_is_not_success(raw):
    async def run():
        h = Harness(lambda r: httpx.Response(200, json=raw))
        with pytest.raises(ProviderError):
            await OpenAICompatibleAdapter(h).generate_text(PROMPT)

    asyncio.run(run())


def test_fragmented_stream_ignores_reasoning_and_closes():
    async def run():
        wire = (
            ": ping\n\n"
            + frame({"role": "assistant", "content": ""})
            + frame({"reasoning_content": "do not display"})
            + frame({"content": "数组"})
            + frame({"content": "说明"}, "stop")
            + "data: [DONE]\n\n"
        ).encode()
        stream = Chunks([wire[i : i + 1] for i in range(len(wire))])
        h = Harness(lambda r: httpx.Response(200, stream=stream))
        out = [d.text async for d in OpenAICompatibleAdapter(h).stream_text(PROMPT)]
        assert out == ["数组", "说明"] and stream.closed
        assert h.calls[0]["stream"] is True

    asyncio.run(run())


@pytest.mark.parametrize(
    "wire,code",
    [
        (frame({"content": "partial"}), "TEMPORARILY_UNAVAILABLE"),
        (frame({"content": "partial"}, "length") + "data: [DONE]\n\n", "INVALID_OUTPUT"),
        ("data: [DONE]\n\n", "INVALID_OUTPUT"),
        (frame({"tool_calls": [{}]}, "tool_calls"), "INVALID_OUTPUT"),
        ("data: " + json.dumps({"error": {"message": KEY}}) + "\n\n", "TEMPORARILY_UNAVAILABLE"),
        ("data: invalid\n\n", "INVALID_OUTPUT"),
    ],
)
def test_stream_failures_close_without_replay(wire, code):
    async def run():
        stream = Chunks([wire.encode()])
        h = Harness(lambda r: httpx.Response(200, stream=stream))
        with pytest.raises(ProviderError) as failure:
            _ = [d.text async for d in OpenAICompatibleAdapter(h).stream_text(PROMPT)]
        assert failure.value.code.value == code and KEY not in str(failure.value)
        assert len(h.calls) == 1 and stream.closed

    asyncio.run(run())


@pytest.mark.parametrize("feature", ["streaming", "structured_output"])
@pytest.mark.parametrize("value", [None, False])
def test_unknown_or_unavailable_capability_is_zero_exit(feature, value):
    async def run():
        r = request_for()
        r = replace(r, capabilities=replace(r.capabilities, **{feature: value}))
        h = Harness(lambda req: pytest.fail("unknown capability reached HTTP"), r)
        with pytest.raises(ProviderError) as failure:
            if feature == "streaming":
                _ = [d async for d in OpenAICompatibleAdapter(h).stream_text(PROMPT)]
            else:
                await OpenAICompatibleAdapter(h).generate_structured(
                    StructuredRequest(PROMPT, SCHEMA)
                )
        assert failure.value.code is ProviderErrorCode.CAPABILITY_UNAVAILABLE and not h.calls

    asyncio.run(run())


def test_external_schema_ref_and_response_size_are_bounded():
    async def run():
        h = Harness(lambda r: pytest.fail("external ref reached HTTP"))
        with pytest.raises(ProviderError):
            await OpenAICompatibleAdapter(h).generate_structured(
                StructuredRequest(PROMPT, {"$ref": "https://example.invalid/schema"})
            )
        assert not h.calls
        stream = Chunks([b"x" * (2 * 1024 * 1024 + 1)])
        h = Harness(lambda r: httpx.Response(200, stream=stream))
        with pytest.raises(ProviderError):
            await OpenAICompatibleAdapter(h).generate_text(PROMPT)
        assert stream.closed

    asyncio.run(run())


@asynccontextmanager
async def pg_context(
    mode="persistent",
    *,
    expires=None,
    policy=None,
    base_url=None,
    resolver=None,
    provider_type="openai-compatible",
):
    engine = create_database_engine(DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as db, db.begin():
        user = User(id=uuid4(), is_guest=True)
        db.add(user)
        await db.flush()
        session_hash = uuid4().hex + uuid4().hex
        db.add(
            GuestSessionRecord(
                token_hash=session_hash,
                user_id=user.id,
                created_at=now,
                expires_at=expires or now + timedelta(hours=2),
            )
        )
    owner = CredentialIdentity(user.id, session_hash)
    store = ProviderConnectionStore(
        factory,
        CredentialKeyring("test", {"test": b"k" * 32}),
        policy=policy,
        resolver=resolver or (lambda host, port: ["8.8.8.8"]),
    )
    view = await store.create(
        owner,
        provider_type=provider_type,
        display_name="synthetic",
        base_url=base_url or "https://chosen.test/v1",
        mode=mode,
        secret={"api_key": KEY} if mode == "persistent" else None,
    )
    try:
        yield store, owner, UUID(str(view["id"]))
    finally:
        async with factory() as db, db.begin():
            await db.execute(
                delete(ProviderConnection).where(ProviderConnection.user_id == user.id)
            )
            await db.execute(
                delete(GuestSessionRecord).where(GuestSessionRecord.user_id == user.id)
            )
            await db.execute(delete(User).where(User.id == user.id))
        await engine.dispose()


async def allowed(request):
    pass


@pg
def test_pg_routing_retry_revalidates_same_target_and_default_is_untouched(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context() as (store, owner, cid):
            grants = []
            sent = []

            async def grant(r):
                grants.append(r.route)

            async def respond(wire):
                assert wire.url.host == "8.8.8.8" and wire.url.path == "/v1/chat/completions"
                assert wire.headers["Host"] == "chosen.test"
                assert wire.extensions["sni_hostname"] == "chosen.test"
                assert wire.headers["Authorization"] == "Bearer " + KEY
                assert json.loads(wire.content)["model"] == "selected-model"
                sent.append(wire)
                await wire.extensions["trace"]("http11.send_request_headers.started", {})
                await wire.extensions["trace"]("http11.send_request_body.started", {})
                await wire.extensions["trace"]("http11.send_request_body.complete", {})
                return httpx.Response(503 if len(sent) < 3 else 200, json=result())

            async with build_connection_provider_gateway(
                store, request_for(owner, cid), grant, transport=httpx.MockTransport(respond)
            ) as gateway:
                out = await gateway.generate_text(PROMPT, retry_safe=True)
                assert out.text == "ok"
            assert len(sent) == len(grants) == 3 and len(set(grants)) == 1
            assert all("Authorization" not in w.headers for w in sent)

    asyncio.run(run())


@pg
@pytest.mark.parametrize(
    "invalid", ["other-owner", "version", "consent", "model", "budget", "catalog"]
)
def test_pg_invalid_authority_denies_all_http(invalid, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context() as (store, owner, cid):
            r = request_for(owner, cid)
            if invalid == "other-owner":
                r = replace(r, identity=CredentialIdentity(uuid4(), owner.session_hash))
            if invalid == "version":
                route = replace(r.route, config_version=2)
                r = replace(
                    r,
                    route=route,
                    consent=ConnectionConsent(route, True),
                    capabilities=replace(r.capabilities, config_version=2),
                )
            if invalid == "consent":
                r = replace(r, consent=ConnectionConsent(r.route, False))
            if invalid == "model":
                r = replace(r, capabilities=replace(r.capabilities, model_id="other"))
            if invalid == "catalog":
                monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")

            async def grant(req):
                if invalid == "budget":
                    raise CredentialFailure("BUDGET_NOT_AUTHORIZED")

            with pytest.raises((CredentialFailure, ProviderError)):
                async with build_connection_provider_gateway(
                    store,
                    r,
                    grant,
                    transport=httpx.MockTransport(
                        lambda w: pytest.fail("invalid authority reached HTTP")
                    ),
                ) as gateway:
                    await gateway.generate_text(PROMPT)

    asyncio.run(run())


@pg
def test_pg_send_lock_covers_real_send_trace_and_observer_is_not_self_blocked(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context() as (store, owner, cid):
            writer = ProviderConnectionStore(store.factory, store.keyring, resolver=store.resolver)
            deleting = None
            proof = []

            async def respond(wire):
                nonlocal deleting
                trace = wire.extensions["trace"]
                await trace("http11.send_request_headers.started", {})
                # Simulate connect/send taking > observer's 1s check interval.
                deleting = asyncio.create_task(writer.delete(owner, cid, 1))
                await asyncio.sleep(1.1)
                assert not deleting.done(), "delete committed before actual auth/data send"
                proof.append("blocked")
                await trace("http11.send_request_headers.complete", {})
                await trace("http11.send_request_body.started", {})
                await trace("http11.send_request_body.complete", {})
                await asyncio.sleep(0.1)
                return httpx.Response(200, json=result())

            with pytest.raises(CredentialFailure):
                async with build_connection_provider_gateway(
                    store, request_for(owner, cid), allowed, transport=httpx.MockTransport(respond)
                ) as gateway:
                    await gateway.generate_text(PROMPT)
            assert proof == ["blocked"] and deleting is not None
            await deleting
            with pytest.raises(CredentialFailure) as missing:
                await writer.read(owner, cid)
            assert missing.value.code == "NOT_FOUND"
            async with writer.factory() as db:
                row = await db.get(ProviderConnection, cid)
                assert row.deleted and row.encrypted_api_key is None

    asyncio.run(run())


@pg
@pytest.mark.parametrize("event", ["remote-revoke", "check-timeout", "deadline"])
def test_pg_active_operation_cancel_deadline_and_remote_revoke_close_http(event, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context() as (store, owner, cid):
            entered = asyncio.Event()
            closed = asyncio.Event()
            when = []

            class Waiting(httpx.AsyncByteStream):
                async def __aiter__(self):
                    entered.set()
                    await asyncio.sleep(20)
                    yield b"never"

                async def aclose(self):
                    closed.set()

            async def respond(wire):
                await wire.extensions["trace"]("http11.send_request_body.complete", {})
                return httpx.Response(200, stream=Waiting())

            if event == "deadline":
                import app.services.provider_connection_dispatch as dispatch

                monkeypatch.setattr(dispatch, "OPERATION_SECONDS", 0.1)

            async def op():
                try:
                    async with build_connection_provider_gateway(
                        store,
                        request_for(owner, cid),
                        allowed,
                        transport=httpx.MockTransport(respond),
                    ) as gateway:
                        await gateway.generate_text(PROMPT)
                except (CredentialFailure, ProviderError) as e:
                    when.append((asyncio.get_running_loop().time(), e.code))

            task = asyncio.create_task(op())
            await asyncio.wait_for(entered.wait(), 3)
            start = asyncio.get_running_loop().time()
            if event == "remote-revoke":
                # Direct committed change represents a different API process, no local hint.
                async with store.factory() as db, db.begin():
                    await db.execute(
                        update(ProviderConnection)
                        .where(ProviderConnection.id == cid)
                        .values(enabled=False, config_version=2)
                    )
                start = asyncio.get_running_loop().time()
            elif event == "check-timeout":

                async def stuck(*args):
                    await asyncio.sleep(20)
                    return True

                monkeypatch.setattr(store, "valid_version", stuck)
            await asyncio.wait_for(task, 3)
            assert when and when[0][0] - start <= 2.0 and closed.is_set()
            assert when[0][1] == (
                ProviderErrorCode.TIMEOUT if event == "deadline" else "CREDENTIAL_UNAVAILABLE"
            )

    asyncio.run(run())


@pg
@pytest.mark.parametrize("terminal", ["success", "failure", "cancel"])
def test_pg_temporary_single_operation_never_persisted_and_wiped(terminal, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context("temporary") as (store, owner, cid):
            registry = TemporaryCredentialRegistry()
            service = TemporaryCredentialService(store, registry)
            r = request_for(owner, cid)
            handle, _ = await service.register(
                owner, cid, 1, r.operation_id, r.purpose, r.route.model_id, {"api_key": KEY}
            )
            r = replace(r, temporary_handle=handle)
            captured = registry._entries[handle]
            sent = []

            async def respond(wire):
                assert wire.headers["Authorization"] == "Bearer " + KEY
                sent.append(wire)
                await wire.extensions["trace"]("http11.send_request_body.complete", {})
                if terminal == "cancel":
                    raise asyncio.CancelledError
                return httpx.Response(401 if terminal == "failure" else 200, json=result())

            try:

                async def op():
                    async with build_connection_provider_gateway(
                        store, r, allowed, registry=registry, transport=httpx.MockTransport(respond)
                    ) as gateway:
                        return await gateway.generate_text(PROMPT)

                if terminal == "success":
                    assert (await op()).text == "ok"
                else:
                    with pytest.raises(
                        asyncio.CancelledError if terminal == "cancel" else ProviderError
                    ):
                        await op()
                assert not registry._entries and captured.payload == bytearray() and len(sent) == 1
                with pytest.raises(CredentialFailure):
                    await op()
                async with store.factory() as db:
                    row = await db.get(ProviderConnection, cid)
                    assert row.encrypted_api_key is None and row.credential_key_id is None
            finally:
                await registry.close()

    asyncio.run(run())


@pg
def test_pg_keyless_connection_never_borrows_system_key(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "UNRELATED_TEST_SYSTEM_KEY")

    async def run():
        async with pg_context("none") as (store, owner, cid):
            sent = []

            def respond(wire):
                assert "Authorization" not in wire.headers
                assert b"UNRELATED_TEST_SYSTEM_KEY" not in wire.content
                sent.append(wire)
                return httpx.Response(200, json=result())

            async with build_connection_provider_gateway(
                store, request_for(owner, cid), allowed, transport=httpx.MockTransport(respond)
            ) as gateway:
                assert (await gateway.generate_text(PROMPT)).text == "ok"
            assert len(sent) == 1

    asyncio.run(run())


@pg
def test_pg_dns_changes_fail_before_second_budget_or_http(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context() as (store, owner, cid):
            grants = []
            sent = []

            async def grant(req):
                grants.append(req.operation_id)

            def respond(wire):
                sent.append(wire)
                store.resolver = lambda host, port: ["127.0.0.1"]
                return httpx.Response(503, text=KEY)

            async with build_connection_provider_gateway(
                store, request_for(owner, cid), grant, transport=httpx.MockTransport(respond)
            ) as gateway:
                with pytest.raises(ProviderError) as failure:
                    await gateway.generate_text(PROMPT, retry_safe=True)
            assert failure.value.code is ProviderErrorCode.INVALID_TARGET
            assert len(sent) == len(grants) == 1
            assert "Authorization" not in sent[0].headers

    asyncio.run(run())


@pg
def test_pg_stream_consumer_close_and_different_task_deny(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context() as (store, owner, cid):
            stream = Chunks(
                [(frame({"content": "first"}) + frame(finish="stop") + "data: [DONE]\n\n").encode()]
            )
            sent = []

            async def respond(wire):
                sent.append(wire)
                await wire.extensions["trace"]("http11.send_request_body.complete", {})
                return httpx.Response(200, stream=stream)

            async with build_connection_provider_gateway(
                store, request_for(owner, cid), allowed, transport=httpx.MockTransport(respond)
            ) as gateway:
                with pytest.raises(CredentialFailure):
                    await asyncio.create_task(gateway.generate_text(PROMPT))
                assert not sent
                output = gateway.stream_text(PROMPT)
                assert (await anext(output)).text == "first"
                await output.aclose()
            assert stream.closed and len(sent) == 1
            assert "Authorization" not in sent[0].headers

    asyncio.run(run())


@pg
def test_pg_actual_httpx_body_trace_releases_lock_before_response(monkeypatch):
    """Real loopback HTTPX/httpcore traffic with synthetic data, no Provider service."""
    from sqlalchemy import select

    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        proof = []
        failures = []
        store = None
        cid = None
        finished = asyncio.Event()

        async def serve(reader, writer):
            try:
                header = await reader.readuntil(b"\r\n\r\n")
                headers = {
                    line.split(b":", 1)[0].lower(): line.split(b":", 1)[1].strip()
                    for line in header.split(b"\r\n")[1:]
                    if b":" in line
                }
                assert headers[b"authorization"] == b"Bearer " + KEY.encode()
                length = next(
                    int(line.split(b":", 1)[1])
                    for line in header.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
                assert json.loads(await reader.readexactly(length))["model"] == "selected-model"
                # Wait until the actual httpcore body-complete callback can commit.
                async with store.factory() as db, db.begin():
                    await asyncio.wait_for(
                        db.scalar(
                            select(ProviderConnection)
                            .where(ProviderConnection.id == cid)
                            .with_for_update()
                        ),
                        1,
                    )
                    proof.append("unlocked_before_response")
                body = json.dumps(result()).encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    + b"Content-Length: "
                    + str(len(body)).encode()
                    + b"\r\nConnection: close\r\n\r\n"
                    + body
                )
                await writer.drain()
            except Exception as error:
                failures.append(type(error).__name__)
            finally:
                writer.close()
                await writer.wait_closed()
                finished.set()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            async with pg_context(
                policy=TargetPolicy("local", frozenset({("127.0.0.1", port)})),
                base_url=f"http://127.0.0.1:{port}/v1",
                resolver=lambda host, port: ["127.0.0.1"],
            ) as context:
                store, owner, cid = context
                async with build_connection_provider_gateway(
                    store, request_for(owner, cid), allowed
                ) as gateway:
                    assert (await gateway.generate_text(PROMPT)).text == "ok"
                await asyncio.wait_for(finished.wait(), 1)
                assert proof == ["unlocked_before_response"] and not failures
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(run())
