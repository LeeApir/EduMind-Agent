"""Strict transport is explicit, same-origin, bounded and locally validated."""

import asyncio
import json

import httpx
import pytest

from app.core.config import ProviderSettings
from app.core.provider_factory import configured_provider_adapter
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.deepseek_beta_tools import (
    DeepSeekBetaToolsAdapter,
    tool_arguments,
    typed_constants,
)
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.provider_gateway import (
    ChatMessage,
    OutputFailureReason,
    ProviderError,
    StructuredRequest,
    TextRequest,
)


def settings(host="api.deepseek.com"):
    return ProviderSettings(base_url=f"https://{host}", api_key="test-secret", model="mock-model")


def guard(config):
    return ProviderTargetGuard(config.base_url, TargetPolicy(), resolver=lambda h, p: ("8.8.8.8",))


def prompt():
    return TextRequest(messages=(ChatMessage("user", "Public educational input"),))


@pytest.mark.parametrize("bad_answer", [False, True])
def test_beta_json_transport_keeps_strict_wire_and_original_validation(bad_answer):
    config = settings()
    schema = {
        "type": "object",
        "properties": {"answer": {"const": "expected"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    calls = []

    def respond(request):
        calls.append(request)
        assert str(request.url) == "https://8.8.8.8/beta/chat/completions"
        assert request.headers["Host"] == "api.deepseek.com"
        assert request.extensions["sni_hostname"] == "api.deepseek.com"
        body = json.loads(request.content)
        definition = body["tools"][0]["function"]
        assert definition["strict"] is True
        assert definition["parameters"]["properties"]["answer"] == {
            "type": "string",
            "enum": ["expected"],
        }
        assert "text" not in body
        assert body["tool_choice"]["function"]["name"] == "edumind_result"
        return httpx.Response(
            200,
            json={
                "model": "mock-model",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "edumind_result",
                                        "arguments": json.dumps(
                                            {"answer": "wrong" if bad_answer else "expected"}
                                        ),
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        )

    adapter = DeepSeekBetaToolsAdapter(
        config, guard(config), transport=httpx.MockTransport(respond)
    )
    if bad_answer:
        with pytest.raises(ProviderError) as caught:
            asyncio.run(adapter.generate_structured(StructuredRequest(prompt(), schema)))
        assert caught.value.schema_keyword == "const"
    else:
        assert asyncio.run(
            adapter.generate_structured(StructuredRequest(prompt(), schema))
        ).value == {"answer": "expected"}
    assert len(calls) == 1
    assert schema["properties"]["answer"] == {"const": "expected"}


def test_beta_does_not_change_ordinary_text_endpoint():
    config = settings()

    def respond(request):
        assert str(request.url) == "https://8.8.8.8/responses"
        assert "tools" not in json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "mock-model",
                "output": [
                    {
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "public"}],
                    }
                ],
            },
        )

    adapter = DeepSeekBetaToolsAdapter(
        config, guard(config), transport=httpx.MockTransport(respond)
    )
    assert asyncio.run(adapter.generate_text(prompt())).text == "public"


def test_factory_is_opt_in_and_refuses_cross_host_or_unknown_mode(monkeypatch):
    config = settings()
    monkeypatch.delenv("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", raising=False)
    assert isinstance(configured_provider_adapter(config, guard(config)), DeepSeekResponsesAdapter)
    monkeypatch.setenv("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", "beta_tools")
    assert isinstance(configured_provider_adapter(config, guard(config)), DeepSeekBetaToolsAdapter)
    other = settings("custom-provider.test")
    with pytest.raises(ProviderError):
        configured_provider_adapter(other, guard(other))
    monkeypatch.setenv("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", "typo")
    with pytest.raises(ProviderError):
        configured_provider_adapter(config, guard(config))


@pytest.mark.parametrize(
    "schema", [{"const": "x", "type": "integer"}, {"const": "x", "enum": ["y"]}]
)
def test_projection_cannot_drop_conflicting_original_constraints(schema):
    with pytest.raises(ProviderError):
        typed_constants(schema)


@pytest.mark.parametrize("status", [302, 400, 401, 429, 500])
def test_beta_failure_never_falls_back_or_follows_redirect(status):
    config = settings()
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://untrusted.test"})

    adapter = DeepSeekBetaToolsAdapter(
        config, guard(config), transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ProviderError):
        asyncio.run(adapter.generate_structured(StructuredRequest(prompt(), {"type": "object"})))
    assert len(calls) == 1
    assert calls[0].url.path == "/beta/chat/completions"


def test_beta_preserves_actual_usage_and_rejects_wrong_function():
    payload = {
        "model": "mock-model",
        "usage": {"prompt_tokens": 8, "completion_tokens": 9},
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "edumind_result", "arguments": "{}"},
                        }
                    ],
                },
            }
        ],
    }
    result = tool_arguments(payload)
    assert result.usage.input_tokens == 8
    assert result.usage.output_tokens == 9
    payload["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "execute_code"
    with pytest.raises(ProviderError):
        tool_arguments(payload)


def test_beta_oversized_output_is_rejected_without_fallback():
    config = settings()
    adapter = DeepSeekBetaToolsAdapter(
        config,
        guard(config),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))
        ),
    )
    with pytest.raises(ProviderError):
        asyncio.run(adapter.generate_structured(StructuredRequest(prompt(), {"type": "object"})))


def test_implicit_string_enum_projection_preserves_review_schema():
    from app.agents.review_schema import review_output_schema

    original = review_output_schema()
    projected = typed_constants(original)
    assert "type" not in original["properties"]["verdict"]
    assert projected["properties"]["verdict"]["type"] == "string"
    assert projected["properties"]["verdict"]["enum"] == original["properties"]["verdict"]["enum"]


@pytest.mark.parametrize(
    "finish,reason",
    [
        ("length", OutputFailureReason.OUTPUT_TOKEN_LIMIT),
        ("content_filter", OutputFailureReason.RESPONSE_INCOMPLETE),
        ("secret-sensitive-vendor-value", OutputFailureReason.RESPONSE_INCOMPLETE),
    ],
)
def test_beta_incomplete_output_has_content_free_reason_and_actual_usage(finish, reason):
    payload = {
        "choices": [{"finish_reason": finish, "message": {"content": "secret-generated-content"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4096},
    }
    with pytest.raises(ProviderError) as caught:
        tool_arguments(payload)
    error = caught.value
    assert error.output_failure_reason == reason
    assert error.usage.output_tokens == 4096
    assert "secret" not in str(error) and "secret" not in repr(error)
