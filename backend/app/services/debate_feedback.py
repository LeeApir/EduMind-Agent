"""Explicit perspective evidence, idempotent receipt, and deterministic profile merge."""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.profile_schema import (
    ProfileSchemaError,
    merge_explicit_profile_values,
    merge_profile_snapshots,
)
from app.models.learning import LearningOperation, StudentProfile
from app.models.learning_state import LearningEvidence
from app.services.debate_publication import owned_debate_result
from app.services.learning_operations import IdempotencyConflict
from app.services.learning_owner_lock import lock_learning_owner
from app.services.owned_learning import latest_profile, visible_unit
from app.services.profile_updates import (
    ProfileVersionConflict,
    persist_profile_version,
    snapshot_profile,
)

PERSPECTIVES = frozenset({"performance", "engineering", "academic"})
DEBATE_FEEDBACK_RULE_VERSION = "debate-perspective-feedback-v1"


class DebateFeedbackNotFound(ValueError):
    """The result is absent or belongs to another owner."""


@dataclass(frozen=True, slots=True)
class DebateFeedbackReceipt:
    evidence_id: UUID
    profile_version: int | None
    update_status: str


def _digest(unit_id: UUID, result_id: UUID, perspective: str) -> str:
    payload = {"unit_id": str(unit_id), "result_id": str(result_id),
               "perspective": perspective, "feedback": "helpful"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _profile_receipt(
    evidence_id: UUID, profile: StudentProfile, perspective: str,
) -> DebateFeedbackReceipt:
    style = profile.cognitive_style or {}
    status = "updated" if style.get("preference_persona") == perspective else "unchanged"
    return DebateFeedbackReceipt(evidence_id, profile.version, status)


async def _profile_for_feedback(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID,
    perspective: str, evidence: LearningEvidence,
) -> DebateFeedbackReceipt:
    profile_key = f"debate-feedback-{evidence.id}"
    existing = await db.scalar(select(StudentProfile).where(
        StudentProfile.user_id == owner_id,
        StudentProfile.idempotency_key == profile_key,
    ))
    if existing is not None:
        return _profile_receipt(evidence.id, existing, perspective)
    for _ in range(3):
        latest = await latest_profile(db, owner_id)
        goal = latest.initial_query if latest is not None else await db.scalar(
            select(LearningOperation.goal).where(
                LearningOperation.user_id == owner_id,
                LearningOperation.learning_unit_id == unit_id,
            ).order_by(LearningOperation.created_at.desc()).limit(1)
        )
        if not isinstance(goal, str) or not goal.strip():
            return DebateFeedbackReceipt(evidence.id, None, "pending")
        version = 1 if latest is None else latest.version + 1
        style = dict(latest.cognitive_style or {}) if latest is not None else {}
        style["preference_persona"] = perspective
        candidate = merge_explicit_profile_values(
            goal,
            {"cognitive_style": style},
            {"cognitive_style": [{
                "source": "explicit_feedback", "confidence": 0.9,
                "observed_at": evidence.created_at.isoformat(),
                "profile_version": version,
            }]},
            profile_version=version,
        )
        try:
            if latest is not None:
                merged = merge_profile_snapshots(snapshot_profile(latest), candidate)
            else:
                merged = candidate
            saved = await persist_profile_version(
                db, owner_id=owner_id, profile=merged,
                idempotency_key=profile_key,
                request_digest=evidence.request_digest,
            )
            return _profile_receipt(evidence.id, saved, perspective)
        except ProfileVersionConflict:
            await db.rollback()
            existing = await db.scalar(select(StudentProfile).where(
                StudentProfile.user_id == owner_id,
                StudentProfile.idempotency_key == profile_key,
            ))
            if existing is not None:
                return _profile_receipt(evidence.id, existing, perspective)
            continue
        except ProfileSchemaError:
            return DebateFeedbackReceipt(evidence.id, None, "failed")
    return DebateFeedbackReceipt(evidence.id, None, "pending")


async def record_debate_feedback(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID, result_id: UUID,
    perspective: str, idempotency_key: str,
) -> DebateFeedbackReceipt:
    if perspective not in PERSPECTIVES:
        raise ValueError("Unsupported perspective.")
    digest = _digest(unit_id, result_id, perspective)
    await lock_learning_owner(db, owner_id)
    existing = await db.scalar(select(LearningEvidence).where(
        LearningEvidence.user_id == owner_id,
        LearningEvidence.idempotency_key == idempotency_key,
    ))
    if existing is not None and existing.request_digest != digest:
        raise IdempotencyConflict("Idempotency key conflicts with another feedback.")
    if existing is None:
        result = await owned_debate_result(
            db, owner_id=owner_id, unit_id=unit_id, result_id=result_id,
        )
        unit = await visible_unit(db, owner_id, unit_id)
        if result is None or unit is None or not unit.knowledge_point_id:
            raise DebateFeedbackNotFound
        existing = await db.scalar(select(LearningEvidence).where(
            LearningEvidence.user_id == owner_id,
            LearningEvidence.evidence_type == "explicit_feedback",
            LearningEvidence.payload["debate_result_id"].astext == str(result_id),
            LearningEvidence.payload["perspective"].astext == perspective,
        ).limit(1))
        if existing is None:
            existing = LearningEvidence(
                user_id=owner_id, idempotency_key=idempotency_key,
                request_digest=digest, evidence_type="explicit_feedback",
                knowledge_node_id=unit.knowledge_point_id,
                learning_unit_id=unit_id, schema_version=1,
                rule_version=DEBATE_FEEDBACK_RULE_VERSION,
                payload={"action": "helpful", "perspective": perspective,
                         "debate_result_id": str(result.id),
                         "debate_result_version": result.scene_version,
                         "scene_key": result.scene_key},
            )
            db.add(existing)
            await db.commit()
    return await _profile_for_feedback(
        db, owner_id=owner_id, unit_id=unit_id,
        perspective=perspective, evidence=existing,
    )
