"""Native Gemini contracts and real PG send authority, with only synthetic Mock data."""

import asyncio
import base64
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
from app.services.anthropic import AnthropicAdapter
from app.services.gemini import GeminiAdapter, model_resource
from app.services.ollama import OllamaAdapter
from app.services.openai_compatible import OpenAICompatibleAdapter
from app.services.provider_gateway import (
    ChatMessage,
    InlineImage,
    InlineImageConsent,
    OutputFailureReason,
    ProviderError,
    ProviderGateway,
    StructuredRequest,
    TextRequest,
)
from app.services.provider_inline_images import image_manifest
from app.services.provider_model_catalog import (
    cached_models,
    model_metadata,
    refresh_models,
    resolve_capabilities,
)
from app.services.provider_probe import probe_connection
from app.services.temporary_credentials import TemporaryCredentialService

IMAGE = InlineImage("image/png", b"\x89PNG\r\n\x1a\nsynthetic-mock-not-a-real-upload")


def result(text="ok", reason="STOP", **extra):
    raw = {
        "modelVersion": "actual-version",
        "candidates": [
            {
                "index": 0,
                "content": {"role": "model", "parts": [{"text": text}]},
                "finishReason": reason,
            }
        ],
        "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
    }
    raw.update(extra)
    return raw


def frame(raw):
    return ("data: " + json.dumps(raw, ensure_ascii=False) + "\n\n").encode()


def media_request(dispatch=None, schema=None):
    dispatch = dispatch or request_for(categories=frozenset({"content_for_review"}))
    dispatch = replace(dispatch, capabilities=replace(dispatch.capabilities, vision=True))
    prompt = replace(PROMPT, images=(IMAGE,))
    route = dispatch.route
    consent = InlineImageConsent(
        route.connection_id,
        route.config_version,
        route.model_id,
        dispatch.operation_id,
        image_manifest(prompt, schema),
        True,
    )
    return dispatch, replace(prompt, image_consent=consent)


def test_native_content_system_role_parameters_and_actual_usage():
    async def run():
        raw = result(
            usageMetadata={
                "promptTokenCount": 4,
                "candidatesTokenCount": 2,
                "thoughtsTokenCount": 3,
            }
        )
        raw["candidates"][0]["content"]["parts"] = [
            {"text": "private thinking", "thought": True},
            {"text": "visible", "thoughtSignature": "hidden-signature"},
        ]
        h = NativeHarness(lambda _: httpx.Response(200, json=raw))
        prompt = TextRequest(
            (
                ChatMessage("system", "rules"),
                ChatMessage("user", "before"),
                ChatMessage("assistant", "answer"),
                ChatMessage("user", "question"),
            ),
            max_output_tokens=17,
            temperature=0.7,
        )
        output = await GeminiAdapter(h).generate_text(prompt)
        assert output.text == "visible" and output.model_id == "actual-version"
        assert output.usage.input_tokens == 4 and output.usage.output_tokens == 5
        assert h.calls == [
            {
                "systemInstruction": {"parts": [{"text": "rules"}]},
                "contents": [
                    {"role": "user", "parts": [{"text": "before"}]},
                    {"role": "model", "parts": [{"text": "answer"}]},
                    {"role": "user", "parts": [{"text": "question"}]},
                ],
                "generationConfig": {
                    "maxOutputTokens": 17,
                    "candidateCount": 1,
                    "temperature": 0.7,
                    "responseModalities": ["TEXT"],
                },
            }
        ]

    asyncio.run(run())


@pytest.mark.parametrize(
    "prompt",
    [
        TextRequest((ChatMessage("assistant", "prefill"),)),
        TextRequest((ChatMessage("user", "q"), ChatMessage("system", "late"))),
        TextRequest((ChatMessage("system", "only"),)),
        replace(PROMPT, temperature=float("nan")),
        replace(PROMPT, max_output_tokens=True),
    ],
)
def test_invalid_prompt_fails_before_send(prompt):
    async def run():
        h = NativeHarness(lambda _: httpx.Response(200, json=result()))
        with pytest.raises(ProviderError):
            await GeminiAdapter(h).generate_text(prompt)
        assert not h.calls

    asyncio.run(run())


