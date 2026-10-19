"""Trusted teaching selection, distinct from path advice and model-generated goals."""

from copy import deepcopy
from dataclasses import asdict
from typing import Any
from uuid import UUID

from app.models.learning_state import LearningPathVersion
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_contract import LearningContractError, canonical, digest

TEACHING_BINDING_VERSION = "teaching-node-binding-v1"
CONTEXT_KEYS = {
    "version",
    "teaching_mode",
    "target_node_id",
    "recommended_node_id",
    "teaching_node_id",
    "selection_reason",
    "original_request",
    "segment_goal",
    "segment_scope",
    "path_version_id",
    "path_version",
    "graph_version",
    "graph_digest",
}


def graph_digest(graph: KnowledgeGraphRepository) -> str:
    return digest("graph", "graph-snapshot-v1", nodes=[asdict(n) for n in graph.all_nodes()])


def validate_teaching_context(value: object) -> dict[str, Any]:
    try:
        if not isinstance(value, dict) or set(value) != CONTEXT_KEYS:
            raise ValueError
        c = deepcopy(value)
        if c["version"] != TEACHING_BINDING_VERSION or c["teaching_mode"] not in (
            "target",
            "recommended",
        ):
            raise ValueError
        for key in (
            "target_node_id",
            "teaching_node_id",
            "original_request",
            "segment_goal",
            "graph_version",
        ):
            if not isinstance(c[key], str) or not c[key].strip():
                raise ValueError
        if not isinstance(c["graph_digest"], str) or len(c["graph_digest"]) != 64:
            raise ValueError
        int(c["graph_digest"], 16)
        recommended = c["recommended_node_id"]
        if recommended is not None and (not isinstance(recommended, str) or not recommended):
            raise ValueError
        if c["path_version_id"] is None:
            if c["path_version"] is not None or recommended is not None:
                raise ValueError
        else:
            UUID(c["path_version_id"])
            if type(c["path_version"]) is not int or c["path_version"] < 1:
                raise ValueError
        if c["teaching_mode"] == "target":
            reason = "direct_target"
            if c["teaching_node_id"] != c["target_node_id"]:
                raise ValueError
        else:
            if not recommended or c["teaching_node_id"] != recommended:
                raise ValueError
            reason = (
                "recommended_target"
                if recommended == c["target_node_id"]
                else "recommended_prerequisite"
            )
        scope = "prerequisite_segment" if reason == "recommended_prerequisite" else "target_lesson"
        if c["selection_reason"] != reason or c["segment_scope"] != scope:
            raise ValueError
        if scope == "target_lesson" and c["segment_goal"] != c["original_request"]:
            raise ValueError
        canonical(c)
        return c
    except (ValueError, TypeError, KeyError):
        raise LearningContractError("TEACHING_BINDING_MISMATCH") from None


def select_teaching_context(
    *,
    owner_id: UUID,
    target_node_id: str,
    original_request: str,
    mode: str,
    graph: KnowledgeGraphRepository,
    path: LearningPathVersion | None,
) -> dict[str, Any]:
    target = graph.get_node(target_node_id)
    if not target or mode not in ("target", "recommended"):
        raise LearningContractError("TEACHING_SELECTION_UNAVAILABLE")
    if path is not None and (
        path.user_id != owner_id
        or path.target_node_id != target_node_id
        or path.graph_version != graph.graph_version
        or path.current_node_id is not None
        and path.current_node_id
        not in {n.get("node_id") for n in path.nodes if isinstance(n, dict)}
    ):
        raise LearningContractError("TEACHING_SELECTION_UNAVAILABLE")
    recommended = path.current_node_id if path else None
    if recommended is not None and graph.get_node(recommended) is None:
        raise LearningContractError("TEACHING_SELECTION_UNAVAILABLE")
    selected = target_node_id if mode == "target" else recommended
    if selected is None:
        raise LearningContractError("TEACHING_SELECTION_UNAVAILABLE")
    teaching = graph.get_node(selected)
    assert teaching is not None
    prerequisite = mode == "recommended" and selected != target_node_id
    return validate_teaching_context(
        {
            "version": TEACHING_BINDING_VERSION,
            "teaching_mode": mode,
            "target_node_id": target_node_id,
            "recommended_node_id": recommended,
            "teaching_node_id": selected,
            "selection_reason": "direct_target"
            if mode == "target"
            else "recommended_prerequisite"
            if prerequisite
            else "recommended_target",
            "original_request": original_request,
            "segment_goal": (
                f"为学习{target.name}，本节先学习路径推荐的{teaching.name}。原目标尚待后续完成。"
            )
            if prerequisite
            else original_request,
            "segment_scope": "prerequisite_segment" if prerequisite else "target_lesson",
            "path_version_id": str(path.id) if path else None,
            "path_version": path.version if path else None,
            "graph_version": graph.graph_version,
            "graph_digest": graph_digest(graph),
        }
    )


def check_teaching_plan(context: object, metadata: dict[str, Any]) -> dict[str, Any]:
    c = validate_teaching_context(context)
    if any(
        metadata.get(k) != c[v]
        for k, v in (
            ("node_id", "teaching_node_id"),
            ("goal", "segment_goal"),
            ("graph_version", "graph_version"),
            ("graph_digest", "graph_digest"),
        )
    ):
        raise LearningContractError("TEACHING_BINDING_MISMATCH")
    return c
