"""Owner-scoped classroom reads, creation, and mode switching.

Every classroom write command carries an owner-scoped idempotency key and a
canonical request digest, matching ADR-0005 Decision B: an idempotency hit is
resolved before the ``If-Match`` revision check, and a mode/role change commits
a new revision and ``generation_id`` so late output from a prior generation can
never be published into the current session.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classroom import ClassroomOperation, ClassroomSession
from app.models.learning import GeneratedResource, LearningScene, LearningUnit, utc_now
from app.services.learning_operations import IdempotencyConflict
from app.services.learning_owner_lock import lock_learning_owner


class ClassroomNotFound(ValueError):
    """No current classroom exists for this owner and learning unit."""


class ClassroomVersionConflict(ValueError):
    """The optimistic revision precondition no longer matches the session."""

    def __init__(self, current_revision: int) -> None:
        self.current_revision = current_revision
        super().__init__(f"Classroom revision is now {current_revision}.")


class InvalidModeCombination(ValueError):
    """Focus mode enables no companion roles."""


class ClassroomReplayUnavailable(ValueError):
    """A pre-migration command has no recoverable immutable receipt."""


def classroom_digest(payload: Mapping[str, object]) -> str:
    """Canonical digest so an owner cannot reuse a key for another command."""
    value = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode()).hexdigest()


def _normalized_roles(enabled_roles: Sequence[str]) -> list[str]:
    """Deduplicate and sort roles so equal sets share one digest and value."""
    return sorted(dict.fromkeys(enabled_roles))


async def _find_operation(
    db: AsyncSession, *, owner_id: UUID, idempotency_key: str
) -> ClassroomOperation | None:
    return cast(
        ClassroomOperation | None,
        await db.scalar(
            select(ClassroomOperation).where(
                ClassroomOperation.user_id == owner_id,
                ClassroomOperation.idempotency_key == idempotency_key,
            )
        ),
    )


async def owned_classroom(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID
) -> ClassroomSession | None:
    """Return the owner's current classroom, if one has been created yet."""
    return cast(
        ClassroomSession | None,
        await db.scalar(
            select(ClassroomSession).where(
                ClassroomSession.user_id == owner_id,
                ClassroomSession.learning_unit_id == unit_id,
            )
        ),
    )


async def current_intro_scene(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID
) -> LearningScene | None:
    """The latest reviewed, generated intro scene of a ready owned unit."""
    return cast(
        LearningScene | None,
        await db.scalar(
            select(LearningScene)
            .join(LearningUnit, LearningUnit.id == LearningScene.learning_unit_id)
            .where(
                LearningUnit.id == unit_id,
                LearningUnit.user_id == owner_id,
                LearningUnit.status == "ready",
                LearningScene.scene_key == "intro",
                LearningScene.generation_status == "complete",
                LearningScene.review_status == "passed",
                select(GeneratedResource.id)
                .where(
                    GeneratedResource.scene_id == LearningScene.id,
                    GeneratedResource.user_id == owner_id,
                    GeneratedResource.learning_unit_id == unit_id,
                    GeneratedResource.review_status == "passed",
                    GeneratedResource.published_at.is_not(None),
                )
                .exists(),
            )
            .order_by(LearningScene.version.desc())
            .limit(1)
        ),
    )


def classroom_payload(session: ClassroomSession) -> dict[str, object]:
    """Render the public classroom snapshot from a persisted session."""
    payload: dict[str, object] = {
        "learning_unit_id": str(session.learning_unit_id),
        "revision": session.revision,
        "message_cursor": session.message_cursor,
        "scene_key": session.scene_key,
        "scene_version": session.scene_version,
        "scene_progress": session.scene_progress,
        "mode": session.mode,
        "enabled_roles": session.enabled_roles,
        "paused": session.paused,
    }
    if session.generation_id is not None:
        payload["generation_id"] = str(session.generation_id)
    if session.detour is not None:
        payload["detour"] = session.detour
    return payload


def _operation_receipt(operation: ClassroomOperation) -> dict[str, object]:
    if operation.result_snapshot is None:
        raise ClassroomReplayUnavailable("Original classroom receipt is unavailable.")
    return operation.result_snapshot


async def create_classroom(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID, idempotency_key: str
) -> tuple[dict[str, object], bool]:
    """Create the default focus classroom once, or replay the existing snapshot."""
    digest = classroom_digest({"kind": "create", "learning_unit_id": str(unit_id)})
    existing = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if existing is not None:
        if existing.request_digest != digest:
            raise IdempotencyConflict("Idempotency key was reused for another classroom.")
        return _operation_receipt(existing), False
    await lock_learning_owner(db, owner_id)
    existing = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if existing is not None:
        if existing.request_digest != digest:
            raise IdempotencyConflict("Idempotency key was reused for another classroom.")
        return _operation_receipt(existing), False
    session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
    created = session is None
    if session is None:
        intro = await current_intro_scene(db, owner_id=owner_id, unit_id=unit_id)
        if intro is None:
            raise ClassroomNotFound("No published intro scene for this learning unit.")
        session = ClassroomSession(
            user_id=owner_id,
            learning_unit_id=unit_id,
            scene_key="intro",
            scene_version=intro.version,
            scene_progress=0,
            mode="focus",
            revision=1,
            message_cursor=0,
            enabled_roles=[],
            paused=False,
        )
        db.add(session)
        await db.flush()
    receipt = classroom_payload(session)
    db.add(
        ClassroomOperation(
            user_id=owner_id,
            learning_unit_id=unit_id,
            kind="create",
            idempotency_key=idempotency_key,
            request_digest=digest,
            base_revision=session.revision,
            result_snapshot=receipt,
            status="published",
        )
    )
    await db.commit()
    return receipt, created


async def set_classroom_mode(
    db: AsyncSession,
    *,
    owner_id: UUID,
    unit_id: UUID,
    idempotency_key: str,
    mode: str,
    enabled_roles: Sequence[str],
    expected_revision: int,
) -> tuple[dict[str, object], bool]:
    """Switch focus/interactive mode and enabled roles idempotently with CAS."""
    roles = _normalized_roles(enabled_roles)
    if mode == "focus" and roles:
        raise InvalidModeCombination("Focus mode enables no companion roles.")
    digest = classroom_digest(
        {
            "kind": "mode",
            "learning_unit_id": str(unit_id),
            "mode": mode,
            "enabled_roles": roles,
        }
    )
    existing = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if existing is not None:
        if existing.request_digest != digest:
            raise IdempotencyConflict("Idempotency key was reused for another mode change.")
        return _operation_receipt(existing), False
    await lock_learning_owner(db, owner_id)
    existing = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if existing is not None:
        if existing.request_digest != digest:
            raise IdempotencyConflict("Idempotency key was reused for another mode change.")
        return _operation_receipt(existing), False
    session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
    if session is None:
        raise ClassroomNotFound("Classroom does not exist.")
    if session.revision != expected_revision:
        raise ClassroomVersionConflict(session.revision)
    new_generation = uuid4()
    session.revision = session.revision + 1
    session.mode = mode
    session.enabled_roles = cast(list[object], roles)
    session.generation_id = new_generation
    session.updated_at = utc_now()
    receipt = classroom_payload(session)
    db.add(
        ClassroomOperation(
            user_id=owner_id,
            learning_unit_id=unit_id,
            kind="mode",
            idempotency_key=idempotency_key,
            request_digest=digest,
            base_revision=expected_revision,
            generation_id=new_generation,
            result_snapshot=receipt,
            status="published",
        )
    )
    await db.commit()
    return receipt, True