@pytest.mark.parametrize(
    "name",
    [
        "../models/other",
        "models/a/b",
        "a?key=value",
        "a%2fb",
        "a:streamGenerateContent",
        "https://other/model",
        "models/",
        "..",
    ],
)
def test_model_path_injection_rejected(name):
    with pytest.raises(ProviderError):
        model_resource(name)


def test_model_resource_keeps_selected_short_or_canonical_name():
    assert model_resource("selected-model") == model_resource("models/selected-model")


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_model",
        "bad_usage",
        "bad_role",
        "extra_candidate",
        "thought_only",
        "function",
        "binary",
        "blocked",
        "echo",
        "bool_index",
        "unknown_finish",
        "limit",
    ],
)
def test_output_rejects_incomplete_refused_tool_binary_and_secret(mutation):
    async def run():
        raw = result()
        candidate = raw["candidates"][0]
        if mutation == "missing_model":
            raw.pop("modelVersion")
        elif mutation == "bad_usage":
            raw["usageMetadata"]["thoughtsTokenCount"] = True
        elif mutation == "bad_role":
            candidate["content"]["role"] = "user"
        elif mutation == "extra_candidate":
            raw["candidates"].append(candidate.copy())
        elif mutation == "thought_only":
            candidate["content"]["parts"][0]["thought"] = True
        elif mutation == "function":
            candidate["content"]["parts"] = [{"functionCall": {"name": "unsafe"}}]
        elif mutation == "binary":
            candidate["content"]["parts"] = [{"inlineData": {"data": "AA=="}}]
        elif mutation == "blocked":
            raw["promptFeedback"] = {"blockReason": "SAFETY"}
        elif mutation == "echo":
            candidate["content"]["parts"][0]["text"] = KEY
        elif mutation == "bool_index":
            candidate["index"] = False
        elif mutation == "unknown_finish":
            candidate["finishReason"] = "SAFETY"
        else:
            candidate["finishReason"] = "MAX_TOKENS"
        h = NativeHarness(lambda _: httpx.Response(200, json=raw))
        with pytest.raises(ProviderError) as failure:
            await GeminiAdapter(h).generate_text(PROMPT)
        assert len(h.calls) == 1 and KEY not in str(failure.value)
        if mutation == "limit":
            assert failure.value.output_failure_reason == OutputFailureReason.OUTPUT_TOKEN_LIMIT

    asyncio.run(run())


@pytest.mark.parametrize("counts", [None, {}, {"promptTokenCount": 4}])
def test_missing_usage_not_invented(counts):
    async def run():
        h = NativeHarness(lambda _: httpx.Response(200, json=result(usageMetadata=counts)))
        output = await GeminiAdapter(h).generate_text(PROMPT)
        if not counts:
            assert output.usage is None
        else:
            assert output.usage.input_tokens == 4 and output.usage.output_tokens is None
        assert "temperature" not in h.calls[0]["generationConfig"]

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["json_schema", "text_json"])
def test_structured_preserves_original_schema_and_explicit_transport(mode):
    async def run():
        dispatch = request_for()
        dispatch = replace(
            dispatch, capabilities=replace(dispatch.capabilities, structured_transport=mode)
        )
        h = NativeHarness(lambda _: httpx.Response(200, json=result('{"answer": 2}')), dispatch)
        output = await GeminiAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
        assert output.value == {"answer": 2}
        config = h.calls[0]["generationConfig"]
        if mode == "json_schema":
            assert config["responseFormat"] == {
                "text": {"mimeType": "application/json", "schema": SCHEMA}
            }
            assert "responseSchema" not in config and "responseJsonSchema" not in config
        else:
            assert "responseFormat" not in config
            assert "schema" in h.calls[0]["systemInstruction"]["parts"][0]["text"]

    asyncio.run(run())


