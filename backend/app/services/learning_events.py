"""Validate learning actions against an owned, reviewed scene before recording facts."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.profile_events import ProfileEventSchemaError, validate_profile_event
from app.models.learning import LearningScene, LearningUnit
from app.models.learning_state import LearningEvidence
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_operations import IdempotencyConflict
from app.services.mastery_updates import apply_mastery_evidence, lock_mastery_node

BEHAVIOR_SCHEMA_VERSION = 1
BEHAVIOR_RULE_VERSION = "learning-behavior-v1"
MASTERY_ACTION_TYPES = frozenset({"hint_used", "reexplanation_requested", "explicit_feedback"})


class LearningEventNotFound(ValueError):
    """The learning context is absent, foreign, or not an approved scene."""


class LearningEventInvalid(ValueError):
    """The action does not satisfy the supported learning-event contract."""


def _event_digest(
    *, event_type: str, node_id: str, unit_id: UUID, scene_id: UUID, action: str
) -> str:
    canonical = json.dumps(
        {
            "event_type": event_type,
            "knowledge_node_id": node_id,
            "learning_unit_id": str(unit_id),
            "scene_id": str(scene_id),
            "action": action,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _hint_text(repository: KnowledgeGraphRepository, node_id: str, action: str) -> str:
    node = repository.get_node(node_id)
    if node is None:
        raise LearningEventNotFound
    if action == "hint_level_1":
        return f"回顾学习目标：{node.learning_objectives[0]}"
    return f"检查常见误区：{node.common_misconceptions[0]}"


def learning_event_receipt(record: LearningEvidence) -> dict[str, object]:
    payload = record.payload
    return {
        "evidence_id": str(record.id),
        "event_type": record.evidence_type,
        "action": payload["action"],
        "knowledge_node_id": record.knowledge_node_id,
        "hint_text": payload.get("hint_text"),
        "mastery_changes": payload.get("mastery_changes", []),
        "path_replan_required": payload.get("path_replan_required", False),
    }


async def _existing_event(
    db: AsyncSession, *, owner_id: UUID, key: str, digest: str
) -> LearningEvidence | None:
    existing = await db.scalar(
        select(LearningEvidence).where(
            LearningEvidence.user_id == owner_id,
            LearningEvidence.idempotency_key == key,
        )
    )
    if existing is not None and existing.request_digest != digest:
        raise IdempotencyConflict("Idempotency key was reused for another learning action.")
    return existing


async def record_learning_action(
    db: AsyncSession,
    *,
    owner_id: UUID,
    idempotency_key: str,
    event_type: str,
    node_id: str,
    unit_id: UUID,
    scene_id: UUID,
    action: str,
    repository: KnowledgeGraphRepository,
) -> tuple[LearningEvidence, bool]:
    """Append a verified action and project mastery in the same transaction."""
    if event_type not in MASTERY_ACTION_TYPES:
        raise LearningEventInvalid
    try:
        validate_profile_event(
            {
                "event_type": event_type,
                "knowledge_node_id": node_id,
                "learning_unit_id": str(unit_id),
                "scene_id": str(scene_id),
                "action": action,
            }
        )
    except ProfileEventSchemaError:
        raise LearningEventInvalid from None
    if not action:
        raise LearningEventInvalid
    digest = _event_digest(
        event_type=event_type,
        node_id=node_id,
        unit_id=unit_id,
        scene_id=scene_id,
        action=action,
    )
    existing = await _existing_event(db, owner_id=owner_id, key=idempotency_key, digest=digest)
    if existing is not None:
        return existing, False

    context = await db.execute(
        select(LearningUnit, LearningScene)
        .join(LearningScene, LearningScene.learning_unit_id == LearningUnit.id)
        .where(
            LearningUnit.id == unit_id,
            LearningUnit.user_id == owner_id,
            LearningUnit.status == "ready",
            LearningUnit.knowledge_point_id == node_id,
            LearningScene.id == scene_id,
            LearningScene.generation_status == "complete",
            LearningScene.review_status == "passed",
        )
    )
    if context.one_or_none() is None or repository.get_node(node_id) is None:
        raise LearningEventNotFound
    hint_text = _hint_text(repository, node_id, action) if event_type == "hint_used" else None
    payload: dict[str, object] = {"action": action}
    if hint_text is not None:
        payload["hint_text"] = hint_text
    record = LearningEvidence(
        user_id=owner_id,
        idempotency_key=idempotency_key,
        request_digest=digest,
        evidence_type=event_type,
        knowledge_node_id=node_id,
        learning_unit_id=unit_id,
        scene_id=scene_id,
        schema_version=BEHAVIOR_SCHEMA_VERSION,
        rule_version=BEHAVIOR_RULE_VERSION,
        payload=payload,
    )
    await lock_mastery_node(db, owner_id=owner_id, node_id=node_id)
    db.add(record)
    try:
        await db.flush()
        change, replan_required = await apply_mastery_evidence(db, record)
        record.payload = {
            **payload,
            "mastery_changes": [change] if change is not None else [],
            "path_replan_required": replan_required,
        }
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raced = await _existing_event(db, owner_id=owner_id, key=idempotency_key, digest=digest)
        if raced is None:
            raise
        return raced, False
    return record, True
