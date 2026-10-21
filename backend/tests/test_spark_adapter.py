"""Optional Spark native HTTP contracts; all data synthetic, all Provider HTTP Mock."""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from test_anthropic_adapter import NativeHarness
from test_provider_connection_gateway import (
    KEY,
    PROMPT,
    SCHEMA,
    Chunks,
    allowed,
    pg,
    pg_context,
    request_for,
)

from app.core.credential_crypto import CredentialFailure
from app.core.provider_factory import build_connection_provider_gateway
from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.services.provider_connection_dispatch import ConnectionConsent
from app.services.provider_gateway import (
    ChatMessage,
    InlineImage,
    ProviderError,
    ProviderGateway,
    StructuredRequest,
    TextRequest,
)
from app.services.provider_model_catalog import refresh_models
from app.services.provider_probe import UnavailableProbeBudget, probe_connection
from app.services.spark import SparkAdapter
from app.services.temporary_credentials import TemporaryCredentialService


def result(text="ok", **fields):
    value = {
        "code": 0,
        "message": "Success",
        "sid": "synthetic-sid",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
    }
    value.update(fields)
    return value


def frame(text="ok", *, reason=None, **fields):
    raw = {"code": 0, "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}}]}
    if reason is not None:
        raw["choices"][0]["finish_reason"] = reason
    raw.update(fields)
    return ("data:" + json.dumps(raw, ensure_ascii=False) + "\n\n").encode()


DONE = b"data:[DONE]\n\n"


@pytest.mark.parametrize("compat", [False, True])
def test_native_complete_envelope_without_model_or_finish_and_safe_wire(compat):
    async def run():
        raw = result()
        if compat:
            raw.pop("code")
            raw["model"] = "upstream-alias"
            raw["choices"][0]["finish_reason"] = "stop"
        raw["choices"][0]["message"]["reasoning_content"] = "hidden"
        h = NativeHarness(lambda _: httpx.Response(200, json=raw))
        prompt = TextRequest(
            (ChatMessage("system", "rule"), ChatMessage("user", "question")),
            max_output_tokens=19,
            temperature=0.7,
        )
        output = await SparkAdapter(h).generate_text(prompt)
        assert output.text == "ok" and output.model_id == "selected-model"
        assert output.usage.input_tokens == 4 and output.usage.output_tokens == 2
        assert h.calls == [
            {
                "model": "selected-model",
                "messages": [
                    {"role": "system", "content": "rule"},
                    {"role": "user", "content": "question"},
                ],
                "max_tokens": 19,
                "temperature": 0.7,
                "stream": False,
                "tool_choice": "none",
                "tools": [{"type": "web_search", "web_search": {"enable": False}}],
            }
        ]
        assert "hidden" not in repr(output) and "user" not in h.calls[0]

    asyncio.run(run())


@pytest.mark.parametrize("counts", [None, {}, {"prompt_tokens": 3}])
def test_unknown_usage_not_invented(counts):
    async def run():
        h = NativeHarness(lambda _: httpx.Response(200, json=result(usage=counts)))
        output = await SparkAdapter(h).generate_text(PROMPT)
        if not counts:
            assert output.usage is None
        else:
            assert output.usage.input_tokens == 3 and output.usage.output_tokens is None
        assert "temperature" not in h.calls[0]

    asyncio.run(run())


@pytest.mark.parametrize(
    "code,error",
    [
        (10007, "RATE_LIMITED"),
        (11201, "RATE_LIMITED"),
        (11202, "RATE_LIMITED"),
        (11203, "RATE_LIMITED"),
        (11200, "AUTHENTICATION_FAILED"),
        (10907, "CAPABILITY_UNAVAILABLE"),
        (10013, "INVALID_OUTPUT"),
        (10014, "INVALID_OUTPUT"),
        (10019, "INVALID_OUTPUT"),
        (98765, "CAPABILITY_UNAVAILABLE"),
    ],
)
@pytest.mark.parametrize("streaming", [False, True])
def test_vendor_codes_are_safe_and_never_success_or_replayed(code, error, streaming):
    async def run():
        raw = {"code": code, "message": "private upstream diagnostic"}
        data = ("data:" + json.dumps(raw) + "\n\n").encode()
        h = NativeHarness(
            lambda _: httpx.Response(200, stream=Chunks([data]))
            if streaming
            else httpx.Response(200, json=raw)
        )
        with pytest.raises(ProviderError) as failure:
            if streaming:
                _ = [d async for d in SparkAdapter(h).stream_text(PROMPT)]
            else:
                await ProviderGateway(SparkAdapter(h)).generate_text(PROMPT)
        assert failure.value.code.value == error and "private upstream" not in str(failure.value)
        assert len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "status,error",
    [
        (401, "AUTHENTICATION_FAILED"),
        (403, "AUTHENTICATION_FAILED"),
        (429, "RATE_LIMITED"),
        (504, "TIMEOUT"),
        (503, "TEMPORARILY_UNAVAILABLE"),
        (400, "CAPABILITY_UNAVAILABLE"),
        (302, "INVALID_TARGET"),
    ],
)
def test_http_error_mapping_and_no_redirect(status, error):
    async def run():
        h = NativeHarness(lambda _: httpx.Response(status, text=KEY))
        with pytest.raises(ProviderError) as failure:
            await SparkAdapter(h).generate_text(PROMPT)
        assert failure.value.code.value == error and KEY not in str(failure.value)
        assert len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        "bool_code",
        "string_code",
        "choices",
        "bool_index",
        "role",
        "empty",
        "binary",
        "refusal",
        "tool",
        "function",
        "security",
        "reasoning",
        "type",
        "usage",
        "search_usage",
        "search",
        "echo",
        "length",
        "error",
    ],
)
def test_invalid_or_unsafe_output_rejected(mutation):
    async def run():
        raw = result()
        message = raw["choices"][0]["message"]
        if mutation == "bool_code":
            raw["code"] = False
        elif mutation == "string_code":
            raw["code"] = "0"
        elif mutation == "choices":
            raw["choices"].append(raw["choices"][0].copy())
        elif mutation == "bool_index":
            raw["choices"][0]["index"] = False
        elif mutation == "role":
            message["role"] = "tool"
        elif mutation == "empty":
            message["content"] = " "
        elif mutation == "binary":
            message["content"] = [{"image": "url"}]
        elif mutation == "refusal":
            message["refusal"] = "private"
        elif mutation == "tool":
            message["tool_calls"] = [{"id": "unsafe"}]
        elif mutation == "function":
            message["function_call"] = {"name": "unsafe"}
        elif mutation == "security":
            message["security_suggest"] = {"action": "HIDE_CONTINUE"}
        elif mutation == "reasoning":
            message["reasoning_content"] = {}
        elif mutation == "type":
            message["type"] = {"unexpected": "object"}
        elif mutation == "usage":
            raw["usage"]["completion_tokens"] = True
        elif mutation == "search_usage":
            raw["usage"]["search_prompt_tokens"] = 1
        elif mutation == "search":
            raw["search_results"] = ["unexpected"]
        elif mutation == "echo":
            message["content"] = KEY
        elif mutation == "length":
            raw["choices"][0]["finish_reason"] = "length"
        else:
            raw["error"] = {"code": None, "message": "private"}
        h = NativeHarness(lambda _: httpx.Response(200, json=raw))
        with pytest.raises(ProviderError):
            await SparkAdapter(h).generate_text(PROMPT)
        assert len(h.calls) == 1

    asyncio.run(run())


