"""Acceptance accounting must cap failed calls and refuse implicit billing."""

import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from app.core.config import ProviderSettings
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.provider_gateway import (
    P0_DEFAULT_MAX_OUTPUT_TOKENS,
    ProviderError,
    ProviderErrorCode,
    StructuredResult,
    TokenUsage,
)

SCRIPT = Path(__file__).resolve().parents[2] / "docs/acceptance/run_mvp02_acceptance.py"
spec = importlib.util.spec_from_file_location("stage_acceptance", SCRIPT)
assert spec is not None and spec.loader is not None
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def test_repair_diagnostic_has_six_calls_without_retries_or_stage_claim():
    from tests.resource_quality import BoundedGateway, provider_report

    class FailingGateway:
        async def generate_structured(self, request, *, retry_safe=False):
            assert retry_safe is False
            assert request.prompt.max_output_tokens == 4096
            raise ProviderError(ProviderErrorCode.TIMEOUT)

    report = asyncio.run(provider_report(BoundedGateway(FailingGateway(), limit=6),
                                         "mock-model", repair=True))
    assert report["provider_calls"] == report["schema_sample_count"] == 6
    assert report["structured_transport"] == "responses_json_schema"
    assert report["retries"] == report["corrections"] == 0
    assert report["stage_gate_passed"] is False
    assert all(not item["valid"] for item in report["schema_samples"])


def test_array_diagnostic_has_three_identical_prompts_and_no_quality_claim():
    from tests.resource_quality import BoundedGateway, provider_report

    requests = []

    class FakeGateway:
        async def generate_structured(self, request, *, retry_safe=False):
            assert retry_safe is False
            requests.append(request)
            raise ProviderError(ProviderErrorCode.TIMEOUT)

    report = asyncio.run(provider_report(BoundedGateway(FakeGateway(), limit=3),
                                         "mock", array=True))
    assert len(requests) == report["provider_calls"] == 3
    assert requests[0] == requests[1] == requests[2]
    assert requests[0].prompt.max_output_tokens == 4096
    assert report["stage_gate_passed"] is False
    assert [item["id"] for item in report["schema_samples"]] == [
        "array:explanation:1", "array:explanation:2", "array:explanation:3"
    ]


def test_review_diagnostic_preserves_failed_denominator_and_three_call_limit():
    from tests.resource_quality import BoundedGateway, provider_report

    class FakeGateway:
        async def generate_structured(self, request, *, retry_safe=False):
            assert retry_safe is False
            raise ProviderError(ProviderErrorCode.TIMEOUT)

    report = asyncio.run(provider_report(BoundedGateway(FakeGateway(), limit=3),
                                         "mock", review_diagnostic=True))
    assert report["provider_calls"] == 3
    assert report["stage_gate_passed"] is False
    assert len(report["review_samples"]) == 3
    assert all(item["model_id"] is None for item in report["review_samples"])
    assert not any(item.get("detected", item.get("correctly_passed", False))
                   for item in report["review_samples"])


def test_safety_diagnostic_keeps_original_classification_and_failed_denominator():
    from tests.resource_quality import BoundedGateway, provider_report

    class FakeGateway:
        async def generate_structured(self, request, *, retry_safe=False):
            assert retry_safe is False
            raise ProviderError(ProviderErrorCode.TIMEOUT)

    report = asyncio.run(provider_report(BoundedGateway(FakeGateway(), limit=3),
                                         "mock", safety_diagnostic=True))
    assert report["provider_calls"] == 3
    assert report["mode"] == "safety-diagnostic"
    assert report["stage_gate_passed"] is False
    assert [item["id"] for item in report["review_samples"]] == [
        "list-traversal-stop", "list-delete-head", "correct-array"
    ]
    assert not any(item.get("detected", item.get("correctly_passed", False))
                   for item in report["review_samples"])


def test_safety_detection_does_not_relabel_fact_or_count_unavailable_review():
    from tests.resource_quality import detection

    verdict = {"verdict": "reject", "issues": [
        {"area": "fact", "severity": "severe", "message": "Memory access is unsafe."}
    ]}
    assert not detection(verdict, expected_area="code_safety", model_id="mock", local=False)
    verdict["issues"][0]["area"] = "code_safety"
    assert detection(verdict, expected_area="code_safety", model_id="mock", local=False)
    assert not detection(verdict, expected_area="code_safety", model_id=None, local=False)


