"""Native protocol/negative contracts and real-PG local dispatch, zero model calls."""

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

from app.core.provider_factory import build_connection_provider_gateway
from app.core.provider_target import TargetPolicy
from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.services.ollama import OllamaAdapter
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
    StructuredRequest,
    TextRequest,
)
from app.services.temporary_credentials import TemporaryCredentialService

LOCAL = TargetPolicy("local", frozenset({("127.0.0.1", 11434)}))


def result(text="ok", *, done=True, reason="stop", **fields):
    raw = {
        "model": "selected-model",
        "message": {"role": "assistant", "content": text},
        "done": done,
        "done_reason": reason,
        "prompt_eval_count": 4,
        "eval_count": 2,
    }
    raw.update(fields)
    return raw


def line(text="", *, done=False, reason=None, **fields):
    return (
        json.dumps(result(text, done=done, reason=reason, **fields), ensure_ascii=False).encode()
        + b"\n"
    )


def test_native_text_request_options_usage_and_unknown_cost():
    async def run():
        h = Harness(lambda r: httpx.Response(200, json=result()))
        out = await OllamaAdapter(h).generate_text(
            TextRequest(PROMPT.messages, max_output_tokens=27, temperature=0)
        )
        assert out.text == "ok" and out.usage.input_tokens == 4 and out.usage.output_tokens == 2
        assert h.calls == [
            {
                "model": "selected-model",
                "messages": [{"role": "user", "content": "synthetic teaching context"}],
                "stream": False,
                "options": {"num_predict": 27, "temperature": 0},
            }
        ]
        raw = result()
        raw.pop("prompt_eval_count")
        raw.pop("eval_count")
        out = await OllamaAdapter(Harness(lambda r: httpx.Response(200, json=raw))).generate_text(
            PROMPT
        )
        assert out.usage is None

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["json_schema", "json_object", "text_json"])
def test_explicit_native_structured_modes_keep_local_schema(mode):
    async def run():
        req = request_for()
        req = replace(req, capabilities=replace(req.capabilities, structured_transport=mode))
        h = Harness(lambda r: httpx.Response(200, json=result('{"answer":3}')), req)
        out = await OllamaAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
        assert out.value == {"answer": 3} and out.usage.output_tokens == 2
        wire = h.calls[0]
        if mode == "json_schema":
            assert wire["format"] == SCHEMA
        elif mode == "json_object":
            assert wire["format"] == "json"
        else:
            assert "format" not in wire
        assert "response_format" not in wire and len(h.calls) == 1

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
        '{"answer":1} trailing',
    ],
)
def test_invalid_structured_output_not_published(text):
    async def run():
        h = Harness(lambda r: httpx.Response(200, json=result(text)))
        with pytest.raises(ProviderError) as e:
            await OllamaAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
        assert e.value.code is ProviderErrorCode.INVALID_OUTPUT and len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "patch",
    [
        {"done": False},
        {"done": 1},
        {"done_reason": "length"},
        {"done_reason": "tool_calls"},
        {"done_reason": None},
        {"message": {"role": "assistant", "content": ""}},
        {"message": {"role": "user", "content": "x"}},
        {"message": {"role": "assistant", "content": None}},
        {"message": {"role": "assistant", "content": "x", "tool_calls": [{}]}},
        {"model": ""},
        {"prompt_eval_count": True},
        {"eval_count": -1},
    ],
)
def test_incomplete_or_malformed_text_is_invalid(patch):
    async def run():
        h = Harness(lambda r: httpx.Response(200, json=result(**patch)))
        with pytest.raises(ProviderError) as e:
            await OllamaAdapter(h).generate_text(PROMPT)
        assert e.value.code is ProviderErrorCode.INVALID_OUTPUT and len(h.calls) == 1

    asyncio.run(run())


def test_fragmented_ndjson_utf8_crlf_thinking_and_final_text():
    async def run():
        thinking = result(
            "",
            done=False,
            reason=None,
            message={"role": "assistant", "content": "", "thinking": "PRIVATE_REASONING"},
        )
        wire = (
            json.dumps(thinking).encode()
            + b"\r\n"
            + line("链表")
            + line("完成", done=True, reason="stop").rstrip(b"\n")
        )
        stream = Chunks([wire[i : i + 1] for i in range(len(wire))])
        h = Harness(lambda r: httpx.Response(200, stream=stream))
        out = [d.text async for d in OllamaAdapter(h).stream_text(PROMPT)]
        assert out == ["链表", "完成"] and stream.closed and len(h.calls) == 1
        assert h.calls[0]["stream"] is True

    asyncio.run(run())