@pytest.mark.parametrize(
    "output",
    [
        '{"answer": "wrong"}',
        '{"answer": 2, "extra": 1}',
        "[]",
        '{"answer": 1, "answer": 2}',
        "```json\n{}\n```",
    ],
)
def test_structured_local_validation_never_replays(output):
    async def run():
        h = NativeHarness(lambda _: httpx.Response(200, json=result(output)))
        with pytest.raises(ProviderError):
            await GeminiAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
        assert len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "capability", ["stream", "unknown_schema", "json_object", "tool_schema", "external_schema"]
)
def test_capability_or_schema_mismatch_before_send(capability):
    async def run():
        r = request_for()
        if capability == "stream":
            r = replace(r, capabilities=replace(r.capabilities, streaming=None))
        elif capability == "unknown_schema":
            r = replace(r, capabilities=replace(r.capabilities, structured_output=None))
        elif capability != "external_schema":
            r = replace(r, capabilities=replace(r.capabilities, structured_transport=capability))
        h = NativeHarness(lambda _: httpx.Response(200, json=result()), r)
        with pytest.raises(ProviderError):
            if capability == "stream":
                _ = [d async for d in GeminiAdapter(h).stream_text(PROMPT)]
            else:
                schema = (
                    {"$ref": "https://unapproved/schema"}
                    if capability == "external_schema"
                    else SCHEMA
                )
                await GeminiAdapter(h).generate_structured(StructuredRequest(PROMPT, schema))
        assert not h.calls

    asyncio.run(run())


@pytest.mark.parametrize(
    "status,code",
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
def test_http_error_is_content_free_and_single_attempt(status, code):
    async def run():
        h = NativeHarness(
            lambda _: httpx.Response(
                status, json={"error": {"message": KEY}}, headers={"Retry-After": "2"}
            )
        )
        with pytest.raises(ProviderError) as failure:
            await ProviderGateway(GeminiAdapter(h)).generate_text(PROMPT)
        assert failure.value.code.value == code and KEY not in str(failure.value)
        assert len(h.calls) == 1

    asyncio.run(run())


def test_stream_incremental_unicode_thoughts_terminal_and_usage_tail():
    async def run():
        first = result(reason=None)
        first["candidates"][0]["content"]["parts"] = [
            {"text": "hidden", "thought": True},
            {"text": "你"},
        ]
        data = (
            frame(first)
            + frame(result("好"))
            + frame({"usageMetadata": {"candidatesTokenCount": 2}})
        )
        stream = Chunks([bytes([b]) for b in data])
        h = NativeHarness(lambda _: httpx.Response(200, stream=stream))
        assert "".join([d.text async for d in GeminiAdapter(h).stream_text(PROMPT)]) == "你好"
        assert stream.closed and len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        "truncated",
        "blocked",
        "after_stop",
        "changed_model",
        "bad_json",
        "duplicate",
        "function",
        "unknown_error",
        "error",
    ],
)
def test_stream_failures_close_and_never_replay(mutation):
    async def run():
        first = result("first", None)
        if mutation == "truncated":
            data = frame(first)
        elif mutation == "blocked":
            data = frame(first) + frame(result("", "SAFETY"))
        elif mutation == "after_stop":
            data = frame(result()) + frame(first)
        elif mutation == "changed_model":
            data = frame(first) + frame(result(modelVersion="other"))
        elif mutation == "bad_json":
            data = frame(first) + b"data: broken\n\n"
        elif mutation == "duplicate":
            data = b'data: {"candidates":[],"candidates":[]}\n\n'
        elif mutation == "function":
            first["candidates"][0]["content"]["parts"] = [{"functionCall": {"name": "unsafe"}}]
            data = frame(first)
        else:
            data = frame(first) + frame(
                {
                    "error": {
                        "status": "UNAVAILABLE" if mutation == "error" else "unknown",
                        "message": KEY,
                    }
                }
            )
        stream = Chunks([data])
        h = NativeHarness(lambda _: httpx.Response(200, stream=stream))
        with pytest.raises(ProviderError) as failure:
            _ = [d async for d in GeminiAdapter(h).stream_text(PROMPT)]
        assert stream.closed and len(h.calls) == 1 and KEY not in str(failure.value)

    asyncio.run(run())


