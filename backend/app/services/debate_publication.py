"""Owner-scoped reservation, whole-result publication, and classroom return."""

from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.debate_candidate_schema import validate_debate_candidate
from app.agents.debate_review import DEBATE_REVIEW_VERSION, DebateReviewOutcome
from app.models.classroom import ClassroomOperation, ClassroomSession, DebateResult
from app.models.learning import LearningScene, LearningUnit, utc_now
from app.services.classroom import (
    ClassroomNotFound,
    ClassroomVersionConflict,
    _find_operation,
    classroom_digest,
    classroom_payload,
    owned_classroom,
)
from app.services.learning_operations import IdempotencyConflict
from app.services.learning_owner_lock import lock_learning_owner
from app.services.owned_learning import latest_profile, visible_unit

DEBATE_SCENE_KEY = "array-vs-linked-list"


class DebateAlreadyActive(ValueError):
    """Another debate operation or detour already owns this classroom."""


@dataclass(frozen=True, slots=True)
class DebateReservation:
    operation: ClassroomOperation
    session: ClassroomSession
    created: bool


@dataclass(frozen=True, slots=True)
class DebateMaterials:
    profile: dict[str, object] | None
    profile_version: int | None


def _digest(unit_id: UUID, preset: str, question: str) -> str:
    return classroom_digest({
        "kind": "debate", "unit_id": str(unit_id), "preset": preset,
        "question": question.strip(),
    })


async def reserve_debate(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID, preset: str,
    question: str, idempotency_key: str, expected_revision: int,
) -> DebateReservation:
    if preset != DEBATE_SCENE_KEY or not 1 <= len(question.strip()) <= 1000:
        raise ValueError("Unsupported debate request.")
    digest = _digest(unit_id, preset, question)
    existing = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if existing is None:
        await lock_learning_owner(db, owner_id)
        existing = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if existing is not None:
        if existing.kind != "debate" or existing.request_digest != digest:
            raise IdempotencyConflict("Idempotency key conflicts with another command.")
        session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
        if session is None:
            raise ClassroomNotFound
        return DebateReservation(existing, session, False)
    session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
    unit = await visible_unit(db, owner_id, unit_id)
    if session is None or unit is None:
        raise ClassroomNotFound
    if session.revision != expected_revision:
        raise ClassroomVersionConflict(session.revision)
    if session.detour is not None:
        raise DebateAlreadyActive
    active = await db.scalar(select(ClassroomOperation.id).where(
        ClassroomOperation.user_id == owner_id,
        ClassroomOperation.learning_unit_id == unit_id,
        ClassroomOperation.kind == "debate",
        ClassroomOperation.status.in_(("accepted", "running")),
    ).limit(1))
    if active is not None:
        raise DebateAlreadyActive
    operation = ClassroomOperation(
        user_id=owner_id, learning_unit_id=unit_id, kind="debate",
        idempotency_key=idempotency_key, request_digest=digest,
        base_revision=session.revision, generation_id=session.generation_id,
        status="accepted",
        result_snapshot={
            "preset": preset, "question": question.strip(),
            "return_point": {
                "scene_key": session.scene_key,
                "scene_version": session.scene_version,
                "scene_progress": session.scene_progress,
                "mode": session.mode, "enabled_roles": list(session.enabled_roles),
                "paused": session.paused,
            },
        },
    )
    db.add(operation)
    await db.commit()
    return DebateReservation(operation, session, True)


async def debate_materials(db: AsyncSession, *, owner_id: UUID) -> DebateMaterials:
    profile = await latest_profile(db, owner_id)
    if profile is None:
        return DebateMaterials(None, None)
    return DebateMaterials({
        "knowledge_base": profile.knowledge_base,
        "cognitive_style": profile.cognitive_style,
        "evidence": profile.evidence,
    }, profile.version)


async def fail_debate(
    db: AsyncSession, *, owner_id: UUID, operation_id: UUID, code: str,
    status: str = "failed", retryable: bool = False,
) -> None:
    operation = await db.scalar(select(ClassroomOperation).where(
        ClassroomOperation.id == operation_id,
        ClassroomOperation.user_id == owner_id,
        ClassroomOperation.kind == "debate",
    ))
    if operation is not None and operation.status in {"accepted", "running"}:
        operation.status = status
        operation.error = {
            "code": code, "message": "Debate result was not published.",
            "retryable": retryable,
        }
        operation.updated_at = utc_now()
        await db.commit()