@pytest.mark.parametrize(
    "wire,code",
    [
        (line("partial"), "TEMPORARILY_UNAVAILABLE"),
        (line("partial") + b'{"error":"' + KEY.encode() + b'"}\n', "TEMPORARILY_UNAVAILABLE"),
        (line("partial") + line(done=True, reason="length"), "INVALID_OUTPUT"),
        (line(done=True, reason="stop"), "INVALID_OUTPUT"),
        (line("x", done=1), "INVALID_OUTPUT"),
        (b'{"error":false}\n', "INVALID_OUTPUT"),
        (b'{"model":\xff}\n', "INVALID_OUTPUT"),
        (b'{"done":false,"done":true}\n', "INVALID_OUTPUT"),
        (b"[]\n", "INVALID_OUTPUT"),
        (b"data: [DONE]\n\n", "INVALID_OUTPUT"),
    ],
)
def test_stream_failures_close_no_replay_or_error_body(wire, code, caplog):
    async def run():
        stream = Chunks([wire])
        h = Harness(lambda r: httpx.Response(200, stream=stream))
        with pytest.raises(ProviderError) as e:
            _ = [d async for d in ProviderGateway(OllamaAdapter(h)).stream_text(PROMPT)]
        assert e.value.code.value == code and stream.closed and len(h.calls) == 1
        assert KEY not in str(e.value) and KEY not in caplog.text

    asyncio.run(run())


@pytest.mark.parametrize(
    "status,code",
    [
        (404, "CAPABILITY_UNAVAILABLE"),
        (400, "CAPABILITY_UNAVAILABLE"),
        (301, "INVALID_TARGET"),
        (401, "AUTHENTICATION_FAILED"),
        (403, "AUTHENTICATION_FAILED"),
        (429, "RATE_LIMITED"),
        (500, "TEMPORARILY_UNAVAILABLE"),
        (504, "TIMEOUT"),
    ],
)
def test_errors_never_download_models_or_probe_other_endpoint(status, code):
    async def run():
        h = Harness(
            lambda r: httpx.Response(
                status, text=KEY, headers={"Location": "http://169.254.169.254/"}
            )
        )
        with pytest.raises(ProviderError) as e:
            await ProviderGateway(OllamaAdapter(h)).generate_text(PROMPT)
        assert e.value.code.value == code and len(h.calls) == 1 and KEY not in str(e.value)

    asyncio.run(run())


@pytest.mark.parametrize(
    "feature,value", [(f, v) for f in ("streaming", "structured_output") for v in (None, False)]
)
def test_unknown_model_capability_zero_http(feature, value):
    async def run():
        req = request_for()
        req = replace(req, capabilities=replace(req.capabilities, **{feature: value}))
        h = Harness(lambda r: pytest.fail("unknown model capability sent data"), req)
        with pytest.raises(ProviderError) as e:
            if feature == "streaming":
                _ = [d async for d in OllamaAdapter(h).stream_text(PROMPT)]
            else:
                await OllamaAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
        assert e.value.code is ProviderErrorCode.CAPABILITY_UNAVAILABLE and not h.calls

    asyncio.run(run())


@pytest.mark.parametrize("oversize", ["request", "response", "line", "total", "utf16", "schema"])
def test_bounded_and_non_remote_protocol(oversize):
    async def run():
        stream = None
        if oversize == "request":
            h = Harness(lambda r: pytest.fail("oversize request sent"))
            op = OllamaAdapter(h).generate_text(TextRequest((ChatMessage("user", "x" * 1048577),)))
        elif oversize == "schema":
            h = Harness(lambda r: pytest.fail("remote schema sent"))
            op = OllamaAdapter(h).generate_structured(
                StructuredRequest(PROMPT, {"$ref": "https://example.invalid/"})
            )
        else:
            chunks = {
                "response": [b"x" * 2097153],
                "line": [b"x" * 1048577 + b"\n"],
                "total": [b"\n" * 1048576, b"\n" * 1048576, b"\n"],
                "utf16": [json.dumps(result()).encode("utf-16")],
            }[oversize]
            stream = Chunks(chunks)
            h = Harness(lambda r: httpx.Response(200, stream=stream))

            async def read():
                if oversize in {"line", "total"}:
                    return [d async for d in OllamaAdapter(h).stream_text(PROMPT)]
                return await OllamaAdapter(h).generate_text(PROMPT)

            op = read()
        with pytest.raises(ProviderError):
            await op
        assert not h.calls if oversize in {"request", "schema"} else stream.closed

    asyncio.run(run())


