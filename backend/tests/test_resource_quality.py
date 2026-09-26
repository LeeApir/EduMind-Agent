"""Benchmark accounting and opt-in guard must not manufacture model evidence."""

import asyncio
import json
from unittest.mock import Mock

import pytest

from app.agents.review_schema import REVIEW_PROMPT_VERSION
from app.services.provider_gateway import (
    JsonSyntaxReason,
    OutputFailureReason,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
    TextRequest,
)
from tests.resource_quality import (
    BoundedGateway,
    candidate,
    detection,
    load_dataset,
    offline_report,
    provider_report,
)


def test_dataset_is_original_schema_valid_and_spans_all_seed_nodes() -> None:
    dataset = load_dataset()
    cases = dataset["semantic_errors"] + dataset["local_code_errors"] + dataset["controls"]
    assert len({item["node_id"] for item in dataset["controls"]}) == 10
    assert len(cases) == 30
    assert all(candidate(item).review_status == "pending" for item in cases)
    assert "no textbook excerpts" in dataset["authorship"]


def test_offline_does_not_count_authored_fixtures_as_generated_model_quality() -> None:
    report = offline_report()
    assert report["provider_calls"] == 0
    assert report["authored_fixture_schema_valid"] == 30
    assert report["local_code_errors_detected"] == 4
    assert report["semantic_errors_not_evaluated"] == 16
    assert report["schema_generation_rate"] is None
    assert report["severe_error_recall"] is None
    assert report["stage_gate_passed"] is False


def test_provider_unavailable_rejection_is_not_counted_as_error_detection() -> None:
    verdict = {
        "review_version": REVIEW_PROMPT_VERSION,
        "verdict": "reject",
        "issues": [{"area": "fact", "severity": "severe", "message": "Review unavailable."}],
    }
    assert not detection(verdict, expected_area="fact", model_id=None, local=False)
    assert detection(verdict, expected_area="fact", model_id="model", local=False)
    assert not detection(verdict, expected_area="code_safety", model_id="model", local=False)


def test_bounded_gateway_disables_retries_and_retains_failed_calls_in_budget() -> None:
    class Gateway:
        def __init__(self):
            self.retry_flags = []

        async def generate_structured(self, request, *, retry_safe=False):
            self.retry_flags.append(retry_safe)
            if len(self.retry_flags) == 1:
                raise ProviderError(ProviderErrorCode.TIMEOUT)
            return StructuredResult({}, "model")

    async def exercise():
        wrapped = Gateway()
        gateway = BoundedGateway(wrapped, limit=2)
        request = StructuredRequest(TextRequest(()), {})
        with pytest.raises(ProviderError):
            await gateway.generate_structured(request, retry_safe=True)
        await gateway.generate_structured(request, retry_safe=True)
        with pytest.raises(RuntimeError, match="CALL_LIMIT"):
            await gateway.generate_structured(request)
        assert gateway.calls == 2 and wrapped.retry_flags == [False, False]

    asyncio.run(exercise())


@pytest.mark.parametrize("mode", ["provider", "diagnostic", "circular-diagnostic"])
def test_provider_cli_refuses_without_explicit_billable_confirmation(monkeypatch, mode) -> None:
    from tests import resource_quality

    factory = Mock(side_effect=AssertionError("Provider must not be created"))
    monkeypatch.setattr(resource_quality, "build_default_provider_gateway", factory)
    monkeypatch.setattr("sys.argv", ["resource_quality", "--mode", mode])
    with pytest.raises(SystemExit, match="confirm-billable"):
        resource_quality.main()
    factory.assert_not_called()


def test_offline_cli_saves_same_sanitized_report_without_provider(
    monkeypatch, tmp_path, capsys
) -> None:
    from tests import resource_quality

    destination = tmp_path / "report.json"
    factory = Mock(side_effect=AssertionError("Provider must not be created"))
    monkeypatch.setattr(resource_quality, "build_default_provider_gateway", factory)
    monkeypatch.setattr("sys.argv", ["resource_quality", "--output", str(destination)])
    resource_quality.main()
    saved = json.loads(destination.read_text(encoding="utf-8"))
    assert saved == json.loads(capsys.readouterr().out)
    assert saved["provider_calls"] == 0 and saved["stage_gate_passed"] is False
    factory.assert_not_called()