async def publish_debate(
    db: AsyncSession, *, owner_id: UUID, operation_id: UUID,
    review: DebateReviewOutcome,
) -> DebateResult | None:
    """Commit all perspectives, moderator, and detour as one CAS transaction."""
    if not review.approved or not review.review_model_id:
        return None
    await lock_learning_owner(db, owner_id)
    operation = await db.scalar(select(ClassroomOperation).where(
        ClassroomOperation.id == operation_id,
        ClassroomOperation.user_id == owner_id,
        ClassroomOperation.kind == "debate",
    ))
    if operation is None:
        raise ClassroomNotFound
    if operation.status == "published" and operation.result_id is not None:
        return await owned_debate_result(
            db, owner_id=owner_id, unit_id=operation.learning_unit_id,
            result_id=operation.result_id,
        )
    if operation.status not in {"accepted", "running"}:
        return None
    session = await owned_classroom(
        db, owner_id=owner_id, unit_id=operation.learning_unit_id,
    )
    snapshot = operation.result_snapshot or {}
    return_point = snapshot.get("return_point")
    if not isinstance(return_point, dict) or session is None:
        raise ClassroomNotFound
    if (
        session.revision != operation.base_revision
        or session.generation_id != operation.generation_id
        or session.scene_key != return_point.get("scene_key")
        or session.scene_version != return_point.get("scene_version")
        or session.detour is not None
    ):
        operation.status = "superseded"
        operation.error = {"code": "CLASSROOM_VERSION_CONFLICT",
                           "message": "Classroom changed before publication.", "retryable": False}
        operation.updated_at = utc_now()
        await db.commit()
        return None
    raw_content = dict(review.candidate.content)
    basis = raw_content.pop("graph_basis", None)
    validated = validate_debate_candidate(raw_content)
    if not isinstance(basis, dict):
        raise ValueError("Graph basis is unavailable.")
    question = snapshot.get("question")
    if not isinstance(question, str):
        raise ValueError("Question is unavailable.")
    result = DebateResult(
        user_id=owner_id, learning_unit_id=operation.learning_unit_id,
        operation_id=operation.id, scene_key=DEBATE_SCENE_KEY, scene_version=1,
        question=question, content={**validated, "graph_basis": basis},
        candidate_schema_version=review.candidate.schema_version,
        candidate_prompt_version=review.candidate.prompt_version,
        generation_model_id=review.candidate.model_id,
        review_version=DEBATE_REVIEW_VERSION,
        review_model_id=review.review_model_id,
        correction_attempts=review.correction_attempts,
    )
    db.add(result)
    await db.flush()
    session.detour = {"kind": "debate", "result_id": str(result.id), **return_point}
    session.scene_key = DEBATE_SCENE_KEY
    session.scene_version = 1
    session.scene_progress = 0
    session.mode = "focus"
    session.enabled_roles = []
    session.paused = True
    session.revision += 1
    session.generation_id = uuid4()
    session.updated_at = utc_now()
    operation.status = "published"
    operation.result_id = result.id
    operation.result_snapshot = {
        **snapshot, "result_id": str(result.id), "scene_version": result.scene_version,
    }
    operation.updated_at = utc_now()
    await db.commit()
    return result


async def owned_debate_result(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID, result_id: UUID
) -> DebateResult | None:
    return cast(DebateResult | None, await db.scalar(select(DebateResult).where(
        DebateResult.id == result_id,
        DebateResult.user_id == owner_id,
        DebateResult.learning_unit_id == unit_id,
    )))


def debate_result_payload(result: DebateResult) -> dict[str, object]:
    content = result.content
    moderator = content.get("moderator")
    assert isinstance(moderator, dict)
    summary = "\n\n".join(str(moderator[field]) for field in (
        "objective_conclusion", "tradeoffs", "learner_advice",
    ))
    return {
        "id": str(result.id), "scene_key": result.scene_key,
        "scene_version": result.scene_version, "status": "published",
        "question": result.question,
        "question_conditions": content["question_conditions"],
        "graph_basis": content["graph_basis"],
        "perspectives": content["perspectives"],
        "moderator": moderator,
        "moderator_summary": summary,
        "candidate_schema_version": result.candidate_schema_version,
        "candidate_prompt_version": result.candidate_prompt_version,
        "generation_model_id": result.generation_model_id,
        "review_version": result.review_version,
        "review_model_id": result.review_model_id,
        "correction_attempts": result.correction_attempts,
    }


async def exit_debate(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID, result_id: UUID,
    idempotency_key: str, expected_revision: int,
) -> tuple[dict[str, object], bool]:
    digest = classroom_digest({
        "kind": "debate_exit", "unit_id": str(unit_id), "result_id": str(result_id),
    })
    existing = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if existing is None:
        await lock_learning_owner(db, owner_id)
        existing = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if existing is not None:
        if existing.kind != "control" or existing.request_digest != digest:
            raise IdempotencyConflict("Idempotency key conflicts with another command.")
        if existing.result_snapshot is None:
            raise ValueError("Original exit receipt is unavailable.")
        return existing.result_snapshot, False
    result = await owned_debate_result(
        db, owner_id=owner_id, unit_id=unit_id, result_id=result_id,
    )
    session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
    if result is None or session is None:
        raise ClassroomNotFound
    if session.revision != expected_revision:
        raise ClassroomVersionConflict(session.revision)
    detour = session.detour
    if (
        not isinstance(detour, dict) or detour.get("kind") != "debate"
        or detour.get("result_id") != str(result_id)
    ):
        raise DebateAlreadyActive("This result is not the current detour.")
    scene_key = detour.get("scene_key")
    if not isinstance(scene_key, str):
        raise ClassroomNotFound
    latest = await db.scalar(select(LearningScene).join(
        LearningUnit, LearningUnit.id == LearningScene.learning_unit_id,
    ).where(
        LearningUnit.id == unit_id, LearningUnit.user_id == owner_id,
        LearningScene.scene_key == scene_key,
        LearningScene.generation_status == "complete",
        LearningScene.review_status == "passed",
    ).order_by(LearningScene.version.desc()).limit(1))
    if latest is None:
        raise ClassroomNotFound
    original_version = detour.get("scene_version")
    changed = latest.version != original_version
    session.scene_key = scene_key
    session.scene_version = latest.version
    session.scene_progress = cast(int, detour["scene_progress"])
    session.mode = cast(str, detour["mode"])
    session.enabled_roles = cast(list[object], detour["enabled_roles"])
    session.paused = cast(bool, detour["paused"])
    session.detour = None
    session.revision += 1
    session.generation_id = uuid4()
    session.updated_at = utc_now()
    receipt = {**classroom_payload(session), "version_changed": changed}
    db.add(ClassroomOperation(
        user_id=owner_id, learning_unit_id=unit_id, kind="control",
        idempotency_key=idempotency_key, request_digest=digest,
        base_revision=expected_revision, generation_id=session.generation_id,
        result_snapshot=receipt, status="published",
    ))
    await db.commit()
    return receipt, True