def test_native_sse_unicode_reasoning_hidden_finish_optional_and_usage_tail():
    async def run():
        thought = frame(
            "",
            choices=[
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "reasoning_content": "hidden",
                        "security_suggest": {"action": "HIDE_CONTINUE"},
                    },
                }
            ],
        )
        data = (
            thought
            + frame("你")
            + frame("好")
            + frame("", usage={"prompt_tokens": 4, "completion_tokens": 2})
            + DONE
        )
        stream = Chunks([bytes([byte]) for byte in data])
        h = NativeHarness(lambda _: httpx.Response(200, stream=stream))
        assert [d.text async for d in SparkAdapter(h).stream_text(PROMPT)] == ["你", "好"]
        assert stream.closed and len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        "truncated",
        "length",
        "tool",
        "refusal",
        "bad_json",
        "after_finish",
        "after_done",
        "hidden_only",
        "changed_model",
        "bad_usage",
        "error",
        "duplicate",
        "escaped_echo",
    ],
)
def test_sse_failures_close_with_no_automatic_replay(mutation):
    async def run():
        first = frame("first")
        if mutation == "truncated":
            data = first
        elif mutation == "length":
            data = first + frame("", reason="length") + DONE
        elif mutation in ("tool", "refusal"):
            delta = (
                {"tool_calls": [{"name": "unsafe"}]}
                if mutation == "tool"
                else {"refusal": "private"}
            )
            data = first + frame("", choices=[{"index": 0, "delta": delta}]) + DONE
        elif mutation == "bad_json":
            data = first + b"data:invalid\n\n" + DONE
        elif mutation == "after_finish":
            data = frame("first", reason="stop") + frame("late") + DONE
        elif mutation == "after_done":
            data = first + DONE + frame("late")
        elif mutation == "hidden_only":
            data = (
                frame("", choices=[{"index": 0, "delta": {"reasoning_content": "hidden"}}]) + DONE
            )
        elif mutation == "changed_model":
            data = frame("first", model="one") + frame("last", model="two") + DONE
        elif mutation == "bad_usage":
            data = first + frame("", usage={"total_tokens": -1}) + DONE
        elif mutation == "error":
            data = first + b'data:{"code":11202,"message":"private"}\n\n'
        elif mutation == "duplicate":
            data = b'data:{"code":0,"code":11200}\n\n'
        else:
            data = (
                frame(KEY).replace(KEY.encode(), "".join("\\u%04x" % ord(c) for c in KEY).encode())
                + DONE
            )
        stream = Chunks([data])
        h = NativeHarness(lambda _: httpx.Response(200, stream=stream))
        with pytest.raises(ProviderError):
            _ = [d async for d in SparkAdapter(h).stream_text(PROMPT)]
        assert stream.closed and len(h.calls) == 1

    asyncio.run(run())


