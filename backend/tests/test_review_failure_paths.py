"""Failure-path prompt integration; historical diagnostics only, never quality scores."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from app.agents.learning_resource_schema import LearningResourceType
from app.agents.learning_unit_generator import PendingLearningResource
from app.agents.review_agent import REVIEW_INSTRUCTION_VERSION, ReviewAgent
from app.services.provider_gateway import StructuredResult

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acceptance_support.phase1_budget import canonical, sha  # noqa: E402
from prepare_t040_diagnostics import HISTORY, capture_case  # noqa: E402


@pytest.mark.parametrize("resource_type", list(LearningResourceType))
@pytest.mark.parametrize("corrected", [False, True])
def test_failure_path_guidance_reaches_each_resource_without_predetermined_rejection(
    resource_type, corrected
):
    source = "Node *insert(Node *old); Node *head = existing; head = insert(head);"
    if corrected:
        source = "Node *next = insert(head); if (next != NULL) { head = next; }"
    content = (
        {"source": source} if resource_type is LearningResourceType.CODE else {"markdown": source}
    )

    class Gateway:
        async def generate_structured(self, request, *, retry_safe=False):
            self.request = request
            return StructuredResult(
                {"review_version": "resource-review-v3", "verdict": "pass", "issues": []},
                "offline-only",
            )

    gateway = Gateway()
    candidate = PendingLearningResource(resource_type, content, "test", "test", None)
    outcome = asyncio.run(ReviewAgent(gateway).review(candidate))
    # This proves dispatch/serialization and preservation of independently supplied verdicts,
    # not that a model can find the defect or that this minimal snippet is complete C.
    assert outcome.approved and outcome.review_model_id == "offline-only"
    instruction = gateway.request.prompt.messages[0].content
    assert REVIEW_INSTRUCTION_VERSION == "resource-review-instructions-v6"
    assert "each returned value together with its caller" in instruction
    assert "last reachable pointer" in instruction
    assert "checked temporary result" in instruction
    assert "reachable path" in instruction
    payload = json.loads(gateway.request.prompt.messages[1].content)
    assert payload["content"] == content and payload["reference_context"] is None
    assert gateway.request.json_schema["required"] == ["review_version", "verdict", "issues"]


def test_historical_candidate_unchanged_only_prompt_changes():
    case = json.loads(HISTORY.read_text())["cases"][0]
    new_body = asyncio.run(capture_case(case))
    root = Path(__file__).resolve().parents[2]
    old_body = json.loads(
        (root / "docs/acceptance/phase-1-t040-deepseek-v1/requests.json").read_text()
    )["error_detection:01"]
    assert new_body["input"][1] == old_body["input"][1]
    assert new_body["text"] == old_body["text"]
    assert new_body["max_output_tokens"] == old_body["max_output_tokens"] == 4096
    assert new_body["reasoning"] == old_body["reasoning"] == {"effort": "none"}
    assert sha(canonical(new_body)) != sha(canonical(old_body))
    assert case["target_defect"] not in new_body["input"][0]["content"]


def test_new_execution_namespace_does_not_reuse_old_run_or_approval(monkeypatch):
    import run_t040_diagnostics as execution
    import t040_diagnostics_v2 as second

    # Restore original globals after verifying the independent composition.
    with monkeypatch.context() as context:
        for name in ("BASE", "RAW", "ROUND", "check_proposal"):
            context.setattr(execution, name, getattr(execution, name))
        second.configure_execution()
        assert execution.BASE == second.BASE and execution.RAW == second.RAW
        assert execution.ROUND == "r02"
        assert "phase-1-t040-deepseek-v2" in str(execution.RAW)
        assert execution.check_proposal is second.check_proposal
