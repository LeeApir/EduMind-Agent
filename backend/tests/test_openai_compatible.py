"""Non-streaming adapter contract exercised only through mock HTTP transport."""

import asyncio
import json
from collections.abc import Sequence

import httpx
import pytest

from app.core.config import ProviderSettings
from app.core.provider_factory import build_default_provider_gateway
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.openai_compatible import OpenAICompatibleAdapter
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    TextRequest,
    TokenUsage,
)


def resolver(_host: str, _port: int) -> Sequence[str]:
    return ("8.8.8.8",)


def adapter(handler: httpx.MockTransport) -> OpenAICompatibleAdapter:
    settings = ProviderSettings(
        base_url="https://api.provider.test/v1", api_key="test-secret", model="server-model"
    )
    guard = ProviderTargetGuard(settings.base_url, TargetPolicy(), resolver=resolver)
    return OpenAICompatibleAdapter(settings, guard, transport=handler)


def prompt() -> TextRequest:
    return TextRequest(
        messages=(ChatMessage(role="user", content="Explain a linked list"),),
        max_output_tokens=300,
        temperature=0.4,
    )


def completion(content: str = "A linked list has nodes.") -> dict[str, object]:
    return {
        "model": "server-model-v2",
        "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 9},
    }


def test_text_request_uses_pinned_ip_original_host_sni_and_neutral_result() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert str(request.url) == "https://8.8.8.8/v1/chat/completions"
        assert request.headers["Host"] == "api.provider.test"
        assert request.extensions["sni_hostname"] == "api.provider.test"
        assert request.headers["Authorization"] == "Bearer test-secret"
        body = json.loads(request.content)
        assert body == {
            "model": "server-model",
            "messages": [{"role": "user", "content": "Explain a linked list"}],
            "stream": False,
            "max_completion_tokens": 300,
            "temperature": 0.4,
        }
        return httpx.Response(200, json=completion())

    result = asyncio.run(adapter(httpx.MockTransport(respond)).generate_text(prompt()))
    assert result.text == "A linked list has nodes."
    assert result.model_id == "server-model-v2"
    assert result.usage == TokenUsage(input_tokens=8, output_tokens=9)
    assert calls == 1


def test_structured_request_sends_json_schema_and_validates_result() -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "edumind_result", "schema": schema, "strict": True},
        }
        return httpx.Response(200, json=completion('{"answer":"linked nodes"}'))

    result = asyncio.run(
        adapter(httpx.MockTransport(respond)).generate_structured(
            StructuredRequest(prompt=prompt(), json_schema=schema)
        )
    )
    assert result.value == {"answer": "linked nodes"}
    assert result.usage == TokenUsage(input_tokens=8, output_tokens=9)


def test_authentication_failure_never_exposes_vendor_body_or_key() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="test-secret vendor detail")

    with pytest.raises(ProviderError) as raised:
        asyncio.run(adapter(httpx.MockTransport(respond)).generate_text(prompt()))
    assert raised.value.code == ProviderErrorCode.AUTHENTICATION_FAILED
    assert not raised.value.retryable
    assert "test-secret" not in str(raised.value)
    assert "vendor detail" not in str(raised.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "server-model", "choices": []},
        {
            "model": "server-model",
            "choices": [{"finish_reason": "length", "message": {"content": "cut"}}],
        },
        {
            "model": "server-model",
            "choices": [{"finish_reason": "stop", "message": {"content": None}}],
        },
        {
            "model": "server-model",
            "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
            "usage": {"prompt_tokens": "bad"},
        },
    ],
)
def test_malformed_response_is_safe_invalid_output(payload: dict[str, object]) -> None:
    with pytest.raises(ProviderError) as raised:
        asyncio.run(
            adapter(
                httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
            ).generate_text(prompt())
        )
    assert raised.value.code == ProviderErrorCode.INVALID_OUTPUT


def test_non_json_and_schema_mismatch_are_invalid_output() -> None:
    with pytest.raises(ProviderError) as raised:
        asyncio.run(
            adapter(
                httpx.MockTransport(lambda _request: httpx.Response(200, text="not-json"))
            ).generate_text(prompt())
        )
    assert raised.value.code == ProviderErrorCode.INVALID_OUTPUT

    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
    with pytest.raises(ProviderError) as raised:
        asyncio.run(
            adapter(
                httpx.MockTransport(
                    lambda _request: httpx.Response(200, json=completion('{"answer":"wrong"}'))
                )
            ).generate_structured(StructuredRequest(prompt=prompt(), json_schema=schema))
        )
    assert raised.value.code == ProviderErrorCode.INVALID_OUTPUT


def test_external_schema_reference_is_rejected_before_http() -> None:
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=completion())

    schema = {"$ref": "https://169.254.169.254/schema.json"}
    with pytest.raises(ProviderError) as raised:
        asyncio.run(
            adapter(httpx.MockTransport(respond)).generate_structured(
                StructuredRequest(prompt=prompt(), json_schema=schema)
            )
        )
    assert raised.value.code == ProviderErrorCode.INVALID_OUTPUT
    assert calls == 0


def test_redirect_is_not_followed_even_when_location_is_private() -> None:
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest"})

    with pytest.raises(ProviderError) as raised:
        asyncio.run(adapter(httpx.MockTransport(respond)).generate_text(prompt()))
    assert raised.value.code == ProviderErrorCode.INVALID_TARGET
    assert calls == 1


def test_dns_change_to_private_is_blocked_before_mock_http() -> None:
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=completion())

    settings = ProviderSettings(
        base_url="https://api.provider.test/v1", api_key="test-secret", model="server-model"
    )
    guard = ProviderTargetGuard(
        settings.base_url, TargetPolicy(), resolver=lambda _host, _port: ("10.0.0.1",)
    )
    with pytest.raises(ProviderError) as raised:
        asyncio.run(
            OpenAICompatibleAdapter(
                settings, guard, transport=httpx.MockTransport(respond)
            ).generate_text(prompt())
        )
    assert raised.value.code == ProviderErrorCode.INVALID_TARGET
    assert calls == 0


def test_default_gateway_composes_single_server_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUMIND_PROVIDER_BASE_URL", "https://8.8.8.8/v1")
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "test-secret")
    monkeypatch.setenv("EDUMIND_PROVIDER_MODEL", "server-model")
    monkeypatch.delenv("EDUMIND_PROVIDER_DEPLOYMENT", raising=False)
    monkeypatch.delenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", raising=False)
    gateway = build_default_provider_gateway()
    assert isinstance(gateway._adapter, OpenAICompatibleAdapter)