def test_cancel_closes_active_stream():
    async def run():
        entered = asyncio.Event()

        class Waiting(Chunks):
            async def __aiter__(self):
                yield frame("visible")
                entered.set()
                await asyncio.Future()

        stream = Waiting([])
        h = NativeHarness(lambda _: httpx.Response(200, stream=stream))

        async def consume():
            return [d async for d in SparkAdapter(h).stream_text(PROMPT)]

        task = asyncio.create_task(consume())
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stream.closed

    asyncio.run(run())


@pytest.mark.parametrize(
    "kind", ["unknown_stream", "structured", "image", "request_size", "response_size", "frame_size"]
)
def test_unsupported_capability_and_size_limits(kind):
    async def run():
        r = request_for()
        if kind == "unknown_stream":
            r = replace(r, capabilities=replace(r.capabilities, streaming=None))
        stream = Chunks(
            [b"x" * (2 * 1024 * 1024 + 1)]
            if kind == "response_size"
            else [b"data:" + b"x" * (1024 * 1024 + 1)]
        )
        h = NativeHarness(lambda _: httpx.Response(200, stream=stream), r)
        with pytest.raises(ProviderError):
            if kind == "structured":
                await SparkAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
            elif kind == "image":
                await SparkAdapter(h).generate_text(
                    replace(PROMPT, images=(InlineImage("image/png", b"synthetic"),))
                )
            elif kind == "request_size":
                await SparkAdapter(h).generate_text(
                    TextRequest((ChatMessage("user", "x" * (1024 * 1024)),))
                )
            elif kind == "response_size":
                await SparkAdapter(h).generate_text(PROMPT)
            else:
                _ = [d async for d in SparkAdapter(h).stream_text(PROMPT)]
        if kind in {"response_size", "frame_size"}:
            assert len(h.calls) == 1 and stream.closed
        else:
            assert not h.calls

    asyncio.run(run())


