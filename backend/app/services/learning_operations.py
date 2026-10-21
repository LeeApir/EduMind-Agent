"""Durable, owner-scoped lifecycle for SSE learning operations."""

import hashlib
import json
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningOperation


class IdempotencyConflict(ValueError):
    """A key may not be reused by its owner for a different request."""


@dataclass(frozen=True, slots=True)
class OperationReservation:
    operation: LearningOperation
    created: bool


def request_digest(
    *,
    goal: str,
    preferred_language: str,
    generation_protocol: str | None = None,
    teaching_mode: str | None = None,
) -> str:
    payload = {"goal": goal.strip(), "preferred_language": preferred_language}
    if generation_protocol is not None:
        payload["generation_protocol"] = generation_protocol
        if teaching_mode not in (None, "target", "recommended"):
            raise ValueError("Invalid teaching mode")
        payload["teaching_mode"] = teaching_mode or "target"
        payload["selection_version"] = "teaching-node-binding-v1"
    value = json.dumps(
        payload,
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
    generation_protocol: str | None = None,
    teaching_mode: str | None = None,
) -> OperationReservation:
    """Create one operation or return the same owner-bound, same-payload record."""
    digest = request_digest(
        goal=goal,
        preferred_language=preferred_language,
        generation_protocol=generation_protocol,
        teaching_mode=teaching_mode,
    )
    existing = await db.scalar(
        select(LearningOperation).where(
            LearningOperation.user_id == owner_id,
            LearningOperation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_digest != digest:
            old_payload = {"goal": goal.strip(), "preferred_language": preferred_language}
            if generation_protocol is not None:
                old_payload["generation_protocol"] = generation_protocol
            old_digest = hashlib.sha256(
                json.dumps(
                    old_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            if (
                generation_protocol == "shared-plan-v1"
                and teaching_mode is None
                and existing.request_digest == old_digest
            ):
                return OperationReservation(existing, False)
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
    from app.services.teaching_binding import public_teaching_context

    context = public_teaching_context(operation.teaching_context)
    return {
        "teaching_context": context,
        "binding_status": "bound" if context else "legacy_unverified",
        "id": str(operation.id),
        "status": operation.status,
        "attempt": operation.attempt,
        "phase": operation.phase,
        "publication_version": (operation.review_summary or {}).get("publication_version"),
        "review_summary": {
            k: v
            for k, v in operation.review_summary.items()
            if k in {"state", "approval_source", "reason_code", "updated_at"}
        }
        if operation.review_summary
        else None,
        "learning_unit_id": str(operation.learning_unit_id) if operation.learning_unit_id else None,
        "published_scene_version": operation.published_scene_version,
        "error": operation.error,
        "created_at": operation.created_at.isoformat(),
        "updated_at": operation.updated_at.isoformat(),
    }