def test_stream_cancel_closes_transport():
    async def run():
        waiting = asyncio.Event()

        class Wait(Chunks):
            async def __aiter__(self):
                yield frame(result("first", None))
                waiting.set()
                await asyncio.Future()

        stream = Wait([])
        h = NativeHarness(lambda _: httpx.Response(200, stream=stream))

        async def consume():
            return [d async for d in GeminiAdapter(h).stream_text(PROMPT)]

        task = asyncio.create_task(consume())
        await asyncio.wait_for(waiting.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stream.closed

    asyncio.run(run())


@pytest.mark.parametrize("structured", [False, True])
def test_json_escaped_secret_values_rejected_inside_send_context(structured):
    async def run():
        escaped = "".join("\\u%04x" % ord(c) for c in KEY)
        text = '{"answer": "' + escaped + '"}' if structured else KEY
        data = json.dumps(result(text)).replace(KEY, escaped).encode()
        h = NativeHarness(lambda _: httpx.Response(200, content=data))
        with pytest.raises(ProviderError):
            if structured:
                await GeminiAdapter(h).generate_structured(StructuredRequest(PROMPT, SCHEMA))
            else:
                await GeminiAdapter(h).generate_text(PROMPT)
        assert len(h.calls) == 1

    asyncio.run(run())


def test_inline_image_failure_is_not_retried_even_when_retry_safe():
    from app.services.provider_gateway import RetryPolicy

    async def run():
        r, prompt = media_request()
        h = NativeHarness(lambda _: httpx.Response(503), r)
        gateway = ProviderGateway(GeminiAdapter(h), retry_policy=RetryPolicy(max_attempts=3))
        with pytest.raises(ProviderError):
            await gateway.generate_text(prompt, retry_safe=True)
        assert len(h.calls) == 1

    asyncio.run(run())


def test_nested_schema_is_snapshotted_before_send_for_content_bound_consent():
    from contextlib import asynccontextmanager

    async def run():
        schema = json.loads(json.dumps(SCHEMA))
        r, prompt = media_request(schema=schema)

        class Mutating(NativeHarness):
            @asynccontextmanager
            async def send(self, body, *, stream=False):
                schema["properties"]["answer"]["type"] = "string"
                async with super().send(body, stream=stream) as response:
                    yield response

        h = Mutating(lambda _: httpx.Response(200, json=result('{"answer": 2}')), r)
        value = await GeminiAdapter(h).generate_structured(StructuredRequest(prompt, schema))
        assert value.value == {"answer": 2}
        assert h.calls[0]["generationConfig"]["responseFormat"]["text"]["schema"] == SCHEMA
        assert schema["properties"]["answer"]["type"] == "string"

    asyncio.run(run())


@pytest.mark.parametrize("structured", [False, True])
def test_exact_image_consent_inline_bytes_and_no_second_upload(structured):
    async def run():
        r, prompt = media_request(schema=SCHEMA if structured else None)
        h = NativeHarness(
            lambda _: httpx.Response(200, json=result('{"answer": 2}' if structured else "ok")), r
        )
        adapter = GeminiAdapter(h)

        async def call():
            if structured:
                return await adapter.generate_structured(StructuredRequest(prompt, SCHEMA))
            return await adapter.generate_text(prompt)

        await call()
        inline = h.calls[0]["contents"][-1]["parts"][-1]["inlineData"]
        assert (
            inline["mimeType"] == IMAGE.mime_type and base64.b64decode(inline["data"]) == IMAGE.data
        )
        assert "synthetic-mock" not in repr(prompt) and "fileData" not in json.dumps(h.calls)
        with pytest.raises(ProviderError):
            await call()
        assert len(h.calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "declined",
        "model",
        "connection",
        "version",
        "operation",
        "manifest",
        "prompt",
        "schema",
        "vision",
        "category",
        "probe",
        "mime",
        "bytes",
        "oversize",
        "count",
    ],
)
def test_image_authority_mismatch_never_sends(mutation):
    async def run():
        r, prompt = media_request()
        c = prompt.image_consent
        if mutation == "missing":
            prompt = replace(prompt, image_consent=None)
        elif mutation == "declined":
            prompt = replace(prompt, image_consent=replace(c, accepted=False))
        elif mutation == "model":
            prompt = replace(prompt, image_consent=replace(c, model_id="other"))
        elif mutation == "connection":
            prompt = replace(prompt, image_consent=replace(c, connection_id=uuid4()))
        elif mutation == "version":
            prompt = replace(prompt, image_consent=replace(c, config_version=2))
        elif mutation == "operation":
            prompt = replace(prompt, image_consent=replace(c, operation_id=uuid4()))
        elif mutation == "manifest":
            prompt = replace(prompt, image_consent=replace(c, manifest_sha256="0" * 64))
        elif mutation == "prompt":
            prompt = replace(prompt, messages=(ChatMessage("user", "changed"),))
        elif mutation == "vision":
            r = replace(r, capabilities=replace(r.capabilities, vision=None))
        elif mutation == "category":
            r = replace(r, route=replace(r.route, data_categories=frozenset({"learning_goal"})))
        elif mutation == "probe":
            r = replace(r, purpose="connection_test")
        elif mutation == "mime":
            prompt = replace(prompt, images=(replace(IMAGE, mime_type="application/pdf"),))
        elif mutation == "bytes":
            prompt = replace(prompt, images=(replace(IMAGE, data=b"https://unapproved/image"),))
        elif mutation == "oversize":
            prompt = replace(
                prompt, images=(replace(IMAGE, data=IMAGE.data + b"x" * (512 * 1024)),)
            )
        elif mutation == "count":
            prompt = replace(prompt, images=(IMAGE,) * 5)
        h = NativeHarness(lambda _: httpx.Response(200, json=result()), r)
        with pytest.raises((ProviderError, CredentialFailure)):
            if mutation == "schema":
                await GeminiAdapter(h).generate_structured(StructuredRequest(prompt, SCHEMA))
            else:
                await GeminiAdapter(h).generate_text(prompt)
        assert not h.calls

    asyncio.run(run())


