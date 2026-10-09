"""Short PG transactions for bounded model preparation; no provider send under row locks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.animation_dsl_review import digest
from app.models.animation import AnimationJob  # noqa: F401 (register target FK metadata)
from app.models.animation_generation import AnimationPreparation
from app.models.auth import GuestSessionRecord
from app.services.animation_dsl_candidates import build_dsl_reference
from app.services.animation_intent import VideoIntent
from app.services.animation_jobs import AnimationIdempotencyConflict, AnimationTargetUnavailable
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_owner_lock import lock_learning_owner

_ACTIVE = frozenset({"reserved", "generating", "reviewing", "compiled"})
_STAGES = ("reserved", "generating", "reviewing", "compiled")


class AnimationPreparationLimit(ValueError):
    code = "ANIMATION_PREPARATION_LIMIT"


@dataclass(frozen=True)
class PreparationReservation:
    operation: AnimationPreparation
    created: bool


async def _now(db: AsyncSession) -> datetime:
    now = await db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    return now


async def _session(
    db: AsyncSession, owner: UUID, session_hash: str, now: datetime
) -> GuestSessionRecord:
    row = await db.get(GuestSessionRecord, session_hash, populate_existing=True)
    if row is None or row.user_id != owner or row.expires_at <= now:
        raise AnimationTargetUnavailable()
    return row


def _expire(operation: AnimationPreparation, now: datetime) -> None:
    if operation.stage in _ACTIVE and operation.deadline <= now:
        operation.stage, operation.error_code = "failed", "ANIMATION_PREPARATION_EXPIRED"


async def reserve_preparation(
    db: AsyncSession,
    graph: KnowledgeGraphRepository,
    *,
    owner: UUID,
    session_hash: str,
    unit_id: UUID,
    scene_id: UUID,
    scene_version: int,
    intent: VideoIntent,
    idempotency_key: str,
    allow_template_fallback: bool = False,
    operation_id: UUID | None = None,
) -> PreparationReservation:
    """Commits reservation only. Replays cannot receive a fresh holder token or extend expiry."""
    if (
        not re.fullmatch(r"[0-9a-f]{64}", session_hash)
        or not 16 <= len(idempotency_key) <= 128
        or type(allow_template_fallback) is not bool
        or operation_id is not None
        and operation_id.version != 4
    ):
        raise ValueError("Invalid preparation identity")
    payload = intent.payload()
    request = digest(
        {
            "unit": str(unit_id),
            "scene": str(scene_id),
            "version": scene_version,
            "intent": payload,
            "allow_template_fallback": allow_template_fallback,
        }
    )
    try:
        await lock_learning_owner(db, owner)
        now = await _now(db)
        session = await _session(db, owner, session_hash, now)
        existing = await db.scalar(
            select(AnimationPreparation)
            .where(
                AnimationPreparation.user_id == owner,
                AnimationPreparation.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.request_digest != request:
                raise AnimationIdempotencyConflict()
            if existing.originating_session_hash != session_hash:
                raise AnimationTargetUnavailable()
            _expire(existing, now)
            await db.commit()
            return PreparationReservation(existing, False)
        if (
            operation_id is not None
            and await db.get(AnimationPreparation, operation_id) is not None
        ):
            raise AnimationTargetUnavailable()
        # Serialize concurrent reservation/count checks on owner; lazily retire expired receipts.
        active = (
            await db.scalars(
                select(AnimationPreparation)
                .where(
                    AnimationPreparation.user_id == owner,
                    AnimationPreparation.stage.in_(_ACTIVE),
                )
                .with_for_update()
            )
        ).all()
        for row in active:
            _expire(row, now)
        if sum(row.stage in _ACTIVE for row in active) >= 2:
            raise AnimationPreparationLimit()
        reference = await build_dsl_reference(
            db,
            graph,
            owner=owner,
            unit_id=unit_id,
            scene_id=scene_id,
            version=scene_version,
            lock=True,
        )
        if reference.knowledge_point_id != intent.knowledge_point_id:
            raise AnimationTargetUnavailable()
        operation = AnimationPreparation(
            id=operation_id or uuid4(),
            user_id=owner,
            learning_unit_id=unit_id,
            scene_id=scene_id,
            scene_version=scene_version,
            idempotency_key=idempotency_key,
            request_digest=request,
            intent=payload,
            reference_sha256=reference.sha256,
            originating_session_hash=session_hash,
            originating_session_expires_at=session.expires_at,
            execution_token=uuid4(),
            allow_template_fallback=allow_template_fallback,
            stage="reserved",
            created_at=now,
            deadline=min(now + timedelta(seconds=180), session.expires_at),
        )
        db.add(operation)
        await db.commit()
        return PreparationReservation(operation, True)
    except Exception:
        await db.rollback()
        raise


async def owned_preparation(
    db: AsyncSession,
    *,
    owner: UUID,
    session_hash: str,
    operation_id: UUID,
    lock: bool = False,
) -> AnimationPreparation:
    query = (
        select(AnimationPreparation)
        .where(
            AnimationPreparation.user_id == owner,
            AnimationPreparation.id == operation_id,
            AnimationPreparation.originating_session_hash == session_hash,
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    operation = await db.scalar(query)
    if operation is None:
        raise AnimationTargetUnavailable()
    now = await _now(db)
    await _session(db, owner, session_hash, now)
    if operation.stage in _ACTIVE and operation.deadline <= now:
        # Snapshot expiry is a CAS under the same row lock used by handoff/cancel.
        if not lock:
            operation = await db.scalar(query.with_for_update())
            if operation is None:
                raise AnimationTargetUnavailable()
        _expire(operation, now)
    return operation


async def advance_preparation(
    db: AsyncSession,
    graph: KnowledgeGraphRepository,
    *,
    owner: UUID,
    session_hash: str,
    operation_id: UUID,
    execution_token: UUID,
    stage: str,
) -> bool:
    """Original holder CAS and current target/session validation before each model phase."""
    if stage not in _STAGES:
        raise ValueError("Invalid preparation stage")
    try:
        row = await owned_preparation(
            db,
            owner=owner,
            session_hash=session_hash,
            operation_id=operation_id,
            lock=True,
        )
        if row.execution_token != execution_token or row.stage not in _ACTIVE:
            await db.commit()
            return False
        if row.stage == "compiled" and stage != "compiled":
            raise ValueError("Compiled preparation cannot send")
        if stage == "reserved" and row.stage != "reserved":
            raise ValueError("Preparation cannot regress")
        if stage == "generating":
            if row.generation_attempts >= 3 or row.generation_attempts != row.review_attempts:
                return False
            row.generation_attempts += 1
        elif stage == "reviewing":
            if row.review_attempts >= row.generation_attempts:
                return False
            row.review_attempts += 1
        # Autoflush must persist the new phase and its attempt count as one transition.
        row.stage = stage
        reference = await build_dsl_reference(
            db,
            graph,
            owner=owner,
            unit_id=row.learning_unit_id,
            scene_id=row.scene_id,
            version=row.scene_version,
            lock=True,
        )
        if reference.sha256 != row.reference_sha256:
            row.stage, row.error_code = "failed", "ANIMATION_TARGET_UNAVAILABLE"
            await db.commit()
            return False
        row.stage = stage
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        raise


async def cancel_preparation(
    db: AsyncSession,
    *,
    owner: UUID,
    session_hash: str,
    operation_id: UUID,
    idempotency_key: str | None = None,
    execution_token: UUID | None = None,
) -> AnimationPreparation:
    """Cancel by owner request or original POST disconnect; observers have no holder token."""
    if idempotency_key is None and execution_token is None:
        raise ValueError("Cancellation authorization required")
    if idempotency_key is not None and not 16 <= len(idempotency_key) <= 128:
        raise ValueError("Invalid cancel key")
    try:
        row = await owned_preparation(
            db,
            owner=owner,
            session_hash=session_hash,
            operation_id=operation_id,
            lock=True,
        )
        if execution_token is not None and row.execution_token != execution_token:
            raise AnimationTargetUnavailable()
        if row.cancel_idempotency_key not in (None, idempotency_key):
            raise AnimationIdempotencyConflict()
        if row.stage in _ACTIVE:
            row.stage = "cancelled"
            row.cancel_idempotency_key = idempotency_key
        await db.commit()
        return row  # Handoff remains immutable; caller must cancel the returned render Job instead.
    except Exception:
        await db.rollback()
        raise


def preparation_payload(row: AnimationPreparation) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(row.id),
        "stage": row.stage,
        "deadline": row.deadline.isoformat(),
    }
    if row.job_id is not None:
        payload["job_id"] = str(row.job_id)
    if row.error_code is not None:
        payload["error_code"] = row.error_code
    if row.source_kind is not None:
        payload["source"] = row.source_kind
    return payload


async def fail_preparation(
    db: AsyncSession,
    *,
    owner: UUID,
    operation_id: UUID,
    execution_token: UUID,
    code: str,
) -> bool:
    """Holder-only fixed-code failure cleanup also works after the original session expires."""
    allowed = {
        "ANIMATION_PREPARATION_EXPIRED",
        "ANIMATION_TARGET_UNAVAILABLE",
        "ANIMATION_UNAVAILABLE",
        "DSL_GENERATION_UNAVAILABLE",
        "DSL_REVIEW_UNAVAILABLE",
        "DSL_COMPILE_REJECTED",
    }
    if code not in allowed:
        raise ValueError("Invalid preparation failure code")
    try:
        row = await db.scalar(
            select(AnimationPreparation)
            .where(
                AnimationPreparation.id == operation_id,
                AnimationPreparation.user_id == owner,
                AnimationPreparation.execution_token == execution_token,
            )
            .with_for_update()
        )
        if row is None or row.stage not in _ACTIVE:
            await db.rollback()
            return False
        _expire(row, await _now(db))
        if row.stage in _ACTIVE:
            row.stage, row.error_code = "failed", code
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        raise
