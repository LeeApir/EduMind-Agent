"""Notation audit dispatch/control coverage; mocked verdicts are not quality evidence."""

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
import t040_high_diagnostics as high  # noqa: E402


@pytest.mark.parametrize(
    "text",
    [
        "位置从1编号，head指向首个数据节点。访问第i个元素需要沿next移动i-1次。",
        "索引从0编号，head指向索引0的数据节点。访问索引i的元素需沿next移动i次。",
        "head指向不存数据的哨兵。位置从1编号，访问第i个数据元素需从哨兵移动i次。",
        "head指向首个数据节点。从1编号，访问第i个元素共访问i个节点，经过i-1条链接。",
    ],
)
def test_explicit_correct_conventions_are_forwarded_without_local_false_rejection(text):
    class Gateway:
        async def generate_structured(self, request, *, retry_safe=False):
            self.request = request
            return StructuredResult(
                {"review_version": "resource-review-v3", "verdict": "pass", "issues": []},
                "offline-only",
            )

    gateway = Gateway()
    candidate = PendingLearningResource(
        LearningResourceType.EXPLANATION, {"markdown": text}, "synthetic", "synthetic", None
    )
    outcome = asyncio.run(ReviewAgent(gateway).review(candidate))
    assert outcome.approved
    prompt = gateway.request.prompt
    assert json.loads(prompt.messages[1].content)["content"]["markdown"] == text
    instructions = prompt.messages[0].content
    assert REVIEW_INSTRUCTION_VERSION == "resource-review-instructions-v4"
    assert "visited nodes from traversed links" in instructions
    assert "dummy/sentinel head" in instructions
    assert "do not silently choose the convention" in instructions
    assert "do not demand redundant declarations" in instructions
    assert "without inventing memory-safety impact" in instructions
    # The pass is supplied by a fake gateway; this test makes no model-quality claim.


def test_r05_has_new_namespace_unchanged_candidates_and_current_prompt(monkeypatch):
    with monkeypatch.context() as context:
        for name in ("BASE", "RAW", "ROUND"):
            context.setattr(high, name, getattr(high, name))
        high.select_round("r05")
        bodies, plan = asyncio.run(high.proposed())
        prior = json.loads(
            (high.ROOT / "docs/acceptance/phase-1-t040-deepseek-high-v1/requests.json").read_text()
        )
        assert high.ROUND == "r05" and str(high.BASE).endswith("deepseek-high-v2")
        assert str(high.RAW).endswith("deepseek-high-v2")
        assert plan["review_instruction_version"] == REVIEW_INSTRUCTION_VERSION
        assert plan["prior_strategy_check_is_current_prompt_evidence"] is False
        assert [g["requests"] for g in plan["groups"]] == [5, 5, 1, 2]
        assert plan["provider_requests_authorized"] == 0 and not plan["old_budget_transferred"]
        for slot, body in bodies.items():
            assert body["input"][1] == prior[slot]["input"][1]
            assert body["input"][0] != prior[slot]["input"][0]
            assert body["text"] == prior[slot]["text"]
            assert body["reasoning"] == prior[slot]["reasoning"] == {"effort": "high"}
            assert body["max_output_tokens"] == prior[slot]["max_output_tokens"] == 8192


def test_unrecognized_round_cannot_select_arbitrary_ledger_path():
    with pytest.raises(ValueError, match="INVALID_FREEZE"):
        high.select_round("../../unrelated")