@pytest.mark.parametrize("adapter_type", [OpenAICompatibleAdapter, OllamaAdapter, AnthropicAdapter])
def test_other_adapters_and_gateway_reject_images_instead_of_dropping(adapter_type):
    async def run():
        r, prompt = media_request()
        h = NativeHarness(lambda _: httpx.Response(200, json=result()), r)
        for adapter in (adapter_type(h),):
            with pytest.raises(ProviderError):
                await adapter.generate_text(prompt)
            with pytest.raises(ProviderError):
                await ProviderGateway(adapter).generate_text(prompt)
        assert not h.calls

    asyncio.run(run())


def test_model_list_canonical_names_unknown_flags_and_no_partial_cache():
    raw = {
        "models": [
            {"name": "models/selected-model", "supportedGenerationMethods": ["generateContent"]}
        ]
    }
    models = model_metadata(raw, "gemini")
    assert models[0]["id"] == "models/selected-model"
    assert models[0]["capabilities"]["streaming"] is None
    assert models[0]["capabilities"]["vision"] is None
    assert models[0]["capabilities"]["structured_output"] is None
    assert models[0]["capabilities"]["source"] == "unknown"
    for token in ("next", {}, False):
        with pytest.raises(ProviderError):
            model_metadata({**raw, "nextPageToken": token}, "gemini")
    with pytest.raises(ProviderError):
        model_metadata({"models": [{"name": "models/../../other"}]}, "gemini")


