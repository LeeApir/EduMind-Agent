"""The P0 debate candidate uses one grounded request and remains unreviewed."""

import asyncio
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from app.agents.debate_candidate_generator import (
    DebateCandidateGenerator,
    DebateCandidateRequest,
    DebateGenerationFailure,
    DebateGenerationInputError,
    PendingDebateCandidate,
)
from app.agents.debate_candidate_schema import (
    DEBATE_CANDIDATE_SCHEMA_VERSION,
    DebateCandidateSchemaError,
    debate_candidate_output_schema,
    validate_debate_candidate,
)
from app.services.knowledge_graph import RelationType, default_knowledge_graph_repository
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
    TokenUsage,
)


def candidate() -> dict[str, object]:
    return {
        "schema_version": DEBATE_CANDIDATE_SCHEMA_VERSION,
        "question_conditions": {
            "stated": ["需要频繁随机访问"],
            "unknown": ["是否频繁插入中间位置"],
        },
        "graph_refs": ["array", "single-linked-list"],
        "perspectives": {
            "performance": "随机访问条件下数组更适合；还需确认更新频率。",
            "engineering": "接口和维护成本取决于实际操作模式。",
            "academic": "二者是不同的顺序存储组织方式，选择须结合操作定义。",
        },
        "moderator": {
            "objective_conclusion": "在给定随机访问需求下优先比较数组。",
            "tradeoffs": "仍需考虑插入位置、内存布局和实现约束。",
            "learner_advice": "先用操作表对照两者。",
        },
    }


class Gateway:
    def __init__(self, result: StructuredResult | ProviderError) -> None:
        self.result = result
        self.calls: list[tuple[StructuredRequest, bool]] = []

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult:
        self.calls.append((request, retry_safe))
        if isinstance(self.result, ProviderError):
            raise self.result
        return self.result


def request(*, profile: dict[str, object] | None = None) -> DebateCandidateRequest:
    return DebateCandidateRequest(
        preset="array-vs-linked-list", question="频繁随机访问时数组还是链表合适？",
        graph=default_knowledge_graph_repository(), profile=profile,
        profile_version=2 if profile else None,
    )


def test_generates_all_three_perspectives_and_separate_moderator_fields_once() -> None:
    async def exercise() -> None:
        gateway = Gateway(StructuredResult(
            value=candidate(), model_id="model-a", usage=TokenUsage(100, 200),
        ))
        outcome = await DebateCandidateGenerator(gateway).generate(request())
        assert isinstance(outcome, PendingDebateCandidate)
        assert outcome.review_status == "pending"
        assert outcome.schema_version == DEBATE_CANDIDATE_SCHEMA_VERSION
        assert outcome.prompt_version == "array-vs-linked-list-instructions-v1"
        assert outcome.usage == TokenUsage(100, 200)
        assert set(outcome.content["perspectives"]) == {"performance", "engineering", "academic"}
        assert set(outcome.content["moderator"]) == {
            "objective_conclusion", "tradeoffs", "learner_advice",
        }
        assert outcome.content["question_conditions"] == candidate()["question_conditions"]
        basis = outcome.content["graph_basis"]
        assert isinstance(basis, dict)
        assert basis["graph_version"] == request().graph.graph_version
        assert [node["id"] for node in basis["nodes"]] == ["array", "single-linked-list"]
        assert len(gateway.calls) == 1
        provider_request, retry_safe = gateway.calls[0]
        assert retry_safe is False
        assert provider_request.json_schema == debate_candidate_output_schema()
        assert provider_request.prompt.task_profile == "quality"
        assert "No parallel agents" in provider_request.prompt.messages[0].content

    asyncio.run(exercise())


