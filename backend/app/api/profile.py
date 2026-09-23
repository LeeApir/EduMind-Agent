"""Authenticated, owner-scoped profile reads, history, corrections, and events."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.profile_events import ProfileEventSchemaError
from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.models.learning import StudentProfile
from app.services.learning_operations import IdempotencyConflict
from app.services.owned_learning import latest_profile
from app.services.profile_updates import (
    ProfileVersionConflict,
    correct_profile,
    record_profile_event,
)

router = APIRouter(tags=["Learning"])


class ProfileCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    professional_background: dict[str, object] | None = None
    learning_goals: dict[str, object] | None = None
    error_preferences: list[object] | None = None
    engineering_preference: dict[str, object] | None = None


class ProfileEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    knowledge_node_id: str
    learning_unit_id: str | None = None
    scene_id: str | None = None
    action: str | None = None


def not_found() -> AuthFailure:
    """Use one response for absent and foreign profile data."""
    return AuthFailure(404, "NOT_FOUND", "Resource not found.")


def profile_payload(profile: StudentProfile) -> dict[str, object]:
    return {
        "id": str(profile.id),
        "version": profile.version,
        "initial_query": profile.initial_query,
        "professional_background": profile.professional_background,
        "knowledge_base": profile.knowledge_base,
        "cognitive_style": profile.cognitive_style,
        "learning_goals": profile.learning_goals,
        "error_preferences": profile.error_preferences,
        "engineering_preference": profile.engineering_preference,
        "extended_dimensions": profile.extended_dimensions,
        "evidence": profile.evidence,
        "updated_at": profile.updated_at.isoformat(),
    }


@router.get("/api/profile/me")
async def get_my_profile(
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        profile = await latest_profile(db, current.user.id)
    if profile is None:
        raise not_found()
    return profile_payload(profile)


@router.get("/api/profile/me/history")
async def get_my_profile_history(
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    limit: int = Query(20, ge=1, le=50),
    before_version: int | None = Query(None, ge=1),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        query = select(StudentProfile).where(StudentProfile.user_id == current.user.id)
        if before_version is not None:
            query = query.where(StudentProfile.version < before_version)
        rows = (
            await db.scalars(query.order_by(StudentProfile.version.desc()).limit(limit + 1))
        ).all()
    next_before_version: int | None = None
    if len(rows) > limit:
        rows = list(rows[:limit])
        next_before_version = rows[-1].version
    return {
        "items": [profile_payload(profile) for profile in rows],
        "next_before_version": next_before_version,
    }


@router.patch("/api/profile/me")
async def correct_my_profile(
    payload: ProfileCorrectionRequest,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    if_match_profile_version: int = Header(ge=1, alias="If-Match-Profile-Version"),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    corrections = payload.model_dump(exclude_none=True)
    if not corrections:
        raise AuthFailure(422, "VALIDATION_ERROR", "At least one editable field is required.")
    async with session_factory() as db:
        try:
            profile, _ = await correct_profile(
                db,
                owner_id=current.user.id,
                idempotency_key=idempotency_key,
                corrections=corrections,
                expected_version=if_match_profile_version,
                observed_at=datetime.now(timezone.utc).isoformat(),
            )
        except IdempotencyConflict:
            raise AuthFailure(
                409, "IDEMPOTENCY_CONFLICT", "Idempotency key conflicts."
            ) from None
        except ProfileVersionConflict:
            raise AuthFailure(
                409, "PROFILE_VERSION_CONFLICT", "Profile version no longer matches."
            ) from None
    return profile_payload(profile)


@router.post("/api/profile/events", status_code=202)
async def record_profile_event_endpoint(
    payload: ProfileEventRequest,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        try:
            record, _ = await record_profile_event(
                db,
                owner_id=current.user.id,
                idempotency_key=idempotency_key,
                event=payload.model_dump(exclude_none=True),
            )
        except ProfileEventSchemaError:
            raise AuthFailure(
                422, "VALIDATION_ERROR", "Profile event did not satisfy the schema."
            ) from None
        except IdempotencyConflict:
            raise AuthFailure(
                409, "IDEMPOTENCY_CONFLICT", "Idempotency key conflicts."
            ) from None
    return {
        "evidence_id": str(record.id),
        "event_type": record.event_type,
        "profile_update_status": "queued",
    }