@pg
def test_pg_native_local_whitelist_keyless_route(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("HTTP_PROXY", "http://unrelated.invalid:8080")

    async def run():
        async with pg_context(
            "none",
            provider_type="ollama",
            policy=LOCAL,
            base_url="http://ollama.test:11434",
            resolver=lambda h, p: ["127.0.0.1"],
        ) as (store, owner, cid):
            sent = []

            def respond(wire):
                assert wire.url.host == "127.0.0.1" and wire.url.port == 11434
                assert wire.url.path == "/api/chat" and wire.headers["Host"] == "ollama.test:11434"
                assert "Authorization" not in wire.headers
                body = json.loads(wire.content)
                assert body["options"]["num_predict"] == 4096 and body["model"] == "selected-model"
                assert "format" not in body
                sent.append(wire)
                return httpx.Response(200, json=result())

            async with build_connection_provider_gateway(
                store, request_for(owner, cid), allowed, transport=httpx.MockTransport(respond)
            ) as gateway:
                assert (await gateway.generate_text(PROMPT)).text == "ok"
                assert isinstance(gateway._adapter, OllamaAdapter)
            assert len(sent) == 1

    asyncio.run(run())


@pg
@pytest.mark.parametrize("event", ["public-cloud", "public-local", "changed-dns"])
def test_pg_ollama_never_sends_to_public_or_nonwhite_target(event, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        public = event != "changed-dns"
        async with pg_context(
            provider_type="ollama",
            policy=(LOCAL if event != "public-cloud" else None),
            base_url=("https://public.test" if public else "http://ollama.test:11434"),
            resolver=lambda h, p: (["8.8.8.8"] if public else ["127.0.0.1"]),
        ) as (store, owner, cid):
            sends = []
            grants = []

            async def grant(req):
                grants.append(req.operation_id)

            def respond(wire):
                sends.append(wire)
                store.resolver = lambda h, p: ["127.0.0.2"]
                return httpx.Response(503, text=KEY)

            if public:
                store.keyring = None
            async with build_connection_provider_gateway(
                store, request_for(owner, cid), grant, transport=httpx.MockTransport(respond)
            ) as gateway:
                with pytest.raises(ProviderError) as e:
                    await gateway.generate_text(PROMPT, retry_safe=True)
            assert e.value.code is ProviderErrorCode.INVALID_TARGET
            assert len(sends) == len(grants) == (0 if public else 1)

    asyncio.run(run())


@pg
def test_pg_native_stream_cancel_retires_temporary_key(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context(
            "temporary",
            provider_type="ollama",
            policy=LOCAL,
            base_url="http://ollama.test:11434",
            resolver=lambda h, p: ["127.0.0.1"],
        ) as (store, owner, cid):
            registry = TemporaryCredentialRegistry()
            service = TemporaryCredentialService(store, registry)
            req = request_for(owner, cid)
            handle, _ = await service.register(
                owner, cid, 1, req.operation_id, req.purpose, req.route.model_id, {"api_key": KEY}
            )
            captured = registry._entries[handle]
            req = replace(req, temporary_handle=handle)
            entered = asyncio.Event()
            closed = asyncio.Event()

            class Waiting(httpx.AsyncByteStream):
                async def __aiter__(self):
                    yield line("first")
                    entered.set()
                    await asyncio.sleep(20)
                    yield line(done=True, reason="stop")

                async def aclose(self):
                    closed.set()

            async def respond(wire):
                assert wire.headers["Authorization"] == "Bearer " + KEY
                assert wire.headers["Accept"] == "application/x-ndjson"
                await wire.extensions["trace"]("http11.send_request_body.complete", {})
                return httpx.Response(200, stream=Waiting())

            async def run_gateway():
                async with build_connection_provider_gateway(
                    store, req, allowed, registry=registry, transport=httpx.MockTransport(respond)
                ) as gateway:
                    return [d async for d in gateway.stream_text(PROMPT)]

            try:
                task = asyncio.create_task(run_gateway())
                await asyncio.wait_for(entered.wait(), 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert closed.is_set() and captured.payload == bytearray() and not registry._entries
            finally:
                await registry.close()

    asyncio.run(run())


@pg
@pytest.mark.parametrize("network", ["connection", "timeout"])
def test_pg_connection_failures_are_safe_unified_errors(network, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context(
            "none",
            provider_type="ollama",
            policy=LOCAL,
            base_url="http://ollama.test:11434",
            resolver=lambda h, p: ["127.0.0.1"],
        ) as (store, owner, cid):
            calls = []

            def respond(wire):
                calls.append(wire)
                if network == "connection":
                    raise httpx.ConnectError(KEY, request=wire)
                raise httpx.ReadTimeout(KEY, request=wire)

            async with build_connection_provider_gateway(
                store, request_for(owner, cid), allowed, transport=httpx.MockTransport(respond)
            ) as gateway:
                with pytest.raises(ProviderError) as e:
                    await gateway.generate_text(PROMPT)
            assert e.value.code is (
                ProviderErrorCode.TEMPORARILY_UNAVAILABLE
                if network == "connection"
                else ProviderErrorCode.TIMEOUT
            )
            assert KEY not in str(e.value) and len(calls) == 1

    asyncio.run(run())
