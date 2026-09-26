"""Durable path command replay and owner-scoped public projections."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning_state import LearningPathCommand, LearningPathCurrent, LearningPathVersion
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_operations import IdempotencyConflict
from app.services.learning_owner_lock import lock_learning_owner
from app.services.path_versions import current_path_version, plan_or_replan_path


class PathNotFound(ValueError):
    """No current path exists for this owner and target."""


class PathVersionConflict(ValueError):
    """The client version no longer matches the current path."""


async def execute_path_command(
    db: AsyncSession,
    *,
    owner_id: UUID,
    target_node_id: str,
    idempotency_key: str,
    graph: KnowledgeGraphRepository,
    action: str,
    reason: str,
    expected_version: int | None = None,
) -> LearningPathVersion:
    digest = hashlib.sha256(
        json.dumps(
            {
                "target": target_node_id,
                "action": action,
                "reason": reason,
                "expected_version": expected_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    await lock_learning_owner(db, owner_id)
    existing = await db.scalar(
        select(LearningPathCommand).where(
            LearningPathCommand.user_id == owner_id,
            LearningPathCommand.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_digest != digest:
            raise IdempotencyConflict("Path command key conflicts.")
        original = await db.get(LearningPathVersion, existing.path_version_id)
        if original is None:
            raise PathNotFound
        return original
    if action == "replan":
        current = await current_path_version(db, owner_id=owner_id, target_node_id=target_node_id)
        if current is None:
            raise PathNotFound
        if current.version != expected_version:
            raise PathVersionConflict
    result, _ = await plan_or_replan_path(
        db,
        owner_id=owner_id,
        target_node_id=target_node_id,
        graph=graph,
        trigger_reason=reason,
        commit=False,
    )
    db.add(
        LearningPathCommand(
            user_id=owner_id,
            target_node_id=target_node_id,
            idempotency_key=idempotency_key,
            request_digest=digest,
            path_version_id=result.id,
        )
    )
    await db.commit()
    return result


async def path_is_stale(db: AsyncSession, version: LearningPathVersion) -> bool:
    pointer = await db.get(LearningPathCurrent, (version.user_id, version.target_node_id))
    return pointer is None or pointer.path_version_id != version.id or pointer.replan_required


def path_payload(version: LearningPathVersion, *, is_stale: bool) -> dict[str, object]:
    nodes = [item for item in version.nodes if isinstance(item, dict)]
    reasons: list[dict[str, object]] = []
    changes: dict[str, object] = {}
    for item in version.reasons:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        node_id = item.get("node_id")
        if kind in {"initial_plan", "path_change"}:
            changes = dict(item)
            summary = (
                f"目标 {version.target_node_id}：{item.get('trigger')}；"
                f"新增 {item.get('added_node_ids')}；移除 {item.get('removed_node_ids')}。"
            )
            public_kind = "goal"
        elif kind == "prerequisite":
            summary = f"{node_id} 是 {item.get('required_by')} 的前置节点。"
            public_kind = "prerequisite"
        elif kind == "profile_field":
            summary = f"按明确画像字段 {item.get('field')} 推荐资源。"
            public_kind = "profile_field"
        else:
            summary = (
                f"{node_id} 的掌握度为 {item.get('score')}，状态 {item.get('status')}；"
                f"证据摘要 {item.get('evidence_summary', [])}。"
            )
            public_kind = "mastery_evidence"
        reason: dict[str, object] = {"kind": public_kind, "summary": summary}
        if isinstance(node_id, str):
            reason["knowledge_node_id"] = node_id
        reasons.append(reason)
    return {
        "version": version.version,
        "target_node_id": version.target_node_id,
        "graph_version": version.graph_version,
        "profile_version": version.profile_version,
        "mastery_revision_watermark": version.mastery_revision_watermark,
        "planner_rule_version": version.planner_rule_version,
        "nodes": [item["node_id"] for item in nodes],
        "node_details": [
            {key: value for key, value in item.items() if key != "reason"} for item in nodes
        ],
        "current_node_id": version.current_node_id,
        "prerequisite_node_ids": version.prerequisite_node_ids,
        "next_node_id": version.next_node_id,
        "reasons": reasons,
        "changes": changes,
        "is_stale": is_stale,
    }