def test_mock_run_keeps_generated_failures_and_missed_semantic_errors_in_denominators() -> None:
    class Gateway:
        def __init__(self):
            self.calls = 0

        async def generate_structured(self, request, *, retry_safe=False):
            assert retry_safe is False
            self.calls += 1
            properties = request.json_schema["properties"]
            if "review_version" in properties:
                return StructuredResult(
                    {"review_version": REVIEW_PROMPT_VERSION, "verdict": "pass", "issues": []},
                    "mock-only",
                )
            if self.calls <= 2:
                raise ProviderError(
                    ProviderErrorCode.INVALID_OUTPUT,
                    output_failure_reason=OutputFailureReason.STRUCTURED_JSON_INVALID,
                    json_syntax_reason=JsonSyntaxReason.INVALID_ESCAPE,
                )
            kind = properties["resource_type"]["const"]
            if kind == "explanation":
                content = {"markdown": "原创测试讲解"}
            elif kind == "code":
                content = {
                    "language": "C",
                    "source": "int main(void) { return 0; }",
                    "expected_output": "正常结束",
                    "key_steps": ["返回"],
                    "display_only": True,
                }
            else:
                content = {
                    "items": [
                        {
                            "id": f"q{i}",
                            "question": "测试题",
                            "answer": "测试答案",
                            "explanation": "测试解释",
                        }
                        for i in range(2)
                    ]
                }
            return StructuredResult(
                {
                    "resource_type": kind,
                    "prompt_version": "learning-resources-v1",
                    "content": content,
                },
                "mock-only",
            )

    report = asyncio.run(provider_report(BoundedGateway(Gateway()), "mock-only"))
    assert report["schema_sample_count"] == 60
    assert report["schema_generation_rate"] == 58 / 60
    assert report["schema_samples"][0]["output_failure_reason"] == "STRUCTURED_JSON_INVALID"
    assert report["schema_samples"][0]["json_syntax_reason"] == "INVALID_ESCAPE"
    assert report["severe_error_count"] == 20 and report["severe_error_recall"] == 4 / 20
    assert report["model_only_severe_error_recall"] == 0
    assert report["control_pass_rate"] == 1
    assert report["provider_calls"] == 86
    assert report["stage_gate_passed"] is False


def test_diagnostic_probes_are_fixed_bounded_and_cannot_claim_quality() -> None:
    class Gateway:
        async def generate_structured(self, request, *, retry_safe=False):
            assert retry_safe is False
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.STRUCTURED_SCHEMA_MISMATCH,
            )

    report = asyncio.run(
        provider_report(BoundedGateway(Gateway(), limit=5), "mock", diagnostic=True)
    )
    assert report["provider_calls"] == 5 and report["schema_sample_count"] == 5
    assert report["mode"] == "diagnostic" and report["stage_gate_passed"] is False
    assert report["schema_generation_rate"] is None and report["severe_error_recall"] is None
    assert {item["id"] for item in report["schema_samples"]} == {
        "array:explanation:1", "c-pointer:explanation:1", "circular-queue:explanation:1",
        "linked-list-deletion:explanation:1", "linked-list-insertion:code:1",
    }
    assert all(item["output_failure_reason"] == "STRUCTURED_SCHEMA_MISMATCH"
               for item in report["schema_samples"])


def test_circular_diagnostic_has_exactly_three_fixed_cases_and_safe_keyword() -> None:
    class Gateway:
        async def generate_structured(self, request, *, retry_safe=False):
            assert retry_safe is False
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.STRUCTURED_SCHEMA_MISMATCH,
                schema_keyword="required",
            )

    report = asyncio.run(provider_report(BoundedGateway(Gateway(), limit=3), "mock", circular=True))
    assert report["provider_calls"] == 3 and report["call_limit"] == 3
    assert report["mode"] == "circular-diagnostic"
    assert {item["id"] for item in report["schema_samples"]} == {
        "circular-queue:code:1", "circular-queue:exercise:1", "circular-queue:code:2",
    }
    assert all(item["schema_keyword"] == "required" for item in report["schema_samples"])
    assert report["schema_generation_rate"] is None and report["stage_gate_passed"] is False
