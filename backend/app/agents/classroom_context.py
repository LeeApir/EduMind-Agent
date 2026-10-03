"""Minimal, sanitized classroom-turn reference context for single-Tutor orchestration.

Only the current goal, already-reviewed resources, the necessary evidence-backed
profile signals, and a compact path snapshot are sent. Raw evidence records, raw
profile fields, unreviewed resources, and message history are deliberately excluded so
one classroom turn never leaks more than it needs.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

from app.agents.profile_schema import EVIDENCE_SOURCES
from app.services.knowledge_graph import KnowledgeGraphRepository

CLASSROOM_CONTEXT_VERSION = "classroom-turn-context-v1"
_RESOURCE_TYPES = frozenset({"explanation", "code", "exercise"})


@dataclass(frozen=True, slots=True)
class ClassroomTurnContext:
    """An immutable, JSON-serialized minimal reference for one classroom turn."""

    serialized: str

    def payload(self) -> dict[str, object]:
        value = json.loads(self.serialized)
        assert isinstance(value, dict)
        return value


def _evidence(profile: Mapping[str, object], field: str) -> list[dict[str, object]]:
    evidence = profile.get("evidence")
    records = evidence.get(field) if isinstance(evidence, dict) else None
    if not isinstance(records, list):
        return []
    selected: list[dict[str, object]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        confidence = record.get("confidence")
        source = record.get("source")
        if (
            isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and isfinite(confidence)
            and 0 < confidence <= 1
            and isinstance(source, str)
            and source in EVIDENCE_SOURCES
        ):
            selected.append({"source": source, "confidence": confidence})
    return selected


def _known_profile(profile: Mapping[str, object], topics: set[str]) -> dict[str, object]:
    """Keep only evidence-backed signals relevant to the current node, without evidence."""
    known: dict[str, object] = {}
    knowledge = profile.get("knowledge_base")
    if isinstance(knowledge, dict) and _evidence(profile, "knowledge_base"):
        values: dict[str, object] = {}
        for key in ("mastered", "weak"):
            raw = knowledge.get(key)
            matches = (
                [item for item in raw if isinstance(item, str) and item in topics]
                if isinstance(raw, list)
                else []
            )
            if matches:
                values[key] = list(dict.fromkeys(matches))
        if values:
            known["knowledge_base"] = values
    preferences = profile.get("error_preferences")
    if isinstance(preferences, list) and _evidence(profile, "error_preferences"):
        errors: list[dict[str, str]] = []
        for item in preferences:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("topic"), str)
                or item.get("topic") not in topics
            ):
                continue
            selected = {
                key: item[key]
                for key in ("topic", "issue", "confusion_with")
                if isinstance(item.get(key), str) and 0 < len(item[key]) <= 200
            }
            if len(selected) > 1:
                errors.append(selected)
        if errors:
            known["error_preferences"] = errors[:3]
    style = profile.get("cognitive_style")
    if isinstance(style, dict) and _evidence(profile, "cognitive_style"):
        persona = style.get("preference_persona")
        if persona in {"performance", "engineering", "academic"}:
            known["preference_persona"] = persona
    return known


def _reviewed_resources(resources: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Serialize only typed resources; callers must pass review-passed content only."""
    selected: list[dict[str, object]] = []
    for resource in resources:
        resource_type = resource.get("resource_type")
        content = resource.get("content")
        if (
            isinstance(resource_type, str)
            and resource_type in _RESOURCE_TYPES
            and isinstance(content, dict)
        ):
            selected.append({"resource_type": resource_type, "content": content})
    return selected


def _path_context(path: Mapping[str, object] | None) -> dict[str, object]:
    """Extract the compact path signals a Tutor needs, dropping mastery internals."""
    if path is None:
        return {}
    context: dict[str, object] = {}
    for key in ("current_node_id", "next_node_id"):
        value = path.get(key)
        if isinstance(value, str) and value:
            context[key] = value
    prerequisite_node_ids = path.get("prerequisite_node_ids")
    if isinstance(prerequisite_node_ids, list):
        context["prerequisite_node_ids"] = [
            item for item in prerequisite_node_ids if isinstance(item, str)
        ]
    reasons = path.get("reasons")
    if isinstance(reasons, list):
        compact: list[dict[str, str]] = []
        for reason in reasons:
            if not isinstance(reason, dict):
                continue
            kind = reason.get("kind")
            summary = reason.get("summary")
            if isinstance(kind, str) and isinstance(summary, str):
                compact.append({"kind": kind, "summary": summary})
        if compact:
            context["reasons"] = compact
    return context


def build_classroom_context(
    graph: KnowledgeGraphRepository,
    *,
    node_id: str,
    goal: str,
    reviewed_resources: Sequence[Mapping[str, object]] = (),
    profile: Mapping[str, object] | None = None,
    path: Mapping[str, object] | None = None,
) -> ClassroomTurnContext:
    """Build the minimal reference context for one orchestrated classroom turn."""
    node = graph.get_node(node_id)
    if node is None or not goal.strip():
        raise ValueError("Classroom context inputs are unavailable.")
    prerequisites = [graph.get_node(key) for key in node.prerequisites]
    if any(item is None for item in prerequisites):
        raise ValueError("Classroom prerequisites are unavailable.")
    topics = {node.id, node.name}
    for item in prerequisites:
        assert item is not None
        topics.update((item.id, item.name))
    payload: dict[str, object] = {
        "context_version": CLASSROOM_CONTEXT_VERSION,
        "graph_version": graph.graph_version,
        "node": {
            "id": node.id,
            "name": node.name,
            "description": node.description,
            "difficulty": node.difficulty,
            "learning_objectives": list(node.learning_objectives),
            "common_misconceptions": list(node.common_misconceptions),
            "ai_context": node.ai_context,
        },
        "prerequisites": [
            {"id": item.id, "name": item.name, "description": item.description}
            for item in prerequisites
            if item is not None
        ],
        "goal": goal.strip(),
        "reviewed_resources": _reviewed_resources(reviewed_resources),
        "known_profile": _known_profile(profile or {}, topics),
        "path": _path_context(path),
    }
    return ClassroomTurnContext(json.dumps(payload, ensure_ascii=False, sort_keys=True))
