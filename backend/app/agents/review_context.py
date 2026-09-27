"""Immutable, minimal course and learner reference for formal resource review."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

from app.agents.profile_schema import EVIDENCE_SOURCES
from app.services.knowledge_graph import KnowledgeGraphRepository

REVIEW_CONTEXT_VERSION = "resource-review-context-v1"


@dataclass(frozen=True, slots=True)
class ResourceReviewContext:
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
    return selected[-3:]


def build_review_context(
    graph: KnowledgeGraphRepository,
    *,
    node_id: str,
    profile_version: int,
    profile: Mapping[str, object],
    code_language: str,
) -> ResourceReviewContext:
    node = graph.get_node(node_id)
    if node is None or profile_version < 1 or not code_language.strip():
        raise ValueError("Review context inputs are unavailable.")
    prerequisites = [graph.get_node(key) for key in node.prerequisites]
    if any(item is None for item in prerequisites):
        raise ValueError("Review prerequisites are unavailable.")
    topics = {node.id, node.name}
    for item in prerequisites:
        assert item is not None
        topics.update((item.id, item.name))
    known: dict[str, object] = {}
    knowledge = profile.get("knowledge_base")
    evidence = _evidence(profile, "knowledge_base")
    if isinstance(knowledge, dict) and evidence:
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
            known["knowledge_base"] = {"value": values, "evidence": evidence}
    preferences = profile.get("error_preferences")
    evidence = _evidence(profile, "error_preferences")
    if isinstance(preferences, list) and evidence:
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
            known["error_preferences"] = {"value": errors[:3], "evidence": evidence}
    payload = {
        "context_version": REVIEW_CONTEXT_VERSION,
        "graph_version": graph.graph_version,
        "profile_version": profile_version,
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
        "relations": [
            {"from": item.from_node_id, "to": item.to_node_id, "type": item.relation_type.value}
            for item in graph.outgoing_relations(node.id)
        ],
        "code_language": code_language.strip(),
        "known_profile": known,
    }
    return ResourceReviewContext(json.dumps(payload, ensure_ascii=False, sort_keys=True))
