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
    content = resource.content
    if resource.resource_type == "exercise":
        items = content.get("items")
        content = {
            "items": [
                {"id": item.get("id"), "question": item.get("question")}
                for item in items
                if isinstance(item, dict)
            ]
            if isinstance(items, list)
            else []
        }
    return {
        "id": str(resource.id),
        "type": resource.resource_type,
        "version": resource.version,
        "content": content,
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
    current_versions: dict[str, int] = {}
    for scene, _ in pairs:
        current_versions[scene.scene_key] = max(
            current_versions.get(scene.scene_key, 0), scene.version
        )
    for scene, resource in pairs:
        scene_key = str(scene.id)
        if scene_key not in scenes:
            scenes[scene_key] = {
                "id": scene_key,
                "scene_key": scene.scene_key,
                "version": scene.version,
                "is_current": scene.version == current_versions[scene.scene_key],
                "review_status": scene.review_status,
                "resources": [],
            }
        resources = scenes[scene_key]["resources"]
        assert isinstance(resources, list)
        resources.append(resource_payload(resource))
    path_snapshot = (unit.outline or {}).get("path_snapshot")
    return {
        "id": str(unit.id),
        "status": unit.status,
        "scenes": list(scenes.values()),
        "knowledge_node_id": unit.knowledge_point_id,
        "path_target_node_id": path_snapshot.get("target_node_id")
        if isinstance(path_snapshot, dict)
        else None,
        "path_version": path_snapshot.get("version") if isinstance(path_snapshot, dict) else None,
    }


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