def test_quality_progress_is_content_free_and_does_not_bypass_budget(capsys):
    from app.services.provider_gateway import StructuredRequest, TextRequest
    from tests.resource_quality import BoundedGateway

    class FakeGateway:
        async def generate_structured(self, request, *, retry_safe=False):
            raise ProviderError(ProviderErrorCode.TIMEOUT)

    bounded = BoundedGateway(FakeGateway(), limit=1, progress=True)
    request = StructuredRequest(TextRequest(messages=()), {})
    with pytest.raises(ProviderError):
        asyncio.run(bounded.generate_structured(request))
    with pytest.raises(RuntimeError, match="BENCHMARK_CALL_LIMIT"):
        asyncio.run(bounded.generate_structured(request))
    assert capsys.readouterr().err == "Provider attempt 1/1\nAttempt 1: TIMEOUT\n"
    assert bounded.calls == 1


def test_objective_diagnostic_is_three_calls_not_a_full_quality_gate():
    from tests.resource_quality import BoundedGateway, provider_report

    class FakeGateway:
        async def generate_structured(self, request, *, retry_safe=False):
            assert retry_safe is False
            raise ProviderError(ProviderErrorCode.TIMEOUT)

    report = asyncio.run(provider_report(BoundedGateway(FakeGateway(), limit=3),
                                         "mock", objective_diagnostic=True))
    assert report["provider_calls"] == report["schema_sample_count"] == 3
    assert report["mode"] == "objective-diagnostic"
    assert report["stage_gate_passed"] is False


def test_quality_attempts_record_only_numeric_text_counts_on_failure_and_success():
    from app.services.provider_gateway import (
        JsonExtraDataKind,
        JsonSyntaxReason,
        OutputFailureReason,
        OutputTextCounts,
    )
    from tests.resource_quality import BoundedGateway

    class FakeGateway:
        async def generate_structured(self, request, *, retry_safe=False):
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT,
                                output_failure_reason=OutputFailureReason.STRUCTURED_JSON_INVALID,
                                json_syntax_reason=JsonSyntaxReason.EXTRA_DATA,
                                json_extra_data_kind=JsonExtraDataKind.JSON_VALUE_SUFFIX,
                                output_text_counts=OutputTextCounts(2, 3))

    from app.services.provider_gateway import StructuredRequest, TextRequest

    bounded = BoundedGateway(FakeGateway(), limit=2)
    request = StructuredRequest(TextRequest(messages=()), {})
    with pytest.raises(ProviderError):
        asyncio.run(bounded.generate_structured(request))
    # Use the same valid request with a separate successful fake.
    class SuccessfulGateway:
        async def generate_structured(self, request, *, retry_safe=False):
            return StructuredResult({}, "mock", output_text_counts=OutputTextCounts(1, 2))

    bounded.gateway = SuccessfulGateway()
    asyncio.run(bounded.generate_structured(request))
    assert bounded.attempts[0]["output_text_counts"] == {"messages": 2, "blocks": 3}
    assert bounded.attempts[0]["json_extra_data_kind"] == "JSON_VALUE_SUFFIX"
    assert bounded.attempts[1]["output_text_counts"] == {"messages": 1, "blocks": 2}


