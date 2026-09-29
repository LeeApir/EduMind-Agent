"""Generate an unreviewed array-versus-linked-list multi-perspective candidate."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Literal, Protocol

from app.agents.debate_candidate_prompt import (
    DEBATE_CANDIDATE_PROMPT_VERSION,
    debate_candidate_context,
    debate_candidate_prompt,
)
from app.agents.debate_candidate_schema import (
    DEBATE_CANDIDATE_SCHEMA_VERSION,
    DEBATE_NODE_IDS,
    DebateCandidateSchemaError,
    debate_candidate_output_schema,
    validate_debate_candidate,
)
from app.services.knowledge_graph import KnowledgeGraphRepository, RelationType
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
    TaskProfile,
    TextRequest,
    TokenUsage,
)


class DebateGenerationInputError(ValueError):
    """The P0 preset or required graph context is unavailable."""

    def __init__(self) -> None:
        super().__init__("A supported preset, question, and graph basis are required.")


class DebateStructuredGateway(Protocol):
    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult: ...


@dataclass(frozen=True, slots=True)
class DebateCandidateRequest:
    preset: Literal["array-vs-linked-list"]
    question: str
    graph: KnowledgeGraphRepository
    profile: Mapping[str, object] | None = None
    profile_version: int | None = None

    def __post_init__(self) -> None:
        if (
            self.preset != "array-vs-linked-list"
            or not isinstance(self.question, str)
            or not 1 <= len(self.question.strip()) <= 1000
            or not isinstance(self.graph, KnowledgeGraphRepository)
            or (self.profile is None) != (self.profile_version is None)
            or self.profile is not None and not isinstance(self.profile, Mapping)
            or self.profile_version is not None
            and (type(self.profile_version) is not int or self.profile_version < 1)
        ):
            raise DebateGenerationInputError


@dataclass(frozen=True, slots=True)
class PendingDebateCandidate:
    """Schema-valid but unreviewed; T024 must review before publication."""

    content: Mapping[str, object]
    schema_version: str
    prompt_version: str
    model_id: str
    usage: TokenUsage | None
    review_status: Literal["pending"] = "pending"


@dataclass(frozen=True, slots=True)
class DebateGenerationFailure:
    code: ProviderErrorCode
    message: str


def _graph_basis(graph: KnowledgeGraphRepository) -> dict[str, object]:
    nodes = [graph.get_node(node_id) for node_id in DEBATE_NODE_IDS]
    if any(node is None for node in nodes):
        raise DebateGenerationInputError
    similar = any(
        relation.relation_type is RelationType.SIMILAR_TO
        and {relation.from_node_id, relation.to_node_id} == set(DEBATE_NODE_IDS)
        for relation in graph.all_relations()
    )
    if not similar:
        raise DebateGenerationInputError
    return {
        "graph_version": graph.graph_version,
        "nodes": [
            {
                "id": node.id, "name": node.name,
                "description": node.description, "ai_context": node.ai_context,
                "learning_objectives": list(node.learning_objectives),
            }
            for node in nodes if node is not None
        ],
        "relation": {"type": "SIMILAR_TO", "node_ids": list(DEBATE_NODE_IDS)},
    }


def _known_profile(
    profile: Mapping[str, object] | None, profile_version: int | None
) -> dict[str, object]:
    if profile is None or profile_version is None:
        return {}
    evidence = profile.get("evidence")
    if not isinstance(evidence, dict):
        return {}

    def has_evidence(field: str, sources: set[str]) -> bool:
        records = evidence.get(field)
        return isinstance(records, list) and any(
            isinstance(item, dict)
            and item.get("source") in sources
            and isinstance(item.get("confidence"), (int, float))
            and not isinstance(item.get("confidence"), bool)
            and isfinite(item["confidence"])
            and 0 < item["confidence"] <= 1
            for item in records
        )

    known: dict[str, object] = {"profile_version": profile_version}
    knowledge = profile.get("knowledge_base")
    if isinstance(knowledge, dict) and has_evidence(
        "knowledge_base",
        {"learner_statement", "learning_behavior", "explicit_feedback", "manual_correction"},
    ):
        selected: dict[str, list[str]] = {}
        for field in ("mastered", "weak"):
            values = knowledge.get(field)
            if isinstance(values, list):
                relevant = [value for value in values if isinstance(value, str)
                            and value in DEBATE_NODE_IDS]
                if relevant:
                    selected[field] = relevant
        if selected:
            known["knowledge_base"] = selected
    style = profile.get("cognitive_style")
    if isinstance(style, dict) and has_evidence(
        "cognitive_style", {"explicit_feedback", "manual_correction"}
    ):
        preference = style.get("preference_persona")
        if isinstance(preference, str) and preference in {
            "performance", "engineering", "academic",
        }:
            known["preference_persona"] = preference
    if len(known) == 1:
        return {}
    return known


class DebateCandidateGenerator:
    def __init__(self, gateway: DebateStructuredGateway) -> None:
        self._gateway = gateway

    async def generate(
        self, request: DebateCandidateRequest
    ) -> PendingDebateCandidate | DebateGenerationFailure:
        graph_basis = _graph_basis(request.graph)
        known_profile = _known_profile(request.profile, request.profile_version)
        provider_request = StructuredRequest(
            prompt=TextRequest(
                messages=(
                    ChatMessage(role="system", content=debate_candidate_prompt()),
                    ChatMessage(role="user", content=debate_candidate_context(
                        question=request.question.strip(), graph_basis=graph_basis,
                        known_profile=known_profile,
                    )),
                ),
                task_profile=TaskProfile.QUALITY,
            ),
            json_schema=debate_candidate_output_schema(),
        )
        try:
            result = await self._gateway.generate_structured(provider_request, retry_safe=False)
            validated = validate_debate_candidate(result.value)
        except ProviderError as error:
            return DebateGenerationFailure(error.code, str(error))
        except DebateCandidateSchemaError as error:
            return DebateGenerationFailure(ProviderErrorCode.INVALID_OUTPUT, str(error))
        content = {**validated, "graph_basis": graph_basis}
        return PendingDebateCandidate(
            content=deepcopy(content),
            schema_version=DEBATE_CANDIDATE_SCHEMA_VERSION,
            prompt_version=DEBATE_CANDIDATE_PROMPT_VERSION,
            model_id=result.model_id,
            usage=result.usage,
        )
