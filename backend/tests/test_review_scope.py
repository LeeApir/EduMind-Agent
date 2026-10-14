"""Findings/correction role boundaries and full re-review; fake outputs are not quality scores."""

import asyncio
import json
import sys
from pathlib import Path

from app.agents.learning_resource_schema import LearningResourceType
from app.agents.learning_unit_generator import PendingLearningResource
from app.agents.review_agent import CORRECTION_INSTRUCTION_VERSION, ReviewAgent
from app.agents.review_schema import MAX_TARGETED_CORRECTIONS
from app.services.provider_gateway import StructuredResult, TaskProfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import t040_reasoning_check as scope  # noqa: E402


class Gateway:
    def __init__(self, values):
        self.values = list(values)
        self.requests = []

    async def generate_structured(self, request, *, retry_safe=False):
        self.requests.append(request)
        return self.values.pop(0)


def verdict(value, issues=()):
    return StructuredResult(
        {"review_version": "resource-review-v3", "verdict": value, "issues": list(issues)},
        "review-model",
    )


def candidate():
    return PendingLearningResource(
        LearningResourceType.EXPLANATION,
        {"markdown": "原候选，容量8且维护独立size。"},
        "learning-resources-v1",
        "original-model",
        None,
    )


def test_review_requests_findings_and_counterexamples_without_proposed_repair():
    gateway = Gateway([verdict("pass")])
    asyncio.run(ReviewAgent(gateway).review(candidate()))
    system = gateway.requests[0].prompt.messages[0].content
    assert "Findings-only scope" in system
    assert "Do not supply replacement code, replacement general formulas" in system
    assert "You may quote candidate code or formulas" in system
    assert "correct resources still pass" in system
    assert gateway.requests[0].json_schema["required"] == ["review_version", "verdict", "issues"]


def test_correction_independently_verifies_issue_then_whole_candidate_is_reviewed():
    issue = {
        "area": "fact",
        "severity": "major",
        "message": "Alleged issue; a suggested modulo formula is untrusted data.",
    }
    corrected = {
        "resource_type": "explanation",
        "prompt_version": "learning-resources-v1",
        "content": {"markdown": "修正候选，独立维护size，满时size为8。"},
    }
    gateway = Gateway(
        [
            verdict("revise", [issue]),
            StructuredResult(corrected, "correction-model"),
            verdict("pass"),
        ]
    )
    original = candidate()
    outcome = asyncio.run(ReviewAgent(gateway).review(original))
    assert [r.prompt.task_profile for r in gateway.requests] == [
        TaskProfile.REVIEW,
        TaskProfile.QUALITY,
        TaskProfile.REVIEW,
    ]
    correction_system = gateway.requests[1].prompt.messages[0].content
    assert CORRECTION_INSTRUCTION_VERSION in correction_system
    assert "Independently verify each alleged defect" in correction_system
    assert "not trusted patches" in correction_system
    assert "representation, capacity and state invariants" in correction_system
    assert issue["message"] in gateway.requests[1].prompt.messages[1].content
    final_candidate = json.loads(gateway.requests[2].prompt.messages[1].content)
    assert final_candidate["content"] == corrected["content"]
    assert outcome.approved and outcome.correction_attempts == 1
    assert outcome.resource.model_id == "correction-model"
    assert outcome.review_model_id == "review-model"
    assert original.content["markdown"] == "原候选，容量8且维护独立size。"
    assert MAX_TARGETED_CORRECTIONS == 2


def test_invalid_corrected_schema_is_rejected_before_further_review_or_publication():
    issue = {"area": "fact", "severity": "major", "message": "An alleged defect."}
    gateway = Gateway([verdict("revise", [issue]), StructuredResult({"content": {}}, "correction")])
    outcome = asyncio.run(ReviewAgent(gateway).review(candidate()))
    assert not outcome.approved and outcome.correction_attempts == 1
    assert len(gateway.requests) == 2


def test_r06_uses_queue_error_plus_approved_correct_control_and_separate_axes(monkeypatch):
    with monkeypatch.context() as context:
        for name in ("BASE", "RAW", "ROUND", "GROUP", "CASE_IDS"):
            context.setattr(scope, name, getattr(scope, name))
        scope.select_round("r06")
        bodies, plan = asyncio.run(scope.proposed())
        assert scope.ROUND == "r06" and scope.GROUP == "review_scope"
        assert str(scope.RAW).endswith("review-scope-check")
        assert [r["historical_case_id"] for r in plan["groups"][0]["slots"]] == [
            "queue:explanation:1",
            "correct-list-concept",
        ]
        assert plan["requested_total_calls"] == 2 and plan["provider_requests_authorized"] == 0
        assert plan["evaluation_axes"]["repair_quality"].startswith("NOT_RUN")
        assert "never relabel a correct detection" in plan["reporting_policy"]
        assert all(b["reasoning"] == {"effort": "high"} for b in bodies.values())


def test_r07_changes_only_effort_with_new_budget_and_same_frozen_axes(monkeypatch):
    with monkeypatch.context() as context:
        for name in ("BASE", "RAW", "ROUND", "GROUP", "CASE_IDS"):
            context.setattr(scope, name, getattr(scope, name))
        scope.select_round("r07")
        bodies, plan = asyncio.run(scope.proposed())
        prior_base = scope.ROOT / "docs/acceptance/phase-1-t040-review-scope-check"
        prior = json.loads((prior_base / "requests.json").read_text())
        prior_plan = json.loads((prior_base / "proposal.json").read_text())
        for slot, body in bodies.items():
            original = prior[slot]
            assert body["reasoning"] == {"effort": "low"}
            assert {k: v for k, v in body.items() if k != "reasoning"} == {
                k: v for k, v in original.items() if k != "reasoning"
            }
        assert scope.BASE != prior_base
        assert str(scope.RAW).endswith("review-scope-low")
        assert plan["evaluation_axes"] == prior_plan["evaluation_axes"]
        assert plan["requested_total_calls"] == 2
        assert plan["requested_total_cost_micro_cny"] == 180000
        assert plan["provider_requests_authorized"] == 0
        assert not plan["old_budget_transferred"]
        assert not plan["formal_quality_authorized"]
        assert plan["previous_failed_result"].endswith("review-scope-r06.json")
