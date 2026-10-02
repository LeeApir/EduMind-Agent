"""Authenticated fixed-course catalog reads and enrollment."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.services.catalog_demo import control_preset_demo, preset_demo
from app.services.catalog_package import CatalogError
from app.services.catalog_sessions import catalog_listing, create_catalog_session
from app.services.classroom import (
    ClassroomNotFound,
    ClassroomReplayUnavailable,
    ClassroomVersionConflict,
)
from app.services.learning_operations import IdempotencyConflict

router = APIRouter(tags=["Catalog"])


class CatalogSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    release_id: UUID
    node_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")


@router.get("/api/catalog")
async def get_catalog(
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        return await catalog_listing(db)


@router.post("/api/catalog/sessions")
async def start_catalog_session(
    payload: CatalogSessionRequest, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        try:
            receipt, created = await create_catalog_session(db, owner_id=current.user.id,
                release_id=payload.release_id, node_id=payload.node_id,
                idempotency_key=idempotency_key)
        except IdempotencyConflict:
            raise AuthFailure(409, "IDEMPOTENCY_CONFLICT", "Request key already used.") from None
        except CatalogError:
            raise AuthFailure(409, "CATALOG_NOT_READY", "Course is unavailable.") from None
    response.status_code = 201 if created else 200
    return receipt


class CatalogDemoControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["begin", "exit"]
    return_resource_type: Literal["explanation", "code", "exercise", "animation"] = "explanation"


@router.get("/api/catalog/learning-units/{unit_id}/demo")
async def get_preset_demo(
    unit_id: UUID, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        try:
            return await preset_demo(db, owner_id=current.user.id, unit_id=unit_id)
        except (ClassroomNotFound, CatalogError):
            raise AuthFailure(404, "NOT_FOUND", "Demonstration unavailable.") from None


@router.post("/api/catalog/learning-units/{unit_id}/demo")
async def change_preset_demo(
    unit_id: UUID, payload: CatalogDemoControl, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    revision: int = Header(ge=1, alias="If-Match-Classroom-Revision"),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        try:
            receipt, _ = await control_preset_demo(db, owner_id=current.user.id, unit_id=unit_id,
                action=payload.action, return_resource_type=payload.return_resource_type,
                idempotency_key=idempotency_key, expected_revision=revision)
        except ClassroomNotFound:
            raise AuthFailure(404, "NOT_FOUND", "Demonstration unavailable.") from None
        except IdempotencyConflict:
            raise AuthFailure(409, "IDEMPOTENCY_CONFLICT", "Request key already used.") from None
        except ClassroomVersionConflict:
            raise AuthFailure(409, "CLASSROOM_VERSION_CONFLICT",
                              "Refresh classroom state.") from None
        except (CatalogError, ClassroomReplayUnavailable):
            raise AuthFailure(409, "CATALOG_DEMO_CONFLICT",
                              "Demonstration state conflicts.") from None
    return receipt
