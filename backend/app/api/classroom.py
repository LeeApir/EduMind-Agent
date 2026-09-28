"""Authenticated classroom snapshot, creation, and mode-switching API."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.services.classroom import (
    ClassroomNotFound,
    ClassroomVersionConflict,
    InvalidModeCombination,
    classroom_payload,
    create_classroom,
    owned_classroom,
    set_classroom_mode,
)
from app.services.learning_operations import IdempotencyConflict

router = APIRouter(tags=["Classroom"])


class ModeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["focus", "interactive"]
    enabled_roles: list[Literal["beginner", "advanced"]]


def _not_found() -> AuthFailure:
    return AuthFailure(404, "NOT_FOUND", "Classroom not found.")


def _conflict(code: str, message: str) -> AuthFailure:
    return AuthFailure(409, code, message)


@router.get("/api/learning-units/{unit_id}/classroom")
async def get_classroom(
    unit_id: UUID, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        session = await owned_classroom(db, owner_id=current.user.id, unit_id=unit_id)
    if session is None:
        raise _not_found()
    response.headers["Cache-Control"] = "no-store"
    return classroom_payload(session)


@router.post("/api/learning-units/{unit_id}/classroom")
async def create_classroom_endpoint(
    unit_id: UUID, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        try:
            session, created = await create_classroom(
                db, owner_id=current.user.id, unit_id=unit_id, idempotency_key=idempotency_key
            )
        except IdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
        except ClassroomNotFound:
            raise _not_found() from None
    response.headers["Cache-Control"] = "no-store"
    response.status_code = 201 if created else 200
    return classroom_payload(session)


@router.patch("/api/learning-units/{unit_id}/classroom/mode")
async def set_classroom_mode_endpoint(
    unit_id: UUID, payload: ModeChange, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    if_match_revision: int = Header(ge=1, alias="If-Match-Classroom-Revision"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        try:
            session, _ = await set_classroom_mode(
                db,
                owner_id=current.user.id,
                unit_id=unit_id,
                idempotency_key=idempotency_key,
                mode=payload.mode,
                enabled_roles=list(payload.enabled_roles),
                expected_revision=if_match_revision,
            )
        except IdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
        except ClassroomVersionConflict as error:
            raise _conflict(
                "CLASSROOM_VERSION_CONFLICT",
                f"Classroom revision is now {error.current_revision}.",
            ) from None
        except ClassroomNotFound:
            raise _not_found() from None
        except InvalidModeCombination:
            raise AuthFailure(
                422, "VALIDATION_ERROR", "Focus mode enables no companion roles."
            ) from None
    response.headers["Cache-Control"] = "no-store"
    return classroom_payload(session)
