"""Commit scored quiz attempts as immutable owner-scoped learning evidence."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.learning_resource_schema import RESOURCE_PROMPT_VERSION
from app.models.learning import LearningUnit
from app.models.learning_state import LearningEvidence
from app.services.learning_operations import IdempotencyConflict
from app.services.mastery_updates import apply_mastery_evidence, lock_mastery_node
from app.services.owned_learning import published_resource
from app.services.quiz_scoring import QuizScoringError, score_exercise_content


class QuizResourceNotFound(ValueError):
    """The resource is absent, foreign, unreviewed, or otherwise not visible."""


def quiz_request_digest(
    *, resource_id: UUID, resource_version: int, answers: list[dict[str, str]]
) -> str:
    """Treat answer ordering as irrelevant for owner-scoped idempotency."""
    canonical = json.dumps(
        {
            "resource_id": str(resource_id),
            "resource_version": resource_version,
            "answers": sorted(answers, key=lambda item: item["question_id"]),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def quiz_receipt(record: LearningEvidence) -> dict[str, object]:
    """Replay the original committed score without re-reading an answer key."""
    payload = record.payload
    return {
        "evidence_id": str(record.id),
        "resource_id": str(record.resource_id),
        "resource_version": record.resource_version,
        "question_results": payload["question_results"],
        "score": payload["score"],
        "correct_count": payload["correct_count"],
        "question_count": payload["question_count"],
        "quiz_schema_version": record.schema_version,
        "scoring_rule_version": record.rule_version,
        "mastery_changes": payload.get("mastery_changes", []),
        "path_replan_required": payload.get("path_replan_required", False),
    }


async def _existing_receipt(
    db: AsyncSession, *, owner_id: UUID, idempotency_key: str, digest: str
) -> LearningEvidence | None:
    existing = await db.scalar(
        select(LearningEvidence).where(
            LearningEvidence.user_id == owner_id,
            LearningEvidence.idempotency_key == idempotency_key,
        )
    )
    if existing is not None and existing.request_digest != digest:
        raise IdempotencyConflict("Idempotency key was reused for another quiz submission.")
    return existing


async def submit_quiz_attempt(
    db: AsyncSession,
    *,
    owner_id: UUID,
    idempotency_key: str,
    resource_id: UUID,
    resource_version: int,
    answers: list[dict[str, str]],
) -> tuple[LearningEvidence, bool]:
    """Validate, score, and append one fact; never update an earlier attempt."""
    digest = quiz_request_digest(
        resource_id=resource_id, resource_version=resource_version, answers=answers
    )
    existing = await _existing_receipt(
        db, owner_id=owner_id, idempotency_key=idempotency_key, digest=digest
    )
    if existing is not None:
        return existing, False

    resource = await published_resource(db, owner_id, resource_id)
    if resource is None:
        raise QuizResourceNotFound
    if (
        resource.resource_type != "exercise"
        or resource.version != resource_version
        or not isinstance(resource.generation_metadata, dict)
        or resource.generation_metadata.get("prompt_version") != RESOURCE_PROMPT_VERSION
    ):
        raise QuizScoringError
    unit = await db.get(LearningUnit, resource.learning_unit_id)
    knowledge_node_id = resource.knowledge_point_id or (unit.knowledge_point_id if unit else None)
    if not knowledge_node_id:
        raise QuizScoringError

    scored = score_exercise_content(
        resource_id=resource.id,
        resource_version=resource.version,
        content=resource.content,
        answers=answers,
    )
    payload: dict[str, object] = {
        "answers": sorted(answers, key=lambda item: item["question_id"]),
        "score": scored.score,
        "correct_count": scored.correct_count,
        "question_count": scored.question_count,
        "question_results": [
            {
                "question_id": result.question_id,
                "correct": result.correct,
                "explanation": result.explanation,
                "error_patterns": list(result.error_patterns),
            }
            for result in scored.question_results
        ],
    }
    record = LearningEvidence(
        user_id=owner_id,
        idempotency_key=idempotency_key,
        request_digest=digest,
        evidence_type="quiz_attempt",
        knowledge_node_id=knowledge_node_id,
        learning_unit_id=resource.learning_unit_id,
        scene_id=resource.scene_id,
        resource_id=resource.id,
        resource_version=resource.version,
        schema_version=scored.schema_version,
        rule_version=scored.rule_version,
        payload=payload,
    )
    await lock_mastery_node(db, owner_id=owner_id, node_id=knowledge_node_id)
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
        raced = await _existing_receipt(
            db, owner_id=owner_id, idempotency_key=idempotency_key, digest=digest
        )
        if raced is None:
            raise
        return raced, False
    return record, True
