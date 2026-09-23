"""Durable, owner-scoped profile events and immutable profile versions."""

from collections.abc import Mapping
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.profile_events import event_digest, validate_profile_event
from app.agents.profile_schema import ProfileValue
from app.models.learning import ProfileEvent, StudentProfile
from app.services.learning_operations import IdempotencyConflict
from app.services.owned_learning import latest_profile


class ProfileVersionConflict(ValueError):
    """The optimistic version precondition no longer matches the latest snapshot."""


def _object_or_none(value: ProfileValue) -> dict[str, object] | None:
    if value is None:
        return None
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _list_or_none(value: ProfileValue) -> list[object] | None:
    if value is None:
        return None
    assert isinstance(value, list)
    return cast(list[object], value)


def _optional_str(value: ProfileValue) -> str | None:
    if value is None:
        return None
    assert isinstance(value, str)
    return value


async def record_profile_event(
    db: AsyncSession,
    *,
    owner_id: UUID,
    idempotency_key: str,
    event: Mapping[str, object],
) -> tuple[ProfileEvent, bool]:
    """Persist a validated behavior summary once, or return the owner's identical record."""
    validated = validate_profile_event(dict(event))
    digest = event_digest(validated)
    existing = await db.scalar(
        select(ProfileEvent).where(
            ProfileEvent.user_id == owner_id,
            ProfileEvent.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_digest != digest:
            raise IdempotencyConflict("Idempotency key was reused for another event.")
        return existing, False
    record = ProfileEvent(
        user_id=owner_id,
        idempotency_key=idempotency_key,
        request_digest=digest,
        event_type=cast(str, validated["event_type"]),
        knowledge_node_id=cast(str, validated["knowledge_node_id"]),
        learning_unit_id=cast(str | None, validated["learning_unit_id"]),
        scene_id=cast(str | None, validated["scene_id"]),
        action=cast(str | None, validated["action"]),
    )
    db.add(record)
    await db.commit()
    return record, True


async def persist_profile_version(
    db: AsyncSession,
    *,
    owner_id: UUID,
    profile: Mapping[str, ProfileValue],
) -> StudentProfile:
    """Insert the next immutable snapshot; a stale or concurrent writer fails loudly."""
    next_version = profile["profile_version"]
    if not isinstance(next_version, int) or isinstance(next_version, bool):
        raise ProfileVersionConflict("Profile version must be a positive integer.")
    latest = await latest_profile(db, owner_id)
    expected = 1 if latest is None else latest.version + 1
    if next_version != expected:
        raise ProfileVersionConflict("Profile version does not follow the latest snapshot.")

    persisted = StudentProfile(
        user_id=owner_id,
        version=next_version,
        initial_query=_optional_str(profile["initial_query"]),
        professional_background=_object_or_none(profile["professional_background"]),
        knowledge_base=_object_or_none(profile["knowledge_base"]),
        cognitive_style=_object_or_none(profile["cognitive_style"]),
        learning_goals=_object_or_none(profile["learning_goals"]),
        error_preferences=_list_or_none(profile["error_preferences"]),
        engineering_preference=_object_or_none(profile["engineering_preference"]),
        evidence=_object_or_none(profile["evidence"]),
    )
    db.add(persisted)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ProfileVersionConflict("Profile version was taken by a concurrent update.") from None
    return persisted
