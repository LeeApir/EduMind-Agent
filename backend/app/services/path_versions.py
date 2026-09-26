"""Persist immutable path versions from one committed owner-state snapshot."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning_state import (
    LearningPathCurrent,
    LearningPathVersion,
    NodeMasteryCurrent,
    NodeMasteryRevision,
)
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_owner_lock import lock_learning_owner
from app.services.owned_learning import latest_profile
from app.services.path_rules import PATH_RULE_VERSION, PathMastery, plan_learning_path


class PathVersionError(ValueError):
    """A durable path cannot be created from the current owner state."""


async def current_path_version(
    db: AsyncSession, *, owner_id: UUID, target_node_id: str
) -> LearningPathVersion | None:
    current = await db.scalar(
        select(LearningPathCurrent).where(
            LearningPathCurrent.user_id == owner_id,
            LearningPathCurrent.target_node_id == target_node_id,
        )
    )
    if current is None:
        return None
    return await db.get(LearningPathVersion, current.path_version_id)


async def plan_or_replan_path(
    db: AsyncSession,
    *,
    owner_id: UUID,
    target_node_id: str,
    graph: KnowledgeGraphRepository,
    trigger_reason: str,
    commit: bool = True,
) -> tuple[LearningPathVersion, bool]:
    """Atomically replace the pointer only after reading locked profile/mastery inputs."""
    if trigger_reason not in {
        "initial_plan",
        "learner_request",
        "mastery_changed",
        "profile_changed",
    }:
        raise PathVersionError("Unsupported path trigger reason.")
    await lock_learning_owner(db, owner_id)
    profile = await latest_profile(db, owner_id)
    if profile is None:
        raise PathVersionError("A persisted profile is required for path planning.")

    mastery_rows = (
        await db.execute(
            select(NodeMasteryCurrent, NodeMasteryRevision)
            .join(NodeMasteryRevision, NodeMasteryRevision.id == NodeMasteryCurrent.revision_id)
            .where(NodeMasteryCurrent.user_id == owner_id)
            .order_by(NodeMasteryCurrent.knowledge_node_id)
        )
    ).all()
    mastery = {
        current.knowledge_node_id: PathMastery(
            score=current.score,
            status=current.status,
            evidence_summary=tuple(str(item) for item in revision.evidence_summary),
        )
        for current, revision in mastery_rows
    }
    # Each revision increments exactly once, so the sum is an owner-wide monotonic watermark.
    mastery_watermark = sum(current.revision for current, _ in mastery_rows)
    decision = plan_learning_path(
        graph,
        target_node_id=target_node_id,
        mastery=mastery,
        profile={"engineering_preference": profile.engineering_preference},
    )
    pointer = await db.scalar(
        select(LearningPathCurrent)
        .where(
            LearningPathCurrent.user_id == owner_id,
            LearningPathCurrent.target_node_id == target_node_id,
        )
        .with_for_update()
    )
    previous = await db.get(LearningPathVersion, pointer.path_version_id) if pointer else None
    if (
        previous is not None
        and previous.graph_version == graph.graph_version
        and previous.profile_version == profile.version
        and previous.mastery_revision_watermark == mastery_watermark
        and previous.planner_rule_version == PATH_RULE_VERSION
    ):
        if pointer is not None and pointer.replan_required:
            pointer.replan_required = False
            if commit:
                await db.commit()
        return previous, False

    nodes = [
        {
            "node_id": step.node_id,
            "score": step.score,
            "status": step.status,
            "cost": step.cost,
            "recommended_resource": step.recommended_resource,
            "estimated_minutes": step.estimated_minutes,
            "reason": dict(step.reason),
        }
        for step in decision.steps
    ]
    old_ids: list[str] = []
    if previous is not None:
        for item in previous.nodes:
            if not isinstance(item, dict) or not isinstance(item.get("node_id"), str):
                raise PathVersionError("Stored path nodes are invalid.")
            old_ids.append(item["node_id"])
    new_ids = [step.node_id for step in decision.steps]
    change_reason: dict[str, object] = {
        "kind": "initial_plan" if previous is None else "path_change",
        "trigger": trigger_reason,
        "added_node_ids": [node_id for node_id in new_ids if node_id not in old_ids],
        "removed_node_ids": [node_id for node_id in old_ids if node_id not in new_ids],
        "reordered_node_ids": [
            node_id
            for node_id in new_ids
            if node_id in old_ids and old_ids.index(node_id) != new_ids.index(node_id)
        ],
    }
    version = LearningPathVersion(
        user_id=owner_id,
        target_node_id=target_node_id,
        version=1 if previous is None else previous.version + 1,
        graph_version=graph.graph_version,
        profile_version=profile.version,
        mastery_revision_watermark=mastery_watermark,
        planner_rule_version=PATH_RULE_VERSION,
        nodes=nodes,
        current_node_id=decision.current_node_id,
        prerequisite_node_ids=list(decision.prerequisite_node_ids),
        next_node_id=decision.next_node_id,
        reasons=[change_reason, *(dict(step.reason) for step in decision.steps)],
        previous_path_id=previous.id if previous else None,
    )
    db.add(version)
    await db.flush()
    if pointer is None:
        db.add(
            LearningPathCurrent(
                user_id=owner_id,
                target_node_id=target_node_id,
                path_version_id=version.id,
                replan_required=False,
            )
        )
    else:
        pointer.path_version_id = version.id
        pointer.replan_required = False
    if commit:
        await db.commit()
    else:
        await db.flush()
    return version, True
