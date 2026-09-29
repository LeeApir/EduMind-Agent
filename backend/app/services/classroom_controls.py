"""Durable owner-scoped classroom controls from ADR-0005 Decision C."""

import hashlib
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.animation import AnimationJob, AnimationResourceBinding
from app.models.classroom import ClassroomOperation
from app.models.learning import GeneratedResource, LearningScene, utc_now
from app.services.classroom import (
    ClassroomNotFound,
    ClassroomReplayUnavailable,
    ClassroomVersionConflict,
    _find_operation,
    classroom_digest,
    classroom_payload,
    owned_classroom,
)
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_events import record_learning_action
from app.services.learning_operations import IdempotencyConflict
from app.services.learning_owner_lock import lock_learning_owner
from app.services.owned_learning import visible_unit
from app.services.path_versions import current_path_version
from app.services.profile_updates import record_profile_event

_ACTIONS = frozenset({"pause", "resume", "skip", "prerequisite", "select_resource"})
_RESOURCE_TYPES = frozenset({"explanation", "code", "exercise", "animation"})


class ClassroomControlInvalid(ValueError):
    """The target is not a current reviewed resource or a recommended prerequisite."""


class ClassroomControlConflict(ValueError):
    """A current detour cannot be replaced by another control command."""


async def _scene(
    db: AsyncSession, *, unit_id: UUID, scene_key: str, version: int
) -> LearningScene | None:
    return cast(LearningScene | None, await db.scalar(
        select(LearningScene).where(
            LearningScene.learning_unit_id == unit_id,
            LearningScene.scene_key == scene_key,
            LearningScene.version == version,
            LearningScene.review_status == "passed",
            LearningScene.generation_status == "complete",
        )
    ))


async def _has_resource(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID,
    scene: LearningScene, resource_type: str,
) -> bool:
    if resource_type == "animation":
        return await db.scalar(
            select(AnimationResourceBinding.id)
            .join(AnimationJob, AnimationJob.id == AnimationResourceBinding.job_id)
            .where(
                AnimationResourceBinding.user_id == owner_id,
                AnimationResourceBinding.learning_unit_id == unit_id,
                AnimationResourceBinding.scene_id == scene.id,
                AnimationResourceBinding.scene_version == scene.version,
                AnimationJob.user_id == owner_id,
                AnimationJob.status == "succeeded",
            )
            .limit(1)
        ) is not None
    return await db.scalar(
        select(GeneratedResource.id).where(
            GeneratedResource.user_id == owner_id,
            GeneratedResource.learning_unit_id == unit_id,
            GeneratedResource.scene_id == scene.id,
            GeneratedResource.resource_type == resource_type,
            GeneratedResource.review_status == "passed",
            GeneratedResource.published_at.is_not(None),
        ).limit(1)
    ) is not None


async def _next_scene(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID,
    current: LearningScene,
) -> LearningScene | None:
    return cast(LearningScene | None, await db.scalar(
        select(LearningScene)
        .where(
            LearningScene.learning_unit_id == unit_id,
            LearningScene.scene_order > current.scene_order,
            LearningScene.review_status == "passed",
            LearningScene.generation_status == "complete",
            select(GeneratedResource.id).where(
                GeneratedResource.user_id == owner_id,
                GeneratedResource.learning_unit_id == unit_id,
                GeneratedResource.scene_id == LearningScene.id,
                GeneratedResource.review_status == "passed",
                GeneratedResource.published_at.is_not(None),
            ).exists(),
        )
        .order_by(LearningScene.scene_order, LearningScene.version.desc())
        .limit(1)
    ))


