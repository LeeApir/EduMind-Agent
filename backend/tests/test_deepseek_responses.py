"""DeepSeek Responses non-streaming contract through mock HTTP only."""

import asyncio
import json
from collections.abc import Sequence

import httpx
import pytest

from app.core.config import ProviderSettings
from app.core.provider_factory import build_default_provider_gateway
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.deepseek_responses import DeepSeekResponsesAdapter
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


def adapter(handler: httpx.MockTransport) -> DeepSeekResponsesAdapter:
    settings = ProviderSettings(
        base_url="https://api.deepseek.test", api_key="test-secret", model="deepseek-flash"
    )
    guard = ProviderTargetGuard(settings.base_url, TargetPolicy(), resolver=resolver)
    return DeepSeekResponsesAdapter(settings, guard, transport=handler)


def prompt() -> TextRequest:
    return TextRequest(
        messages=(ChatMessage(role="user", content="Explain a linked list"),),
        max_output_tokens=300,
        temperature=0.4,
    )


def response(content: str = "A linked list has nodes.") -> dict[str, object]:
    return {
        "object": "response",
        "status": "completed",
        "model": "deepseek-flash",
        "output": [
            {
                "type": "reasoning",
                "status": "completed",
                "content": [{"type": "reasoning_text", "text": "private reasoning"}],
            },
            {
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content}],
            },
        ],
        "usage": {"input_tokens": 8, "output_tokens": 9, "total_tokens": 17},
    }


def test_text_request_uses_responses_pinned_ip_host_sni_and_neutral_result() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert str(request.url) == "https://8.8.8.8/responses"
        assert request.headers["Host"] == "api.deepseek.test"
        assert request.extensions["sni_hostname"] == "api.deepseek.test"
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert json.loads(request.content) == {
            "model": "deepseek-flash",
            "input": [{"role": "user", "content": "Explain a linked list"}],
            "stream": False,
            "reasoning": {"effort": "none"},
            "max_output_tokens": 300,
            "temperature": 0.4,
        }
        return httpx.Response(200, json=response())

    result = asyncio.run(adapter(httpx.MockTransport(respond)).generate_text(prompt()))
    assert result.text == "A linked list has nodes."
    assert result.model_id == "deepseek-flash"
    assert result.usage == TokenUsage(input_tokens=8, output_tokens=9)
    assert calls == 1


def test_unspecified_output_limit_uses_bounded_p0_nonthinking_defaults() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["reasoning"] == {"effort": "none"}
        assert body["max_output_tokens"] == 4096
        return httpx.Response(200, json=response())

    request = TextRequest(messages=(ChatMessage(role="user", content="Explain a queue"),))
    result = asyncio.run(adapter(httpx.MockTransport(respond)).generate_text(request))
    assert result.model_id == "deepseek-flash"


def test_structured_request_uses_text_json_schema_and_validates_result() -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["text"] == {
            "format": {
                "type": "json_schema",
                "name": "edumind_result",
                "schema": schema,
            }
        }
        assert "response_format" not in body
        return httpx.Response(200, json=response('{"answer":"linked nodes"}'))

    result = asyncio.run(
        adapter(httpx.MockTransport(respond)).generate_structured(
            StructuredRequest(prompt=prompt(), json_schema=schema)
        )
    )
    assert result.value == {"answer": "linked nodes"}
    assert result.usage == TokenUsage(input_tokens=8, output_tokens=9)


def test_structured_request_defaults_temperature_without_overriding_explicit_value() -> None:
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = json.loads(request.content)
        assert body["temperature"] == (0.0 if calls == 1 else 0.7)
        return httpx.Response(200, json=response('{"ok":true}'))

    subject = adapter(httpx.MockTransport(respond))
    default_request = StructuredRequest(
        prompt=TextRequest(messages=(ChatMessage(role="user", content="Return JSON"),)),
        json_schema=schema,
    )
    explicit_request = StructuredRequest(
        prompt=TextRequest(
            messages=(ChatMessage(role="user", content="Return JSON"),), temperature=0.7
        ),
        json_schema=schema,
    )
    assert asyncio.run(subject.generate_structured(default_request)).value == {"ok": True}
    assert asyncio.run(subject.generate_structured(explicit_request)).value == {"ok": True}
    assert calls == 2


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
        {"model": "deepseek-flash", "status": "completed", "output": []},
        {**response(), "status": "incomplete"},
        {
            **response(),
            "output": [
                {
                    "type": "message",
                    "status": "incomplete",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "cut"}],
                }
            ],
        },
        {**response(), "usage": {"input_tokens": "bad"}},
    ],
)
def test_malformed_or_incomplete_response_is_safe_invalid_output(
    payload: dict[str, object],
) -> None:
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
                    lambda _request: httpx.Response(
                        200, json=response('{"answer":"wrong"}')
                    )
                )
            ).generate_structured(StructuredRequest(prompt=prompt(), json_schema=schema))
        )
    assert raised.value.code == ProviderErrorCode.INVALID_OUTPUT


def test_external_schema_reference_is_rejected_before_http() -> None:
    calls = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response())

    with pytest.raises(ProviderError) as raised:
        asyncio.run(
            adapter(httpx.MockTransport(respond)).generate_structured(
                StructuredRequest(
                    prompt=prompt(), json_schema={"$ref": "https://169.254.169.254/schema"}
                )
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
        return httpx.Response(200, json=response())

    settings = ProviderSettings(
        base_url="https://api.deepseek.test", api_key="test-secret", model="deepseek-flash"
    )
    guard = ProviderTargetGuard(
        settings.base_url, TargetPolicy(), resolver=lambda _host, _port: ("10.0.0.1",)
    )
    with pytest.raises(ProviderError) as raised:
        asyncio.run(
            DeepSeekResponsesAdapter(
                settings, guard, transport=httpx.MockTransport(respond)
            ).generate_text(prompt())
        )
    assert raised.value.code == ProviderErrorCode.INVALID_TARGET
    assert calls == 0


def test_default_gateway_composes_only_deepseek_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EDUMIND_PROVIDER_BASE_URL", "https://8.8.8.8")
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "test-secret")
    monkeypatch.setenv("EDUMIND_PROVIDER_MODEL", "deepseek-flash")
    monkeypatch.delenv("EDUMIND_PROVIDER_DEPLOYMENT", raising=False)
    monkeypatch.delenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", raising=False)
    gateway = build_default_provider_gateway()
    assert isinstance(gateway._adapter, DeepSeekResponsesAdapter)
