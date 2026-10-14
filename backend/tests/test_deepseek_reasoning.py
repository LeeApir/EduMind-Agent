"""Explicit reasoning configuration, total-token accounting and strategy preparation."""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

from app.core.config import ProviderSettings
from app.core.provider_factory import configured_provider_adapter
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.deepseek_responses import DeepSeekResponsesAdapter, _request_body
from app.services.provider_gateway import ChatMessage, ProviderError, StructuredRequest, TextRequest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_t040_diagnostics as execution  # noqa: E402
import t040_reasoning_check as strategy  # noqa: E402


def settings_guard():
    settings = ProviderSettings("https://api.deepseek.test", "synthetic-secret", "deepseek-flash")
    guard = ProviderTargetGuard(settings.base_url, TargetPolicy(), resolver=lambda *_: ("8.8.8.8",))
    return settings, guard


@pytest.mark.parametrize("structured", [False, True])
def test_explicit_high_uses_same_adapter_and_total_output_bound(structured, monkeypatch):
    observed = []

    def send(request):
        body = json.loads(request.content)
        observed.append(body)
        assert body["reasoning"] == {"effort": "high"}
        assert body["max_output_tokens"] == 8192
        assert request.headers["Host"] == "api.deepseek.test"
        assert request.extensions["sni_hostname"] == "api.deepseek.test"
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "deepseek-flash",
                "output": [
                    {
                        "type": "reasoning",
                        "content": [{"type": "reasoning_text", "text": "PRIVATE"}],
                    },
                    {
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": '{"ok":true}'}],
                    },
                ],
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 220,
                    "output_tokens_details": {"reasoning_tokens": 200},
                },
            },
        )

    monkeypatch.setenv("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", "responses_json_schema")
    adapter = configured_provider_adapter(*settings_guard(), reasoning_effort="high")
    assert isinstance(adapter, DeepSeekResponsesAdapter)
    adapter._transport = httpx.MockTransport(send)
    prompt = TextRequest((ChatMessage("user", "Synthetic check"),), max_output_tokens=8192)
    result = asyncio.run(
        adapter.generate_structured(StructuredRequest(prompt, {"type": "object"}))
        if structured
        else adapter.generate_text(prompt)
    )
    assert result.usage.output_tokens == 220  # Includes reasoning, never just visible tokens.
    assert "PRIVATE" not in repr(result)
    assert len(observed) == 1


def test_default_body_remains_none_and_invalid_effort_fails_before_dns():
    prompt = TextRequest((ChatMessage("user", "Synthetic"),))
    assert _request_body(prompt)["reasoning"] == {"effort": "none"}
    with pytest.raises(ProviderError):
        DeepSeekResponsesAdapter(*settings_guard(), reasoning_effort="unsupported")
    with pytest.raises(ProviderError):
        _request_body(prompt, reasoning_effort="unsupported")


def test_beta_transport_cannot_silently_ignore_high(monkeypatch):
    monkeypatch.setenv("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", "beta_tools")
    with pytest.raises(ProviderError):
        configured_provider_adapter(*settings_guard(), reasoning_effort="high")


def test_retention_discards_reasoning_text_but_keeps_usage_counts():
    retained = execution.retain_generated_response(
        json.dumps(
            {
                "status": "completed",
                "model": "synthetic",
                "usage": {"output_tokens": 200, "output_tokens_details": {"reasoning_tokens": 180}},
                "output": [
                    {"type": "reasoning", "content": "PRIVATE_REASONING"},
                    {"type": "message", "content": [{"type": "output_text", "text": "visible"}]},
                ],
            }
        ).encode()
    )
    assert "PRIVATE_REASONING" not in json.dumps(retained)
    assert retained["usage"]["output_tokens"] == 200


@pytest.mark.parametrize(
    "count,expected", [(180, 180), (0, 0), (None, None), (True, None), (-1, None), (201, None)]
)
def test_reasoning_subcount_is_numeric_and_bounded(count, expected):
    data = json.dumps({"usage": {"output_tokens_details": {"reasoning_tokens": count}}}).encode()
    assert execution.reasoning_count(data, 200) == expected
    assert execution.reasoning_count(b"{}", 200) is None


def test_two_case_strategy_does_not_reuse_old_approval_or_claim_diagnostic_pass():
    bodies, plan = asyncio.run(strategy.proposed())
    assert plan["requested_total_calls"] == 2
    assert [row["historical_case_id"] for row in plan["groups"][0]["slots"]] == [
        "linked-list-concept:explanation:1",
        "correct-list-concept",
    ]
    assert plan["provider_requests_authorized"] == 0 and not plan["old_budget_transferred"]
    assert not plan["formal_quality_authorized"] and not plan["automatic_next_round"]
    previous = json.loads(
        (strategy.ROOT / "docs/acceptance/phase-1-t040-deepseek-v2/requests.json").read_text()
    )
    for slot, prior in (
        ("reasoning_check:01", "error_detection:01"),
        ("reasoning_check:02", "correct_control:01"),
    ):
        body = bodies[slot]
        assert body["input"] == previous[prior]["input"]
        assert body["text"] == previous[prior]["text"]
        assert body["reasoning"] == {"effort": "high"}
        assert body["max_output_tokens"] == 8192
    assert (
        plan["groups"][0]["computed_reservation_micro_cny"]
        <= plan["requested_total_cost_micro_cny"]
    )
