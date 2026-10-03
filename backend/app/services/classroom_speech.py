"""Owner-scoped tiered classroom speech: reserve, context, commit, and read.

A speech request reserves one idempotent ``speech`` operation with the same
optimistic-revision CAS as a mode switch. The streamed tokens are temporary;
only a reviewed, still-current turn is committed to append-only messages with
a monotonic cursor. A mode switch that lands mid-stream advances ``generation_id``
and ``revision``, so a late commit is demoted to ``superseded`` and never writes
old role output into the current session.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classroom import (
    ClassroomMessage,
    ClassroomOperation,
    ClassroomSession,
)
from app.models.learning import GeneratedResource, LearningScene, LearningUnit, utc_now
from app.services.classroom import (
    ClassroomNotFound,
    ClassroomVersionConflict,
    _find_operation,
    classroom_digest,
    owned_classroom,
)
from app.services.learning_operations import IdempotencyConflict
from app.services.learning_owner_lock import lock_learning_owner
from app.services.owned_learning import latest_profile, visible_unit
from app.services.path_versions import current_path_version
from app.services.profile_updates import snapshot_profile


@dataclass(frozen=True, slots=True)
class SpeechReservation:
    operation: ClassroomOperation
    session: ClassroomSession
    created: bool


@dataclass(frozen=True, slots=True)
class SpeechMaterials:
    """Provider-ready, sanitized inputs for one orchestrated classroom turn."""

    node_id: str | None
    goal: str
    reviewed_resources: tuple[dict[str, object], ...]
    profile: dict[str, object] | None
    path: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class CommittedSpeech:
    """Whether the turn was committed, superseded, and each committed message."""

    published: bool
    superseded: bool
    messages: tuple[tuple[int, str, str], ...]  # (message_cursor, role, message_id)


async def reserve_classroom_speech(
    db: AsyncSession,
    *,
    owner_id: UUID,
    unit_id: UUID,
    idempotency_key: str,
    text: str,
    scene_version: int,
    expected_revision: int,
) -> SpeechReservation:
    """Reserve one idempotent speech operation with optimistic revision CAS."""
    digest = classroom_digest(
        {
            "kind": "speech",
            "learning_unit_id": str(unit_id),
            "text": text,
            "scene_version": scene_version,
        }
    )
    existing = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if existing is not None:
        if existing.request_digest != digest:
            raise IdempotencyConflict("Idempotency key was reused for another speech.")
        session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
        if session is None:
            raise ClassroomNotFound("Classroom does not exist.")
        return SpeechReservation(existing, session, False)
    await lock_learning_owner(db, owner_id)
    existing = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if existing is not None:
        if existing.request_digest != digest:
            raise IdempotencyConflict("Idempotency key was reused for another speech.")
        session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
        if session is None:
            raise ClassroomNotFound("Classroom does not exist.")
        return SpeechReservation(existing, session, False)
    session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
    if session is None:
        raise ClassroomNotFound("Classroom does not exist.")
    if session.revision != expected_revision:
        raise ClassroomVersionConflict(session.revision)
    operation = ClassroomOperation(
        user_id=owner_id,
        learning_unit_id=unit_id,
        kind="speech",
        idempotency_key=idempotency_key,
        request_digest=digest,
        base_revision=expected_revision,
        generation_id=session.generation_id,
        status="accepted",
    )
    db.add(operation)
    await db.commit()
    return SpeechReservation(operation, session, True)


async def reviewed_scene_resources(
    db: AsyncSession,
    *,
    owner_id: UUID,
    unit_id: UUID,
    scene_key: str,
    scene_version: int,
) -> list[GeneratedResource]:
    """Published, review-passed resources for the session's current scene."""
    result = await db.execute(
        select(GeneratedResource)
        .join(LearningScene, LearningScene.id == GeneratedResource.scene_id)
        .join(LearningUnit, LearningUnit.id == GeneratedResource.learning_unit_id)
        .where(
            LearningUnit.id == unit_id,
            LearningUnit.user_id == owner_id,
            GeneratedResource.user_id == owner_id,
            LearningScene.scene_key == scene_key,
            LearningScene.version == scene_version,
            GeneratedResource.review_status == "passed",
            GeneratedResource.published_at.is_not(None),
        )
    )
    return list(result.scalars().all())