@pytest.mark.parametrize("limit", ["request", "response", "frame"])
def test_bounded_wire_and_response_limits(limit):
    async def run():
        stream = Chunks(
            [b"x" * (2 * 1024 * 1024 + 1)]
            if limit == "response"
            else [b"data: " + b"x" * (1024 * 1024 + 1)]
        )
        h = NativeHarness(lambda _: httpx.Response(200, stream=stream))
        with pytest.raises(ProviderError):
            if limit == "request":
                await GeminiAdapter(h).generate_text(
                    replace(PROMPT, messages=(ChatMessage("user", "x" * (1024 * 1024)),))
                )
            elif limit == "response":
                await GeminiAdapter(h).generate_text(PROMPT)
            else:
                _ = [d async for d in GeminiAdapter(h).stream_text(PROMPT)]
        if limit == "request":
            assert not h.calls
        else:
            assert stream.closed and len(h.calls) == 1

    asyncio.run(run())


@pg
@pytest.mark.parametrize("streaming", [False, True])
def test_pg_native_header_fixed_ip_model_path_and_cleanup(streaming, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("HTTPS_PROXY", "http://unrelated.invalid:8080")

    async def run():
        async with pg_context(provider_type="gemini", base_url="https://chosen.test/v1beta") as (
            store,
            owner,
            cid,
        ):
            sent = []

            def respond(wire):
                expected = "streamGenerateContent?alt=sse" if streaming else "generateContent"
                assert str(wire.url) == "https://8.8.8.8/v1beta/models/selected-model:" + expected
                assert (
                    wire.headers["Host"] == "chosen.test"
                    and wire.extensions["sni_hostname"] == "chosen.test"
                )
                assert wire.headers["x-goog-api-key"] == KEY and "Authorization" not in wire.headers
                assert "x-api-key" not in wire.headers and "key=" not in str(wire.url)
                sent.append(wire)
                return (
                    httpx.Response(200, stream=Chunks([frame(result())]))
                    if streaming
                    else httpx.Response(200, json=result())
                )

            async with build_connection_provider_gateway(
                store, request_for(owner, cid), allowed, transport=httpx.MockTransport(respond)
            ) as gateway:
                if streaming:
                    assert [d.text async for d in gateway.stream_text(PROMPT)] == ["ok"]
                else:
                    assert (await gateway.generate_text(PROMPT)).text == "ok"
            assert len(sent) == 1 and "x-goog-api-key" not in sent[0].headers

    asyncio.run(run())


@pg
def test_pg_model_refresh_and_probe_keep_default_denial_and_exact_target(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")

    class Budget:
        async def preflight(self, request):
            pass

        async def authorize_attempt(self, request):
            pass

    async def run():
        async with pg_context(provider_type="gemini", base_url="https://chosen.test/v1beta") as (
            store,
            owner,
            cid,
        ):
            r = request_for(owner, cid, purpose="model_refresh", categories=frozenset({"probe"}))
            calls = []

            def models(wire):
                assert str(wire.url) == "https://8.8.8.8/v1beta/models?pageSize=1000"
                assert (
                    wire.method == "GET"
                    and not wire.content
                    and wire.headers["x-goog-api-key"] == KEY
                )
                calls.append(wire)
                return httpx.Response(
                    200,
                    json={
                        "models": [
                            {
                                "name": "models/selected-model",
                                "edumind_capabilities": {
                                    "streaming": True,
                                    "structured_output": True,
                                    "vision": True,
                                },
                            }
                        ]
                    },
                )

            snapshot = await refresh_models(
                store,
                owner,
                r.route,
                accepted=True,
                operation_id=r.operation_id,
                temporary_handle=None,
                registry=None,
                budget=Budget(),
                transport=httpx.MockTransport(models),
            )
            assert snapshot == await cached_models(store, owner, cid)
            canonical = replace(r.route, model_id="models/selected-model")
            assert (await resolve_capabilities(store, owner, canonical)).vision is True
            assert "x-goog-api-key" not in calls[0].headers
            for data in (
                {"models": [{"name": "models/" + KEY}]},
                {"models": [], "nextPageToken": "not-complete"},
            ):
                with pytest.raises(ProviderError):
                    await refresh_models(
                        store,
                        owner,
                        r.route,
                        accepted=True,
                        operation_id=uuid4(),
                        temporary_handle=None,
                        registry=None,
                        budget=Budget(),
                        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)),
                    )
                assert snapshot == await cached_models(store, owner, cid)

            def probe(wire):
                body = json.loads(wire.content)
                assert body["generationConfig"]["maxOutputTokens"] == 8
                assert "inlineData" not in str(body) and len(body["contents"]) == 1
                assert wire.headers["x-goog-api-key"] == KEY
                calls.append(wire)
                return httpx.Response(200, json=result())

            kwargs = dict(
                accepted=True,
                operation_id=uuid4(),
                temporary_handle=None,
                registry=None,
                budget=Budget(),
                transport=httpx.MockTransport(probe),
            )
            output = await probe_connection(store, owner, r.route, **kwargs)
            assert output["requests"] == 1 and output["model_id"] == r.route.model_id
            assert output["target"] == "https://chosen.test/v1beta" and len(calls) == 2
            assert output["capabilities"]["vision"] is None
            from app.services.provider_probe import UnavailableProbeBudget

            with pytest.raises(CredentialFailure):
                await probe_connection(
                    store, owner, r.route, **{**kwargs, "budget": UnavailableProbeBudget()}
                )
            assert len(calls) == 2

    asyncio.run(run())