def test_quality_budget_matches_production_and_review_failures_remain_diagnostic():
    from tests.resource_quality import BoundedGateway, provider_report

    class OfflineFailingGateway:
        def __init__(self):
            self.requests = []

        async def generate_structured(self, request, *, retry_safe=False):
            assert retry_safe is False
            self.requests.append(request)
            raise ProviderError(ProviderErrorCode.TIMEOUT, usage=TokenUsage(10, 20))

    fake = OfflineFailingGateway()
    bounded = BoundedGateway(fake)
    report = asyncio.run(provider_report(bounded, "mock-model"))
    assert len(fake.requests) == 86
    assert all(
        request.prompt.max_output_tokens == P0_DEFAULT_MAX_OUTPUT_TOKENS
        for request in fake.requests[:60]
    )
    assert report["generation_max_output_tokens"] == report["review_max_output_tokens"] == 4096
    assert len(report["provider_attempts"]) == 86
    assert all(
        attempt["usage"] == {"input_tokens": 10, "output_tokens": 20}
        and attempt["error_code"] == "TIMEOUT"
        for attempt in report["provider_attempts"]
    )
    model_reviews = [sample for sample in report["review_samples"] if not sample["local_gate"]]
    assert len(model_reviews) == 26
    assert all(len(sample["provider_attempts"]) == 1 for sample in model_reviews)
    assert report["stage_gate_passed"] is False


@pytest.mark.parametrize("usage", [TokenUsage(-1, 1), TokenUsage(True, 1), "sensitive"])
def test_error_usage_diagnostics_reject_non_numeric_values(usage):
    with pytest.raises(ValueError, match="Invalid token usage"):
        ProviderError(ProviderErrorCode.INVALID_OUTPUT, usage=usage)


probe_spec = importlib.util.spec_from_file_location(
    "strict_probe", SCRIPT.with_name("probe_responses_strict.py")
)
assert probe_spec is not None and probe_spec.loader is not None
strict_probe = importlib.util.module_from_spec(probe_spec)
probe_spec.loader.exec_module(strict_probe)

beta_spec = importlib.util.spec_from_file_location(
    "beta_probe", SCRIPT.with_name("probe_beta_tools.py")
)
assert beta_spec is not None and beta_spec.loader is not None
beta_probe = importlib.util.module_from_spec(beta_spec)
beta_spec.loader.exec_module(beta_probe)


def test_beta_tool_probe_pins_same_host_and_only_returns_validated_arguments():
    import json

    from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest

    def respond(request):
        assert str(request.url) == "https://8.8.8.8/beta/chat/completions"
        assert request.headers["Host"] == "api.deepseek.com"
        assert request.extensions["sni_hostname"] == "api.deepseek.com"
        body = json.loads(request.content)
        assert body["tools"][0]["function"]["strict"] is True
        assert body["thinking"] == {"type": "disabled"}
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
                                        "arguments": '{"answer":"expected"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        )

    settings = ProviderSettings(
        base_url="https://api.deepseek.com/beta", api_key="test-secret", model="mock-model"
    )
    guard = ProviderTargetGuard(
        settings.base_url, TargetPolicy(), resolver=lambda host, port: ("8.8.8.8",)
    )
    ledger = []
    adapter = beta_probe.BetaToolProbe(
        settings, guard, ledger=ledger, transport=httpx.MockTransport(respond)
    )
    request = StructuredRequest(
        TextRequest(messages=(ChatMessage("user", "Public probe"),)),
        {
            "type": "object",
            "properties": {"answer": {"enum": ["expected"]}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    )
    for _ in range(4):
        assert asyncio.run(adapter.generate_structured(request)).value == {"answer": "expected"}
    with pytest.raises(RuntimeError, match="BUDGET_EXHAUSTED"):
        asyncio.run(adapter.generate_structured(request))
    assert ledger == [{"http_status": 200}] * 4


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"finish_reason": "stop", "message": {"content": "not a tool"}}]},
    ],
)
def test_beta_probe_rejects_missing_or_non_tool_output(payload):
    with pytest.raises(ProviderError):
        beta_probe.tool_arguments(payload)


def test_beta_constant_projection_keeps_original_business_constraints():
    from jsonschema import Draft202012Validator

    from app.agents.learning_resource_schema import resource_output_schema

    for kind in ("explanation", "code", "exercise"):
        original = resource_output_schema(kind)
        projected = beta_probe.typed_constants(original)
        assert "const" in original["properties"]["resource_type"]
        assert projected["properties"]["resource_type"] == {"type": "string", "enum": [kind]}
        validator = Draft202012Validator(projected["properties"]["resource_type"])
        assert validator.is_valid(kind)
        assert not validator.is_valid("wrong")
    boolean = beta_probe.typed_constants({"const": True})
    assert Draft202012Validator(boolean).is_valid(True)
    assert not Draft202012Validator(boolean).is_valid(False)