def test_context_keeps_graph_facts_and_only_evidence_backed_profile_fields() -> None:
    async def exercise() -> None:
        profile = {
            "knowledge_base": {"mastered": ["array", "stack", "invented"]},
            "cognitive_style": {"preference_persona": "engineering"},
            "professional_background": {"private": "do not send"},
            "evidence": {
                "knowledge_base": [{"source": "learning_behavior", "confidence": 0.8}],
                "cognitive_style": [{"source": "explicit_feedback", "confidence": 0.9}],
            },
        }
        gateway = Gateway(StructuredResult(value=candidate(), model_id="model-a"))
        await DebateCandidateGenerator(gateway).generate(request(profile=profile))
        context = json.loads(gateway.calls[0][0].prompt.messages[1].content)
        assert context["preset"] == "array-vs-linked-list"
        assert context["question"] == "频繁随机访问时数组还是链表合适？"
        assert context["graph_basis"]["relation"]["type"] == "SIMILAR_TO"
        assert context["known_profile"] == {
            "profile_version": 2,
            "knowledge_base": {"mastered": ["array"]},
            "preference_persona": "engineering",
        }
        assert "private" not in gateway.calls[0][0].prompt.messages[1].content
        profile["evidence"]["cognitive_style"] = [
            {"source": "learning_behavior", "confidence": 0.9},
        ]
        await DebateCandidateGenerator(gateway).generate(request(profile=profile))
        later = json.loads(gateway.calls[1][0].prompt.messages[1].content)
        assert "preference_persona" not in later["known_profile"]

    asyncio.run(exercise())


@pytest.mark.parametrize("breakage", [
    lambda value: value.pop("moderator"),
    lambda value: value["perspectives"].pop("academic"),
    lambda value: value.update({"graph_refs": ["array", "stack"]}),
    lambda value: value.update({"schema_version": "later"}),
    lambda value: value["question_conditions"].update({"stated": ["same", "same"]}),
])
def test_rejects_partial_or_unsupported_candidate(breakage) -> None:
    value = deepcopy(candidate())
    breakage(value)
    with pytest.raises(DebateCandidateSchemaError):
        validate_debate_candidate(value)


@pytest.mark.parametrize("result,code", [
    (ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE),
     ProviderErrorCode.TEMPORARILY_UNAVAILABLE),
    (StructuredResult(value={"perspectives": {}}, model_id="model-a"),
     ProviderErrorCode.INVALID_OUTPUT),
])
def test_provider_and_format_failures_remain_safe_and_unpublished(result, code) -> None:
    async def exercise() -> None:
        gateway = Gateway(result)
        outcome = await DebateCandidateGenerator(gateway).generate(request())
        assert isinstance(outcome, DebateGenerationFailure)
        assert outcome.code == code
        assert outcome.message
        assert len(gateway.calls) == 1

    asyncio.run(exercise())


def test_invalid_preset_and_question_stop_before_provider() -> None:
    with pytest.raises(DebateGenerationInputError):
        DebateCandidateRequest(
            preset="other", question="数组还是链表？", graph=default_knowledge_graph_repository(),
        )
    with pytest.raises(DebateGenerationInputError):
        DebateCandidateRequest(
            preset="array-vs-linked-list", question=" ", graph=default_knowledge_graph_repository(),
        )
    with pytest.raises(DebateGenerationInputError):
        DebateCandidateRequest(
            preset="array-vs-linked-list", question="数组还是链表？",
            graph=default_knowledge_graph_repository(), profile={"evidence": {}},
        )


def test_missing_graph_relation_prevents_unsupported_generation() -> None:
    async def exercise() -> None:
        graph = default_knowledge_graph_repository()
        without_similar = replace(
            graph,
            _relations=tuple(relation for relation in graph.all_relations()
                             if relation.relation_type is not RelationType.SIMILAR_TO),
        )
        gateway = Gateway(StructuredResult(value=candidate(), model_id="model-a"))
        with pytest.raises(DebateGenerationInputError):
            await DebateCandidateGenerator(gateway).generate(DebateCandidateRequest(
                preset="array-vs-linked-list", question="数组还是链表？", graph=without_similar,
            ))
        assert gateway.calls == []

    asyncio.run(exercise())
