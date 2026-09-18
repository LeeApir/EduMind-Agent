"""Durable, owner-scoped lifecycle for SSE learning operations."""

import hashlib
import json
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningOperation

_ACTIVE_STATUSES = {
    "accepted",
    "preparing",
    "streaming_temporary",
    "temporary_complete",
    "reviewing",
}


class IdempotencyConflict(ValueError):
    """A key may not be reused by its owner for a different request."""


@dataclass(frozen=True, slots=True)
class OperationReservation:
    operation: LearningOperation
    created: bool


def request_digest(*, goal: str, preferred_language: str) -> str:
    value = json.dumps(
        {"goal": goal.strip(), "preferred_language": preferred_language},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()


async def reserve_operation(
    db: AsyncSession,
    *,
    owner_id: UUID,
    idempotency_key: str,
    goal: str,
    preferred_language: str,
) -> OperationReservation:
    """Create one operation or return the same owner-bound, same-payload record."""
    digest = request_digest(goal=goal, preferred_language=preferred_language)
    existing = await db.scalar(
        select(LearningOperation).where(
            LearningOperation.user_id == owner_id,
            LearningOperation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_digest != digest:
            raise IdempotencyConflict("Idempotency key was reused for another request.")
        return OperationReservation(existing, False)
    operation = LearningOperation(
        user_id=owner_id,
        idempotency_key=idempotency_key,
        request_digest=digest,
        goal=goal.strip(),
        preferred_language=preferred_language,
        status="accepted",
    )
    db.add(operation)
    await db.commit()
    return OperationReservation(operation, True)


async def owned_operation(
    db: AsyncSession, *, owner_id: UUID, operation_id: UUID
) -> LearningOperation | None:
    return cast(
        LearningOperation | None,
        await db.scalar(
            select(LearningOperation).where(
                LearningOperation.id == operation_id,
                LearningOperation.user_id == owner_id,
            )
        ),
    )


async def fail_interrupted_operation(
    db: AsyncSession, operation: LearningOperation
) -> LearningOperation:
    """A newly observed active record survived a process break; never resume temp text."""
    if operation.status in _ACTIVE_STATUSES:
        operation.status = "failed"
        operation.error = {
            "code": "INTERRUPTED",
            "message": "Generation was interrupted before formal resources were published.",
            "retryable": True,
        }
        await db.commit()
    return operation


async def update_operation(
    db: AsyncSession,
    operation: LearningOperation,
    *,
    status: str,
    error: dict[str, object] | None = None,
    learning_unit_id: UUID | None = None,
    scene_id: UUID | None = None,
    scene_version: int | None = None,
) -> None:
    operation.status = status
    operation.error = error
    if learning_unit_id is not None:
        operation.learning_unit_id = learning_unit_id
    if scene_id is not None:
        operation.scene_id = scene_id
    if scene_version is not None:
        operation.published_scene_version = scene_version
    await db.commit()


def operation_payload(operation: LearningOperation) -> dict[str, object]:
    return {
        "id": str(operation.id),
        "status": operation.status,
        "attempt": operation.attempt,
        "learning_unit_id": str(operation.learning_unit_id) if operation.learning_unit_id else None,
        "published_scene_version": operation.published_scene_version,
        "error": operation.error,
        "created_at": operation.created_at.isoformat(),
        "updated_at": operation.updated_at.isoformat(),
    }