@pytest.mark.parametrize("existing", [False, True])
def test_strict_probe_requires_opt_in_and_preserves_existing_evidence(
    monkeypatch, tmp_path, existing
):
    report = tmp_path / "report.json"
    args = ["probe", "--output", str(report)]
    if existing:
        report.write_text("existing evidence")
        args.append("--confirm-billable")
    factory = Mock(side_effect=AssertionError("No network before guards"))
    monkeypatch.setattr(strict_probe, "build_server_provider_gateway", factory)
    monkeypatch.setattr("sys.argv", args)
    with pytest.raises(SystemExit):
        strict_probe.main()
    factory.assert_not_called()
    if existing:
        assert report.read_text() == "existing evidence"
    else:
        assert not report.exists()


@pytest.mark.parametrize("strict", [None, True])
def test_strict_probe_injects_flag_without_weakening_local_validation(strict):
    import json

    from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest

    def respond(request):
        body = json.loads(request.content)
        if strict is None:
            assert "strict" not in body["text"]["format"]
        else:
            assert body["text"]["format"]["strict"] is True
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
                        "content": [{"type": "output_text", "text": '{"answer":"wrong"}'}],
                    }
                ],
            },
        )

    settings = ProviderSettings(
        base_url="https://provider.test", api_key="test-secret", model="mock-model"
    )
    guard = ProviderTargetGuard(
        settings.base_url, TargetPolicy(), resolver=lambda host, port: ("8.8.8.8",)
    )
    ledger = []
    adapter = strict_probe.StrictProbeAdapter(
        settings, guard, strict=strict, ledger=ledger, transport=httpx.MockTransport(respond)
    )
    request = StructuredRequest(
        TextRequest(messages=(ChatMessage("user", "Public probe"),)),
        {
            "type": "object",
            "properties": {"answer": {"enum": ["expected"]}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    )
    for _ in range(3):
        with pytest.raises(ProviderError) as caught:
            asyncio.run(adapter.generate_structured(request))
        assert caught.value.schema_keyword == "enum"
    with pytest.raises(RuntimeError, match="BUDGET_EXHAUSTED"):
        asyncio.run(adapter.generate_structured(request))
    assert len(ledger) == 3


def test_billable_confirmation_is_required_before_creating_real_gateway(monkeypatch, tmp_path):
    factory = Mock(side_effect=AssertionError("No Provider without opt-in"))
    monkeypatch.setattr(acceptance, "build_server_provider_gateway", factory)
    monkeypatch.setattr("sys.argv", ["acceptance", "--output", str(tmp_path / "report.json")])
    with pytest.raises(SystemExit, match="confirmation"):
        acceptance.main()
    factory.assert_not_called()


def test_attempt_budget_cannot_be_reset_by_provider_failures():
    class Adapter:
        async def generate_structured(self, request):
            raise ProviderError(ProviderErrorCode.TIMEOUT)

    async def scenario():
        ledger = []
        bounded = acceptance.BoundedAdapter(Adapter(), ledger)
        for _ in range(30):
            with pytest.raises(ProviderError):
                await bounded.generate_structured(None)
        with pytest.raises(RuntimeError, match="BUDGET_EXHAUSTED"):
            await bounded.generate_structured(None)
        assert len(ledger) == 30
        assert all(entry == {"kind": "structured", "error_code": "TIMEOUT"} for entry in ledger)

    asyncio.run(scenario())


def test_call_metadata_and_latency_percentiles_do_not_claim_provider_usage_or_money():
    class Adapter:
        async def generate_structured(self, request):
            return StructuredResult({}, "mock-model")

    async def scenario():
        ledger = []
        await acceptance.BoundedAdapter(Adapter(), ledger).generate_structured(None)
        assert ledger == [{"kind": "structured", "model": "mock-model"}]

    asyncio.run(scenario())
    latency = acceptance.distribution(list(range(1, 101)), 1)
    assert latency["p95_ms"] == 95 and latency["p99_ms"] == 99
    assert latency["samples"] == 101 and latency["failure_rate"] == 1 / 101
