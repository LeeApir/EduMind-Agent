"""Persist the first conservative profile for an authenticated anonymous owner."""

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.profile_agent import ProfileAgent
from app.agents.profile_schema import ProfileValue
from app.models.learning import StudentProfile
from app.services.owned_learning import latest_profile


@dataclass(frozen=True, slots=True)
class PersistedTransientProfile:
    """A newly flushed snapshot plus whether provider output had to be discarded."""

    profile: StudentProfile
    degraded: bool


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


async def create_transient_profile(
    db: AsyncSession,
    *,
    owner_id: UUID,
    initial_query: str,
    profile_agent: ProfileAgent,
) -> PersistedTransientProfile:
    """Create the next owner-scoped snapshot; the caller owns the transaction commit."""
    previous = await latest_profile(db, owner_id)
    version = 1 if previous is None else previous.version + 1
    extraction = await profile_agent.extract(initial_query, profile_version=version)
    profile = extraction.profile

    persisted = StudentProfile(
        user_id=owner_id,
        version=version,
        initial_query=cast(str, profile["initial_query"]),
        professional_background=_object_or_none(profile["professional_background"]),
        knowledge_base=_object_or_none(profile["knowledge_base"]),
        cognitive_style=_object_or_none(profile["cognitive_style"]),
        learning_goals=_object_or_none(profile["learning_goals"]),
        error_preferences=_list_or_none(profile["error_preferences"]),
        engineering_preference=_object_or_none(profile["engineering_preference"]),
        evidence=_object_or_none(profile["evidence"]),
    )
    db.add(persisted)
    await db.flush()
    return PersistedTransientProfile(profile=persisted, degraded=extraction.degraded)
