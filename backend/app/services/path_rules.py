"""Pure, versioned path planning over the validated knowledge graph."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Final

from app.services.knowledge_graph import KnowledgeGraphRepository, KnowledgeNode
from app.services.mastery_rules import MASTERY_RULE_CONFIG

PATH_RULE_VERSION: Final = "path-v1"
PATH_RULE_CONFIG: Final[Mapping[str, float]] = MappingProxyType(
    {
        "mastered_at": MASTERY_RULE_CONFIG["mastered_at"],
        "dependency_distance_weight": 0.2,
        "difficulty_jump_weight": 0.4,
        "error_risk_weight": 0.3,
        "forgetting_risk_weight": 0.15,
        "mastery_weight": 0.2,
        "target_relevance_weight": 0.5,
        "base_minutes": 8.0,
        "minutes_per_difficulty": 4.0,
    }
)


class PathRuleError(ValueError):
    """The target, graph, or mastery input cannot produce a safe path."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PathMastery:
    score: float
    status: str
    evidence_summary: tuple[str, ...] = ()
    forgetting_risk: float = 0.0


@dataclass(frozen=True, slots=True)
class PathStep:
    node_id: str
    score: float
    status: str
    cost: float
    recommended_resource: str
    estimated_minutes: int
    reason: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PathDecision:
    target_node_id: str
    rule_version: str
    steps: tuple[PathStep, ...]
    current_node_id: str | None
    prerequisite_node_ids: tuple[str, ...]
    next_node_id: str | None


def _mastery_for(node_id: str, mastery: Mapping[str, PathMastery]) -> PathMastery:
    value = mastery.get(node_id, PathMastery(0.0, "unseen"))
    if (
        not isinstance(value.score, (int, float))
        or isinstance(value.score, bool)
        or not isfinite(value.score)
        or not 0 <= value.score <= 1
        or value.status not in {"unseen", "learning", "weak", "mastered"}
        or not all(isinstance(item, str) for item in value.evidence_summary)
        or not isinstance(value.forgetting_risk, (int, float))
        or isinstance(value.forgetting_risk, bool)
        or not isfinite(value.forgetting_risk)
        or not 0 <= value.forgetting_risk <= 1
    ):
        raise PathRuleError("INVALID_MASTERY")
    return value


def _dependency_closure(
    graph: KnowledgeGraphRepository,
    target_node_id: str,
    available_node_ids: frozenset[str] | None,
) -> dict[str, KnowledgeNode]:
    if graph.get_node(target_node_id) is None:
        raise PathRuleError("UNKNOWN_TARGET")
    seen: dict[str, KnowledgeNode] = {}
    visiting: set[str] = set()

    def visit(node_id: str) -> None:
        if available_node_ids is not None and node_id not in available_node_ids:
            raise PathRuleError("UNREACHABLE_TARGET")
        if node_id in visiting:
            raise PathRuleError("INVALID_GRAPH")
        if node_id in seen:
            return
        node = graph.get_node(node_id)
        if node is None:
            raise PathRuleError("INVALID_GRAPH")
        visiting.add(node_id)
        for dependency in node.prerequisites:
            visit(dependency)
        visiting.remove(node_id)
        seen[node_id] = node

    visit(target_node_id)
    return seen


def _distance_to_target(nodes: Mapping[str, KnowledgeNode], target_node_id: str) -> dict[str, int]:
    distance = {target_node_id: 0}

    def walk(node_id: str) -> None:
        node = nodes[node_id]
        for dependency in node.prerequisites:
            candidate = distance[node_id] + 1
            if candidate > distance.get(dependency, -1):
                distance[dependency] = candidate
                walk(dependency)

    walk(target_node_id)
    return distance


def plan_learning_path(
    graph: KnowledgeGraphRepository,
    *,
    target_node_id: str,
    mastery: Mapping[str, PathMastery],
    available_node_ids: frozenset[str] | None = None,
) -> PathDecision:
    """Choose stable prerequisite-safe steps; never infer mastery or call a Provider."""
    nodes = _dependency_closure(graph, target_node_id, available_node_ids)
    distances = _distance_to_target(nodes, target_node_id)
    states = {node_id: _mastery_for(node_id, mastery) for node_id in nodes}
    complete = {
        node_id
        for node_id, state in states.items()
        if state.status == "mastered" and state.score >= PATH_RULE_CONFIG["mastered_at"]
    }
    remaining = set(nodes) - complete
    ordered: list[PathStep] = []
    previous_difficulty = 1
    while remaining:
        ready = [
            node_id
            for node_id in remaining
            if all(dependency not in remaining for dependency in nodes[node_id].prerequisites)
        ]
        if not ready:
            raise PathRuleError("INVALID_GRAPH")

        def priority(node_id: str) -> tuple[int, float, str]:
            node = nodes[node_id]
            state = states[node_id]
            cost = (
                PATH_RULE_CONFIG["dependency_distance_weight"] * distances[node_id]
                + PATH_RULE_CONFIG["difficulty_jump_weight"]
                * max(0, node.difficulty - previous_difficulty - 1)
                + PATH_RULE_CONFIG["error_risk_weight"] * (1 - state.score)
                + PATH_RULE_CONFIG["forgetting_risk_weight"] * state.forgetting_risk
                - PATH_RULE_CONFIG["mastery_weight"] * state.score
                - PATH_RULE_CONFIG["target_relevance_weight"] * (node_id == target_node_id)
            )
            return (0 if state.status == "weak" else 1, round(cost, 4), node_id)

        chosen = min(ready, key=priority)
        node = nodes[chosen]
        state = states[chosen]
        dependent = next(
            (
                item.id
                for item in sorted(nodes.values(), key=lambda item: item.id)
                if chosen in item.prerequisites
            ),
            None,
        )
        if state.status == "weak":
            reason: Mapping[str, object] = {
                "kind": "mastery_evidence",
                "node_id": chosen,
                "score": state.score,
                "status": state.status,
                "evidence_summary": list(state.evidence_summary),
            }
        elif dependent is not None:
            reason = {"kind": "prerequisite", "node_id": chosen, "required_by": dependent}
        else:
            reason = {
                "kind": "mastery_state",
                "node_id": chosen,
                "score": state.score,
                "status": state.status,
            }
        ordered.append(
            PathStep(
                node_id=chosen,
                score=state.score,
                status=state.status,
                cost=priority(chosen)[1],
                recommended_resource=(
                    "review"
                    if state.status == "weak"
                    else "exercise"
                    if state.score >= 0.4
                    else "explanation"
                ),
                estimated_minutes=int(
                    PATH_RULE_CONFIG["base_minutes"]
                    + PATH_RULE_CONFIG["minutes_per_difficulty"] * node.difficulty
                ),
                reason=reason,
            )
        )
        previous_difficulty = node.difficulty
        remaining.remove(chosen)
    current = ordered[0].node_id if ordered else None
    next_node = ordered[1].node_id if len(ordered) > 1 else None
    direct_prerequisites = (
        tuple(sorted(nodes[current].prerequisites)) if current is not None else ()
    )
    return PathDecision(
        target_node_id=target_node_id,
        rule_version=PATH_RULE_VERSION,
        steps=tuple(ordered),
        current_node_id=current,
        prerequisite_node_ids=direct_prerequisites,
        next_node_id=next_node,
    )
