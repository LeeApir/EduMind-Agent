"""Authenticated, owner-scoped published resource reads."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.models.learning import GeneratedResource
from app.services.owned_learning import (
    published_resource,
    published_scenes,
    visible_unit,
)

router = APIRouter(tags=["Learning"])


def not_found() -> AuthFailure:
    """Use one response for absent, foreign, and unpublished data."""
    return AuthFailure(404, "NOT_FOUND", "Resource not found.")


def resource_payload(resource: GeneratedResource) -> dict[str, object]:
    return {
        "id": str(resource.id),
        "type": resource.resource_type,
        "version": resource.version,
        "content": resource.content,
        "review_status": resource.review_status,
    }


@router.get("/api/learning-units/{unit_id}")
async def get_learning_unit(
    unit_id: UUID,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        unit = await visible_unit(db, current.user.id, unit_id)
        if unit is None:
            raise not_found()
        pairs = await published_scenes(db, current.user.id, unit_id)
    scenes: dict[str, dict[str, object]] = {}
    for scene, resource in pairs:
        scene_key = str(scene.id)
        if scene_key not in scenes:
            scenes[scene_key] = {
                "id": scene_key,
                "version": scene.version,
                "review_status": scene.review_status,
                "resources": [],
            }
        resources = scenes[scene_key]["resources"]
        assert isinstance(resources, list)
        resources.append(resource_payload(resource))
    return {"id": str(unit.id), "status": unit.status, "scenes": list(scenes.values())}


@router.get("/api/resource/{resource_id}")
@router.get("/api/resources/{resource_id}", include_in_schema=False)
async def get_published_resource(
    resource_id: UUID,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        resource = await published_resource(db, current.user.id, resource_id)
    if resource is None:
        raise not_found()
    return resource_payload(resource)