async def apply_classroom_control(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID,
    idempotency_key: str, expected_revision: int, action: str,
    resource_type: str | None, target_node_id: str | None,
    graph: KnowledgeGraphRepository,
) -> tuple[dict[str, object], bool]:
    """Apply one versioned control; replay its original immutable snapshot by key."""
    if action not in _ACTIONS:
        raise ClassroomControlInvalid
    if action == "select_resource":
        if resource_type not in _RESOURCE_TYPES or target_node_id is not None:
            raise ClassroomControlInvalid
    elif action == "prerequisite":
        if resource_type is not None or not target_node_id:
            raise ClassroomControlInvalid
    elif resource_type is not None or target_node_id is not None:
        raise ClassroomControlInvalid
    digest = classroom_digest({
        "kind": "control", "unit_id": str(unit_id), "action": action,
        "resource_type": resource_type, "target_node_id": target_node_id,
    })
    operation = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if operation is None:
        await lock_learning_owner(db, owner_id)
        operation = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if operation is not None:
        if operation.kind != "control" or operation.request_digest != digest:
            raise IdempotencyConflict("Idempotency key was reused for another command.")
        if operation.result_snapshot is None:
            raise ClassroomReplayUnavailable
        return operation.result_snapshot, False
    session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
    unit = await visible_unit(db, owner_id, unit_id)
    if session is None or unit is None or unit.knowledge_point_id is None:
        raise ClassroomNotFound
    if session.revision != expected_revision:
        raise ClassroomVersionConflict(session.revision)
    if session.detour is not None:
        if session.detour.get("kind") != "prerequisite" or action not in {"resume", "pause"}:
            raise ClassroomControlConflict
    scene = await _scene(
        db, unit_id=unit_id, scene_key=session.scene_key, version=session.scene_version
    )
    if scene is None:
        raise ClassroomNotFound
    base_scene_id = scene.id
    if action == "select_resource":
        assert resource_type is not None
        if not await _has_resource(
            db, owner_id=owner_id, unit_id=unit_id,
            scene=scene, resource_type=resource_type,
        ):
            raise ClassroomControlInvalid
    elif action == "prerequisite":
        assert target_node_id is not None
        path = await current_path_version(
            db, owner_id=owner_id, target_node_id=unit.knowledge_point_id,
        )
        prerequisites = {node.id for node in graph.prerequisites_for(unit.knowledge_point_id)}
        if (
            path is None or path.graph_version != graph.graph_version
            or target_node_id not in prerequisites
            or target_node_id not in path.prerequisite_node_ids
        ):
            raise ClassroomControlInvalid
        session.detour = {
            "kind": "prerequisite", "target_node_id": target_node_id,
            "path_version_id": str(path.id),
            "scene_key": session.scene_key, "scene_version": session.scene_version,
            "scene_progress": session.scene_progress,
            "mode": session.mode, "enabled_roles": list(session.enabled_roles),
            "paused": session.paused,
        }
        session.paused = True
    elif action == "skip":
        next_scene = await _next_scene(
            db, owner_id=owner_id, unit_id=unit_id, current=scene,
        )
        session.scene_progress += 1
        if next_scene is not None:
            session.scene_key = next_scene.scene_key
            session.scene_version = next_scene.version
    elif action == "pause":
        session.paused = True
    elif action == "resume":
        if session.detour is not None and session.detour.get("kind") == "prerequisite":
            session.detour = None
        session.paused = False
    session.revision += 1
    session.generation_id = uuid4()
    session.updated_at = utc_now()
    receipt = classroom_payload(session)
    db.add(ClassroomOperation(
        user_id=owner_id, learning_unit_id=unit_id, kind="control",
        idempotency_key=idempotency_key, request_digest=digest,
        base_revision=expected_revision, generation_id=session.generation_id,
        result_snapshot=receipt, status="published",
    ))
    evidence_key = "control:" + hashlib.sha256(idempotency_key.encode()).hexdigest()
    if action == "skip":
        await record_learning_action(
            db, owner_id=owner_id, idempotency_key=evidence_key,
            event_type="explicit_feedback", node_id=unit.knowledge_point_id,
            unit_id=unit_id, scene_id=base_scene_id, action="skip",
            repository=graph,
        )
    elif action == "select_resource":
        assert resource_type is not None
        await record_profile_event(
            db, owner_id=owner_id, idempotency_key=evidence_key,
            event={
                "event_type": "resource_selected",
                "knowledge_node_id": unit.knowledge_point_id,
                "learning_unit_id": str(unit_id),
                "scene_id": str(base_scene_id),
                "action": resource_type,
            },
        )
    await db.commit()
    return receipt, True