@pg
@pytest.mark.parametrize("terminal", ["success", "failure", "cancel"])
def test_pg_temporary_key_destroyed_after_terminal(terminal, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context("temporary", provider_type="gemini") as (store, owner, cid):
            registry = TemporaryCredentialRegistry()
            try:
                r = request_for(owner, cid)
                handle, _ = await TemporaryCredentialService(store, registry).register(
                    owner, cid, 1, r.operation_id, r.purpose, r.route.model_id, {"api_key": KEY}
                )
                r = replace(r, temporary_handle=handle)
                entry = registry._entries[handle]
                sent = []

                def respond(wire):
                    assert wire.headers["x-goog-api-key"] == KEY
                    sent.append(wire)
                    return (
                        httpx.Response(503)
                        if terminal == "failure"
                        else httpx.Response(200, json=result())
                    )

                try:
                    async with build_connection_provider_gateway(
                        store, r, allowed, registry=registry, transport=httpx.MockTransport(respond)
                    ) as gateway:
                        await gateway.generate_text(PROMPT)
                        if terminal == "cancel":
                            raise asyncio.CancelledError
                except (ProviderError, asyncio.CancelledError):
                    assert terminal != "success"
                assert len(sent) == 1 and "x-goog-api-key" not in sent[0].headers
                assert (
                    handle not in registry._entries and not entry.alive and not any(entry.payload)
                )
                with pytest.raises(CredentialFailure):
                    async with build_connection_provider_gateway(
                        store, r, allowed, registry=registry, transport=httpx.MockTransport(respond)
                    ):
                        pytest.fail("used handle reopened")
                assert len(sent) == 1
            finally:
                await registry.close()

    asyncio.run(run())


@pg
def test_pg_exact_image_authorization_and_budget_rejection(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def run():
        async with pg_context(provider_type="gemini") as (store, owner, cid):
            r, prompt = media_request(
                request_for(owner, cid, categories=frozenset({"content_for_review"}))
            )
            calls = []

            def respond(wire):
                calls.append(wire)
                assert (
                    base64.b64decode(
                        json.loads(wire.content)["contents"][-1]["parts"][-1]["inlineData"]["data"]
                    )
                    == IMAGE.data
                )
                return httpx.Response(200, json=result())

            async with build_connection_provider_gateway(
                store, r, allowed, transport=httpx.MockTransport(respond)
            ) as gateway:
                assert (await gateway.generate_text(prompt)).text == "ok"

            async def deny(request):
                raise CredentialFailure("BUDGET_NOT_AUTHORIZED")

            async with build_connection_provider_gateway(
                store, r, deny, transport=httpx.MockTransport(respond)
            ) as gateway:
                with pytest.raises(CredentialFailure):
                    await gateway.generate_text(prompt)
            assert len(calls) == 1

    asyncio.run(run())
