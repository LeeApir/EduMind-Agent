"""Native Anthropic protocol and PG authority contracts; all upstreams are Mock."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from test_provider_connection_gateway import (
    KEY,
    PROMPT,
    SCHEMA,
    Chunks,
    Harness,
    allowed,
    pg,
    pg_context,
    request_for,
)

from app.core.credential_crypto import CredentialFailure
from app.core.provider_factory import build_connection_provider_gateway
from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.services.anthropic import TOOL_NAME, AnthropicAdapter
from app.services.ollama import OllamaAdapter
from app.services.openai_compatible import OpenAICompatibleAdapter
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    TextRequest,
)
from app.services.provider_model_catalog import (
    cached_models,
    model_metadata,
    refresh_models,
    resolve_capabilities,
)
from app.services.provider_probe import probe_connection as run_probe
from app.services.temporary_credentials import TemporaryCredentialService


class NativeHarness(Harness):
    def check_public_metadata(self, value):
        if KEY in value:
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)


def result(text="ok", **fields):
    value = {
        "id": "msg_mock",
        "type": "message",
        "role": "assistant",
        "model": "selected-model",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 4, "output_tokens": 2},
    }
    value.update(fields)
    return value


def event(kind, **fields):
    return (
        f"event: {kind}\ndata: " + json.dumps({"type": kind, **fields}, ensure_ascii=False) + "\n\n"
    ).encode()


def events(text="可见"):
    return [
        event("message_start", message=result(content=[], stop_reason=None)),
        event("content_block_start", index=0, content_block={"type": "text", "text": ""}),
        event("content_block_delta", index=0, delta={"type": "text_delta", "text": text}),
        event("content_block_stop", index=0),
        event(
            "message_delta",
            delta={"stop_reason": "end_turn", "stop_sequence": None},
            usage={"output_tokens": 2},
        ),
        event("message_stop"),
    ]


def test_native_message_system_model_limit_usage_and_no_default_sampling():
    async def run():
        raw = result(
            content=[
                {"type": "thinking", "thinking": "hidden"},
                {"type": "text", "text": "visible"},
            ]
        )
        h = NativeHarness(lambda wire: httpx.Response(200, json=raw))
        request = TextRequest(
            (
                ChatMessage("system", "first"),
                ChatMessage("system", "second"),
                ChatMessage("user", "question"),
            ),
            max_output_tokens=27,
        )
        out = await AnthropicAdapter(h).generate_text(request)
        assert out.text == "visible" and out.model_id == "selected-model"
        assert out.usage.input_tokens == 4 and out.usage.output_tokens == 2
        assert h.calls == [
            {
                "model": "selected-model",
                "messages": [{"role": "user", "content": "question"}],
                "system": [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}],
                "max_tokens": 27,
                "stream": False,
            }
        ]
        assert "hidden" not in repr(out) and KEY not in repr(AnthropicAdapter(h))

    asyncio.run(run())


@pytest.mark.parametrize(
    "counts, expected", [(None, None), ({}, None), ({"output_tokens": 2}, (None, 2))]
)
def test_missing_usage_stays_unknown(counts, expected):
    async def run():
        out = await AnthropicAdapter(
            NativeHarness(lambda wire: httpx.Response(200, json=result(usage=counts)))
        ).generate_text(PROMPT)
        assert (
            out.usage is None
            if expected is None
            else (out.usage.input_tokens, out.usage.output_tokens) == expected
        )

    asyncio.run(run())


@pytest.mark.parametrize(
    "fields",
    [
        {"type": "other"},
        {"role": "user"},
        {"model": ""},
        {"stop_reason": "max_tokens"},
        {"stop_reason": "refusal"},
        {"stop_reason": "pause_turn"},
        {"stop_sequence": "unexpected"},
        {"content": []},
        {"content": [{"type": "text", "text": " "}]},
        {"content": [{"type": "tool_use", "name": "unapproved", "input": {}}]},
        {"usage": {"input_tokens": True}},
        {"usage": {"output_tokens": -1}},
        {"model": KEY},
        {"content": [{"type": "text", "text": KEY}]},
    ],
)
def test_invalid_or_secret_output_is_not_returned(fields):
    async def run():
        h = NativeHarness(lambda wire: httpx.Response(200, json=result(**fields)))
        with pytest.raises(ProviderError) as failure:
            await AnthropicAdapter(h).generate_text(PROMPT)
        assert failure.value.code is ProviderErrorCode.INVALID_OUTPUT and len(h.calls) == 1
        assert KEY not in str(failure.value)

    asyncio.run(run())


@pytest.mark.parametrize(
    "prompt_variant",
    [
        TextRequest(
            (ChatMessage("user", "a"), ChatMessage("system", "later"), ChatMessage("user", "b"))
        ),
        TextRequest((ChatMessage("assistant", "prefill"),)),
        TextRequest((ChatMessage("system", "only"),)),
        TextRequest(PROMPT.messages, temperature=1.5),
        TextRequest(PROMPT.messages, max_output_tokens=0),
    ],
)
def test_unsupported_input_fails_without_sending(prompt_variant):
    async def run():
        h = NativeHarness(lambda wire: httpx.Response(200, json=result()))
        with pytest.raises(ProviderError):
            await AnthropicAdapter(h).generate_text(prompt_variant)
        assert not h.calls

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["json_schema", "text_json", "tool_schema"])
def test_explicit_structured_wire_and_fixed_tool_are_locally_validated(mode):
    async def run():
        request = request_for()
        request = replace(
            request,
            capabilities=replace(
                request.capabilities, structured_transport=mode, tool_calling=True
            ),
        )
        raw = (
            result('{"answer":3}')
            if mode != "tool_schema"
            else result(
                content=[
                    {
                        "type": "tool_use",
                        "id": "tool_mock",
                        "name": TOOL_NAME,
                        "input": {"answer": 3},
                    }
                ],
                stop_reason="tool_use",
            )
        )
        h = NativeHarness(lambda wire: httpx.Response(200, json=raw), request)
        out = await AnthropicAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
        assert out.value == {"answer": 3} and len(h.calls) == 1
        body = h.calls[0]
        if mode == "json_schema":
            assert body["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
            assert "tools" not in body
        elif mode == "tool_schema":
            assert body["tools"] == [{"name": TOOL_NAME, "strict": True, "input_schema": SCHEMA}]
            assert body["tool_choice"] == {
                "type": "tool",
                "name": TOOL_NAME,
                "disable_parallel_tool_use": True,
            }
            assert "output_config" not in body
        else:
            assert "schema" in body["system"][-1]["text"] and "output_config" not in body

    asyncio.run(run())


@pytest.mark.parametrize(
    "text",
    [
        '{"answer":"wrong"}',
        '{"answer":1,"extra":1}',
        '{"answer":NaN}',
        '{"answer":1,"answer":2}',
        '```json\n{"answer":1}\n```',
        "[]",
    ],
)
def test_structured_invalid_json_or_schema_does_not_publish(text):
    async def run():
        h = NativeHarness(lambda wire: httpx.Response(200, json=result(text)))
        with pytest.raises(ProviderError) as failure:
            await AnthropicAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
        assert failure.value.code is ProviderErrorCode.INVALID_OUTPUT and len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "mode, tools, structured",
    [("json_object", True, True), ("tool_schema", None, True), ("json_schema", True, None)],
)
def test_unsupported_or_unknown_capabilities_do_not_send(mode, tools, structured):
    async def run():
        request = request_for()
        request = replace(
            request,
            capabilities=replace(
                request.capabilities,
                structured_transport=mode,
                tool_calling=tools,
                structured_output=structured,
            ),
        )
        h = NativeHarness(lambda wire: httpx.Response(200, json=result()), request)
        with pytest.raises(ProviderError) as failure:
            await AnthropicAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
        assert failure.value.code is ProviderErrorCode.CAPABILITY_UNAVAILABLE and not h.calls

    asyncio.run(run())


@pytest.mark.parametrize("cls", [OpenAICompatibleAdapter, OllamaAdapter])
def test_native_tool_transport_is_never_silently_used_by_other_adapters(cls):
    async def run():
        request = request_for()
        request = replace(
            request,
            capabilities=replace(
                request.capabilities, structured_transport="tool_schema", tool_calling=True
            ),
        )
        h = NativeHarness(lambda wire: httpx.Response(200, json=result()), request)
        with pytest.raises(ProviderError) as failure:
            await cls(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
        assert failure.value.code is ProviderErrorCode.CAPABILITY_UNAVAILABLE and not h.calls

    asyncio.run(run())


@pytest.mark.parametrize(
    "status, code",
    [
        (401, "AUTHENTICATION_FAILED"),
        (403, "AUTHENTICATION_FAILED"),
        (429, "RATE_LIMITED"),
        (504, "TIMEOUT"),
        (529, "TEMPORARILY_UNAVAILABLE"),
        (400, "CAPABILITY_UNAVAILABLE"),
        (302, "INVALID_TARGET"),
    ],
)
def test_http_errors_sanitized_no_retry_and_retry_after(status, code):
    async def run():
        h = NativeHarness(
            lambda wire: httpx.Response(status, headers={"retry-after": "2"}, text=KEY)
        )
        with pytest.raises(ProviderError) as failure:
            await AnthropicAdapter(h).generate_text(PROMPT)
        assert (
            failure.value.code.value == code and len(h.calls) == 1 and KEY not in str(failure.value)
        )
        if status == 429:
            assert failure.value.retry_after_seconds == 2

    asyncio.run(run())


def test_stream_unicode_arbitrary_bytes_thinking_ping_and_completion():
    async def run():
        frames = events()
        thinking = [
            event(
                "content_block_start", index=0, content_block={"type": "thinking", "thinking": ""}
            ),
            event(
                "content_block_delta",
                index=0,
                delta={"type": "thinking_delta", "thinking": "private"},
            ),
            event(
                "content_block_delta",
                index=0,
                delta={"type": "signature_delta", "signature": "opaque"},
            ),
            event("content_block_stop", index=0),
        ]
        visible = [frame.replace(b'"index": 0', b'"index": 1') for frame in frames[1:4]]
        wire = b"".join(
            [
                frames[0],
                *thinking,
                event("ping"),
                event("future_event", extra="ignored"),
                *visible,
                *frames[4:],
            ]
        )
        stream = Chunks([bytes([byte]) for byte in wire])
        h = NativeHarness(lambda request: httpx.Response(200, stream=stream))
        deltas = [delta.text async for delta in AnthropicAdapter(h).stream_text(PROMPT)]
        assert "".join(deltas) == "可见" and stream.closed and h.calls[0]["stream"] is True

    asyncio.run(run())


@pytest.mark.parametrize(
    "bad",
    [
        "truncated",
        "wrong-index",
        "max-tokens",
        "tool",
        "duplicate-start",
        "missing-block-stop",
        "bad-usage",
        "bad-json",
    ],
)
def test_stream_invalid_state_is_closed_and_never_retried(bad):
    async def run():
        frames = events()
        if bad == "truncated":
            frames.pop()
        elif bad == "wrong-index":
            frames[2] = event(
                "content_block_delta", index=1, delta={"type": "text_delta", "text": "x"}
            )
        elif bad == "max-tokens":
            frames[4] = event("message_delta", delta={"stop_reason": "max_tokens"})
        elif bad == "tool":
            frames[1] = event("content_block_start", index=0, content_block={"type": "tool_use"})
        elif bad == "duplicate-start":
            frames.insert(1, frames[0])
        elif bad == "missing-block-stop":
            frames.pop(3)
        elif bad == "bad-usage":
            frames[4] = event(
                "message_delta", delta={"stop_reason": "end_turn"}, usage={"output_tokens": True}
            )
        else:
            frames[2] = b'data: {"type":"content_block_delta","type":"message_stop"}\n\n'
        stream = Chunks(frames)
        h = NativeHarness(lambda wire: httpx.Response(200, stream=stream))
        with pytest.raises(ProviderError):
            _ = [delta async for delta in AnthropicAdapter(h).stream_text(PROMPT)]
        assert stream.closed and len(h.calls) == 1

    asyncio.run(run())


def test_stream_error_after_visible_text_is_safe_and_cancellation_closes():
    async def run():
        stream = Chunks(
            [
                *events()[:3],
                event("error", error={"type": "overloaded_error", "message": "private diagnostic"}),
            ]
        )
        h = NativeHarness(lambda wire: httpx.Response(200, stream=stream))
        output = []
        with pytest.raises(ProviderError) as failure:
            async for delta in AnthropicAdapter(h).stream_text(PROMPT):
                output.append(delta.text)
        assert failure.value.code is ProviderErrorCode.TEMPORARILY_UNAVAILABLE
        assert output == ["可见"] and stream.closed and len(h.calls) == 1
        started = asyncio.Event()

        class Waiting(Chunks):
            async def __aiter__(self):
                yield b"".join(events()[:3])
                started.set()
                await asyncio.Future()

        waiting = Waiting([])
        h = NativeHarness(lambda wire: httpx.Response(200, stream=waiting))

        async def consume():
            return [delta async for delta in AnthropicAdapter(h).stream_text(PROMPT)]

        task = asyncio.create_task(consume())
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert waiting.closed

    asyncio.run(run())


def test_native_model_capabilities_use_explicit_official_fields_and_no_partial_pages():
    raw = {
        "has_more": False,
        "data": [
            {
                "id": "anything",
                "capabilities": {
                    "structured_outputs": {"supported": True},
                    "image_input": {"supported": False},
                },
            }
        ],
    }
    models = model_metadata(raw, "anthropic")
    caps = models[0]["capabilities"]
    assert caps["structured_output"] is True and caps["vision"] is False
    assert (
        caps["streaming"] is None and caps["tool_calling"] is None and caps["source"] == "declared"
    )
    assert caps["version"] == "anthropic-model-capabilities-v1"
    for more in (True, 0, None):
        with pytest.raises(ProviderError):
            model_metadata({**raw, "has_more": more}, "anthropic")


@pytest.mark.parametrize("limit", ["request", "schema", "response"])
def test_native_limits_and_external_schema_refs_fail_closed(limit):
    async def run():
        stream = Chunks([b"x" * (2 * 1024 * 1024 + 1)])
        h = NativeHarness(lambda wire: httpx.Response(200, stream=stream))
        with pytest.raises(ProviderError):
            if limit == "request":
                await AnthropicAdapter(h).generate_text(
                    TextRequest((ChatMessage("user", "x" * (1024 * 1024)),))
                )
            elif limit == "schema":
                await AnthropicAdapter(h).generate_structured(
                    StructuredRequest(PROMPT, {"$ref": "https://forbidden.example/schema"})
                )
            else:
                await AnthropicAdapter(h).generate_text(PROMPT)
        if limit == "response":
            assert len(h.calls) == 1 and stream.closed
        else:
            assert not h.calls

    asyncio.run(run())


@pg
def test_pg_native_x_api_key_fixed_target_and_cleanup(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("HTTPS_PROXY", "http://unrelated.invalid:8080")

    async def run():
        async with pg_context(provider_type="anthropic") as (store, owner, cid):
            sent = []

            def respond(wire):
                assert str(wire.url) == "https://8.8.8.8/v1/messages"
                assert (
                    wire.headers["Host"] == "chosen.test"
                    and wire.extensions["sni_hostname"] == "chosen.test"
                )
                assert wire.headers["x-api-key"] == KEY and "Authorization" not in wire.headers
                assert wire.headers["anthropic-version"] == "2023-06-01"
                sent.append(wire)
                return httpx.Response(200, json=result())

            async with build_connection_provider_gateway(
                store, request_for(owner, cid), allowed, transport=httpx.MockTransport(respond)
            ) as gateway:
                assert (
                    isinstance(gateway._adapter, AnthropicAdapter)
                    and (await gateway.generate_text(PROMPT)).text == "ok"
                )
            assert len(sent) == 1 and "x-api-key" not in sent[0].headers

    asyncio.run(run())


@pg
def test_pg_native_budget_owner_and_catalog_fail_closed(monkeypatch):
    async def run():
        async with pg_context(provider_type="anthropic") as (store, owner, cid):
            sends = []

            async def denied(request):
                raise CredentialFailure("BUDGET_NOT_AUTHORIZED")

            transport = httpx.MockTransport(
                lambda wire: sends.append(wire) or httpx.Response(200, json=result())
            )
            monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
            with pytest.raises(CredentialFailure) as failure:
                async with build_connection_provider_gateway(
                    store, request_for(owner, cid), allowed, transport=transport
                ):
                    pass
            assert failure.value.code == "FEATURE_UNAVAILABLE"
            monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
            with pytest.raises(CredentialFailure) as failure:
                async with build_connection_provider_gateway(
                    store, request_for(owner, cid), denied, transport=transport
                ) as gateway:
                    await gateway.generate_text(PROMPT)
            assert failure.value.code == "BUDGET_NOT_AUTHORIZED"
            foreign = request_for(cid=cid)
            with pytest.raises(CredentialFailure):
                async with build_connection_provider_gateway(
                    store, foreign, allowed, transport=transport
                ):
                    pass
            assert not sends

    asyncio.run(run())


@pg
def test_pg_native_model_list_header_binding_cache_and_secret_echo(monkeypatch):
    async def run():
        async with pg_context(provider_type="anthropic") as (store, owner, cid):
            route = request_for(
                owner, cid, purpose="model_refresh", categories=frozenset({"probe"})
            ).route
            calls = []

            class Budget:
                async def preflight(self, request):
                    pass

                async def authorize_attempt(self, request):
                    pass

            def respond(wire):
                assert (
                    wire.method == "GET" and str(wire.url) == "https://8.8.8.8/v1/models?limit=1000"
                )
                assert (
                    wire.headers["x-api-key"] == KEY
                    and wire.headers["anthropic-version"] == "2023-06-01"
                )
                calls.append(wire)
                return httpx.Response(
                    200,
                    json={
                        "has_more": False,
                        "data": [
                            {
                                "id": "selected-model",
                                "capabilities": {"structured_outputs": {"supported": True}},
                            }
                        ],
                    },
                )

            result = await refresh_models(
                store,
                owner,
                route,
                accepted=True,
                operation_id=request_for().operation_id,
                temporary_handle=None,
                registry=None,
                budget=Budget(),
                transport=httpx.MockTransport(respond),
            )
            assert result == await cached_models(store, owner, cid)
            assert (await resolve_capabilities(store, owner, route)).structured_output is True
            assert "x-api-key" not in calls[0].headers
            with pytest.raises(ProviderError):
                await refresh_models(
                    store,
                    owner,
                    route,
                    accepted=True,
                    operation_id=request_for().operation_id,
                    temporary_handle=None,
                    registry=None,
                    budget=Budget(),
                    transport=httpx.MockTransport(
                        lambda wire: httpx.Response(
                            200, json={"has_more": False, "data": [{"id": KEY}]}
                        )
                    ),
                )
            assert result == await cached_models(store, owner, cid)

    asyncio.run(run())


@pg
@pytest.mark.parametrize("terminal", ["success", "failure", "cancel"])
def test_pg_native_temporary_key_one_use_and_header_wipe(terminal, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context("temporary", provider_type="anthropic") as (store, owner, cid):
            registry = TemporaryCredentialRegistry()
            try:
                r = request_for(owner, cid)
                handle, _ = await TemporaryCredentialService(store, registry).register(
                    owner, cid, 1, r.operation_id, r.purpose, r.route.model_id, {"api_key": KEY}
                )
                r = replace(r, temporary_handle=handle)
                entry = registry._entries[handle]
                sent = []

                async def respond(wire):
                    assert wire.headers["x-api-key"] == KEY
                    sent.append(wire)
                    await wire.extensions["trace"]("http11.send_request_body.complete", {})
                    if terminal == "cancel":
                        raise asyncio.CancelledError
                    return httpx.Response(401 if terminal == "failure" else 200, json=result())

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
                assert not registry._entries and entry.payload == bytearray()
                assert len(sent) == 1 and "x-api-key" not in sent[0].headers
                with pytest.raises(CredentialFailure):
                    await op()
            finally:
                await registry.close()

    asyncio.run(run())


@pg
def test_pg_native_probe_omits_deprecated_sampling_and_keeps_one_request():
    async def run():
        async with pg_context(provider_type="anthropic") as (store, owner, cid):
            r = request_for(owner, cid, purpose="connection_test", categories=frozenset({"probe"}))
            calls = []

            class Budget:
                async def preflight(self, request):
                    pass

                async def authorize_attempt(self, request):
                    pass

            def respond(wire):
                body = json.loads(wire.content)
                assert body["max_tokens"] == 8 and "temperature" not in body
                assert body["messages"] == [{"role": "user", "content": "Reply only with OK."}]
                calls.append(wire)
                return httpx.Response(200, json=result("OK"))

            out = await run_probe(
                store,
                owner,
                r.route,
                accepted=True,
                operation_id=r.operation_id,
                temporary_handle=None,
                registry=None,
                budget=Budget(),
                transport=httpx.MockTransport(respond),
            )
            assert (
                out["requests"] == 1
                and len(calls) == 1
                and out["capabilities"]["structured_output"] is None
            )
            assert "x-api-key" not in calls[0].headers

    asyncio.run(run())