async def speech_materials(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID, session: ClassroomSession
) -> SpeechMaterials:
    """Gather the minimal reviewed inputs for a classroom turn without a provider call."""
    unit = await visible_unit(db, owner_id, unit_id)
    if unit is None:
        raise ClassroomNotFound("Classroom does not exist.")
    resources = await reviewed_scene_resources(
        db,
        owner_id=owner_id,
        unit_id=unit_id,
        scene_key=session.scene_key,
        scene_version=session.scene_version,
    )
    reviewed: tuple[dict[str, object], ...] = tuple(
        {"resource_type": resource.resource_type, "content": resource.content}
        for resource in resources
        if isinstance(resource.content, dict)
    )
    node_id = unit.knowledge_point_id or next(
        (resource.knowledge_point_id for resource in resources if resource.knowledge_point_id),
        None,
    )
    goal = (unit.title or "").strip() or node_id or ""
    profile_snapshot = None
    profile = await latest_profile(db, owner_id)
    if profile is not None:
        profile_snapshot = snapshot_profile(profile)
    path: dict[str, object] | None = None
    if node_id is not None:
        version = await current_path_version(db, owner_id=owner_id, target_node_id=node_id)
        if version is not None:
            path = {
                "current_node_id": version.current_node_id,
                "next_node_id": version.next_node_id,
                "prerequisite_node_ids": version.prerequisite_node_ids,
                "reasons": version.reasons,
            }
    return SpeechMaterials(
        node_id=node_id,
        goal=goal,
        reviewed_resources=reviewed,
        profile=profile_snapshot,
        path=path,
    )


async def commit_classroom_speech(
    db: AsyncSession,
    *,
    owner_id: UUID,
    operation: ClassroomOperation,
    student_text: str,
    utterances: Sequence[tuple[str, str]],
) -> CommittedSpeech:
    """Commit a still-current turn, or demote it to superseded after a mode switch."""
    await lock_learning_owner(db, owner_id)
    session = await owned_classroom(db, owner_id=owner_id, unit_id=operation.learning_unit_id)
    if session is None:
        operation.status = "cancelled"
        await db.commit()
        return CommittedSpeech(False, True, ())
    if (
        session.revision != operation.base_revision
        or session.generation_id != operation.generation_id
    ):
        operation.status = "superseded"
        await db.commit()
        return CommittedSpeech(False, True, ())
    pending: list[tuple[int, str, ClassroomMessage]] = []
    cursor = session.message_cursor

    def add(role: str, text: str) -> None:
        nonlocal cursor
        cursor += 1
        message = ClassroomMessage(
            session_id=session.id,
            user_id=owner_id,
            message_cursor=cursor,
            role=role,
            session_revision=session.revision,
            scene_key=session.scene_key,
            scene_version=session.scene_version,
            text=text,
            visible=True,
        )
        db.add(message)
        pending.append((cursor, role, message))

    add("student", student_text)
    for role, text in utterances:
        add(role, text)
    await db.flush()
    committed = tuple((cur, role, str(message.id)) for cur, role, message in pending)
    session.message_cursor = cursor
    session.updated_at = utc_now()
    operation.status = "published"
    operation.updated_at = utc_now()
    await db.commit()
    return CommittedSpeech(True, False, committed)


async def owned_classroom_operation(
    db: AsyncSession, *, owner_id: UUID, operation_id: UUID
) -> ClassroomOperation | None:
    return cast(
        ClassroomOperation | None,
        await db.scalar(
            select(ClassroomOperation).where(
                ClassroomOperation.id == operation_id,
                ClassroomOperation.user_id == owner_id,
            )
        ),
    )


async def classroom_messages(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID, after: int
) -> tuple[ClassroomSession | None, list[ClassroomMessage]]:
    """Committed messages after a cursor, always replaying only durable text."""
    session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
    if session is None:
        return None, []
    result = await db.execute(
        select(ClassroomMessage)
        .where(
            ClassroomMessage.session_id == session.id,
            ClassroomMessage.message_cursor > after,
        )
        .order_by(ClassroomMessage.message_cursor)
    )
    return session, list(result.scalars().all())


def classroom_operation_payload(operation: ClassroomOperation) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(operation.id),
        "status": operation.status,
        "learning_unit_id": str(operation.learning_unit_id),
        "kind": operation.kind,
        "base_revision": operation.base_revision,
    }
    if operation.generation_id is not None:
        payload["generation_id"] = str(operation.generation_id)
    if operation.result_id is not None:
        payload["result_id"] = str(operation.result_id)
    if operation.error is not None:
        payload["error"] = operation.error
    return payload


def classroom_message_payload(message: ClassroomMessage) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(message.id),
        "cursor": message.message_cursor,
        "role": message.role,
        "scene_key": message.scene_key,
        "scene_version": message.scene_version,
    }
    if message.text is not None:
        payload["text"] = message.text
    if message.resource_id is not None:
        payload["resource_id"] = str(message.resource_id)
    return payload