@pg
@pytest.mark.parametrize("prefix", ["v1", "v2", "x2"])
def test_pg_native_fixed_ip_password_header_and_cleanup(prefix, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("HTTPS_PROXY", "http://unrelated.invalid:8080")

    async def run():
        async with pg_context(provider_type="spark", base_url="https://chosen.test/" + prefix) as (
            store,
            owner,
            cid,
        ):
            calls = []

            def respond(wire):
                assert str(wire.url) == "https://8.8.8.8/" + prefix + "/chat/completions"
                assert wire.headers["Authorization"] == "Bearer " + KEY
                assert (
                    wire.headers["Host"] == "chosen.test"
                    and wire.extensions["sni_hostname"] == "chosen.test"
                )
                body = json.loads(wire.content)
                assert (
                    body["tools"][0]["web_search"]["enable"] is False
                    and body["tool_choice"] == "none"
                )
                calls.append(wire)
                return httpx.Response(200, json=result())

            async with build_connection_provider_gateway(
                store, request_for(owner, cid), allowed, transport=httpx.MockTransport(respond)
            ) as gateway:
                assert isinstance(gateway._adapter, SparkAdapter)
                assert (await gateway.generate_text(PROMPT)).text == "ok"
            assert len(calls) == 1 and "Authorization" not in calls[0].headers

    asyncio.run(run())


@pg
def test_pg_catalog_owner_budget_and_signed_credentials_fail_closed(monkeypatch):
    async def run():
        async with pg_context(provider_type="spark") as (store, owner, cid):
            calls = []
            transport = httpx.MockTransport(
                lambda wire: calls.append(wire) or httpx.Response(200, json=result())
            )
            r = request_for(owner, cid)
            monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
            with pytest.raises(CredentialFailure):
                async with build_connection_provider_gateway(
                    store, r, allowed, transport=transport
                ):
                    pass
            monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

            async def deny(request):
                raise CredentialFailure("BUDGET_NOT_AUTHORIZED")

            with pytest.raises(CredentialFailure):
                async with build_connection_provider_gateway(
                    store, r, deny, transport=transport
                ) as gateway:
                    await gateway.generate_text(PROMPT)
            with pytest.raises(CredentialFailure):
                async with build_connection_provider_gateway(
                    store, request_for(cid=cid), allowed, transport=transport
                ):
                    pass
            await store.replace(
                owner,
                cid,
                1,
                secret={
                    "api_key": KEY,
                    "api_secret": "synthetic-ws-secret",
                    "app_id": "synthetic-app",
                },
            )
            route = replace(r.route, config_version=2)
            r = replace(
                r,
                route=route,
                consent=ConnectionConsent(route, True),
                capabilities=replace(r.capabilities, config_version=2),
            )
            with pytest.raises(CredentialFailure):
                async with build_connection_provider_gateway(
                    store, r, allowed, transport=transport
                ) as gateway:
                    await gateway.generate_text(PROMPT)
            assert not calls

    asyncio.run(run())


@pg
@pytest.mark.parametrize("terminal", ["success", "failure", "cancel"])
def test_pg_temporary_password_wiped_for_every_terminal(terminal, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context("temporary", provider_type="spark") as (store, owner, cid):
            registry = TemporaryCredentialRegistry()
            try:
                r = request_for(owner, cid)
                handle, _ = await TemporaryCredentialService(store, registry).register(
                    owner, cid, 1, r.operation_id, r.purpose, r.route.model_id, {"api_key": KEY}
                )
                r = replace(r, temporary_handle=handle)
                entry = registry._entries[handle]
                calls = []

                async def respond(wire):
                    calls.append(wire)
                    assert wire.headers["Authorization"] == "Bearer " + KEY
                    await wire.extensions["trace"]("http11.send_request_body.complete", {})
                    if terminal == "cancel":
                        raise asyncio.CancelledError
                    return httpx.Response(401 if terminal == "failure" else 200, json=result())

                async def operation():
                    async with build_connection_provider_gateway(
                        store, r, allowed, registry=registry, transport=httpx.MockTransport(respond)
                    ) as gateway:
                        return await gateway.generate_text(PROMPT)

                if terminal == "success":
                    assert (await operation()).text == "ok"
                else:
                    with pytest.raises(
                        asyncio.CancelledError if terminal == "cancel" else ProviderError
                    ):
                        await operation()
                assert not registry._entries and entry.payload == bytearray() and len(calls) == 1
                assert "Authorization" not in calls[0].headers
                with pytest.raises(CredentialFailure):
                    await operation()
                assert len(calls) == 1
            finally:
                await registry.close()

    asyncio.run(run())


@pg
def test_pg_native_probe_and_unimplemented_models_do_not_grant_budget():
    class Budget:
        async def preflight(self, request):
            pass

        async def authorize_attempt(self, request):
            pass

    async def run():
        async with pg_context(provider_type="spark") as (store, owner, cid):
            r = request_for(owner, cid, purpose="connection_test", categories=frozenset({"probe"}))
            calls = []

            def respond(wire):
                calls.append(wire)
                body = json.loads(wire.content)
                assert (
                    body["max_tokens"] == 8
                    and "temperature" not in body
                    and len(body["messages"]) == 1
                )
                return httpx.Response(200, json=result())

            kwargs = dict(
                accepted=True,
                operation_id=uuid4(),
                temporary_handle=None,
                registry=None,
                budget=Budget(),
                transport=httpx.MockTransport(respond),
            )
            output = await probe_connection(store, owner, r.route, **kwargs)
            assert output["requests"] == 1 and output["capabilities"]["streaming"] is None
            with pytest.raises(CredentialFailure):
                await probe_connection(
                    store, owner, r.route, **{**kwargs, "budget": UnavailableProbeBudget()}
                )
            with pytest.raises(ProviderError):
                await refresh_models(store, owner, r.route, **kwargs)
            assert len(calls) == 1 and "Authorization" not in calls[0].headers

    asyncio.run(run())
