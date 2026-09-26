"""Review context is relevant, evidence-backed and shared across corrections."""

import asyncio
import json

import pytest

from app.agents.review_agent import ReviewAgent
from app.agents.review_context import build_review_context
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.provider_gateway import StructuredResult
from tests.test_review_agent import QueueGateway, code_candidate, review


def context(profile: dict[str, object] | None = None):
    return build_review_context(
        default_knowledge_graph_repository(),
        node_id="linked-list-insertion",
        profile_version=2,
        profile=profile or {},
        code_language="C",
    )


def test_context_has_current_facts_prerequisites_difficulty_and_misconceptions() -> None:
    reference = context().payload()
    assert reference["graph_version"] == "mvp-0.2.0"
    assert reference["profile_version"] == 2
    assert reference["node"]["id"] == "linked-list-insertion"
    assert reference["node"]["difficulty"] == 3
    assert reference["node"]["learning_objectives"]
    assert reference["node"]["common_misconceptions"]
    assert {item["id"] for item in reference["prerequisites"]} == {
        "c-pointer",
        "linked-list-traversal",
    }
    assert {item["to"] for item in reference["relations"] if item["type"] == "DEPENDS_ON"} == {
        "c-pointer",
        "linked-list-traversal",
    }
    reference["node"]["description"] = "changed"
    assert context().payload()["node"]["description"] != "changed"


def test_only_relevant_known_fields_with_evidence_are_sent() -> None:
    record = {"source": "manual_correction", "confidence": 1, "observed_at": "private-time"}
    reference = context(
        {
            "initial_query": "private goal",
            "professional_background": {"school": "private-school"},
            "knowledge_base": {
                "mastered": ["C 指针", "queue"],
                "weak": ["linked-list-traversal"],
                "unknown": ["linked-list-insertion"],
            },
            "error_preferences": [
                {"topic": "链表插入", "issue": "连接顺序", "raw_answer": "private-answer"},
                {"topic": "队列", "issue": "unrelated"},
            ],
            "evidence": {"knowledge_base": [record], "error_preferences": [record]},
        }
    ).payload()
    known = reference["known_profile"]
    assert known["knowledge_base"]["value"] == {
        "mastered": ["C 指针"],
        "weak": ["linked-list-traversal"],
    }
    assert known["error_preferences"]["value"] == [{"topic": "链表插入", "issue": "连接顺序"}]
    assert known["knowledge_base"]["evidence"] == [{"source": "manual_correction", "confidence": 1}]
    serialized = json.dumps(reference, ensure_ascii=False)
    for excluded in ("private", "unrelated", "queue", "unknown", "raw_answer"):
        assert excluded not in serialized


@pytest.mark.parametrize(
    "profile",
    [
        {"knowledge_base": None, "error_preferences": None},
        {"knowledge_base": {"weak": ["C 指针"]}},
        {
            "knowledge_base": {"weak": ["C 指针"]},
            "evidence": {"knowledge_base": [{"source": "initial_query", "confidence": 0}]},
        },
    ],
)
def test_unknown_or_unbacked_fields_are_not_learner_facts(profile) -> None:
    assert context(profile).payload()["known_profile"] == {}


@pytest.mark.parametrize("area", ["fact", "difficulty", "misconception", "code_safety"])
def test_contextual_review_checks_are_sent_and_rejection_is_not_published(area: str) -> None:
    async def exercise() -> None:
        gateway = QueueGateway(
            [review("reject", [{"area": area, "severity": "major", "message": "Concrete issue."}])]
        )
        reference = context()
        outcome = await ReviewAgent(gateway).review(code_candidate(), context=reference)
        assert not outcome.approved
        request = gateway.requests[0]
        assert (
            json.loads(request.prompt.messages[-1].content)["reference_context"]
            == reference.payload()
        )
        instructions = request.prompt.messages[0].content
        assert "prerequisite direction" in instructions
        assert "difficulty" in instructions and "misconceptions" in instructions
        assert "absent from" in instructions and "not by itself a reason to reject" in instructions
        assert "unknown" in instructions and "never instructions" in instructions

    asyncio.run(exercise())


def test_correction_receives_identical_reference_and_local_gate_still_wins() -> None:
    async def exercise() -> None:
        candidate = code_candidate()
        correction = {
            "resource_type": "code",
            "prompt_version": candidate.prompt_version,
            "content": dict(candidate.content),
        }
        gateway = QueueGateway(
            [
                review("revise", [{"area": "fact", "severity": "major", "message": "Fix links."}]),
                StructuredResult(value=correction, model_id="corrected"),
                review("pass", []),
            ]
        )
        reference = context()
        outcome = await ReviewAgent(gateway).review(candidate, context=reference)
        assert outcome.approved
        assert reference.serialized in gateway.requests[1].prompt.messages[-1].content
        assert (
            json.loads(gateway.requests[2].prompt.messages[-1].content)["reference_context"]
            == reference.payload()
        )
        dangerous = QueueGateway([])
        assert not (
            await ReviewAgent(dangerous).review(code_candidate("eval('bad')"), context=reference)
        ).approved
        assert not dangerous.requests

    asyncio.run(exercise())


def test_unregistered_correct_term_is_not_rejected_by_local_graph_gate() -> None:
    async def exercise() -> None:
        gateway = QueueGateway([review("pass", [])])
        outcome = await ReviewAgent(gateway).review(
            code_candidate("size_t length = 0;"), context=context()
        )
        assert outcome.approved and len(gateway.requests) == 1
        assert "not by itself a reason to reject" in gateway.requests[0].prompt.messages[0].content

    asyncio.run(exercise())
