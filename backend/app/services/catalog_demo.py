"""Approved preset demonstration with durable owner-scoped return points."""

from copy import deepcopy
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import CatalogRelease
from app.models.classroom import ClassroomOperation
from app.models.learning import utc_now
from app.services.catalog_package import CatalogError
from app.services.catalog_publication import release_package
from app.services.classroom import (
    ClassroomNotFound,
    ClassroomReplayUnavailable,
    ClassroomVersionConflict,
    _find_operation,
    classroom_digest,
    classroom_payload,
    owned_classroom,
)
from app.services.learning_operations import IdempotencyConflict
from app.services.learning_owner_lock import lock_learning_owner
from app.services.owned_learning import visible_unit


async def preset_demo(db: AsyncSession, *, owner_id: UUID, unit_id: UUID) -> dict[str, object]:
    unit = await visible_unit(db, owner_id, unit_id)
    if unit is None or unit.catalog_release_id is None:
        raise ClassroomNotFound
    release = await db.get(CatalogRelease, unit.catalog_release_id)
    if release is None:
        raise ClassroomNotFound
    package = release_package(release)
    session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
    return {"preset": True, "origin_type": "curated", "release_id": str(release.id),
            "demo_digest": package.manifest["demo_digest"], "script": deepcopy(package.demo),
            "classroom": classroom_payload(session) if session else None}


async def control_preset_demo(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID, action: str,
    return_resource_type: str, idempotency_key: str, expected_revision: int,
) -> tuple[dict[str, object], bool]:
    await lock_learning_owner(db, owner_id)
    unit = await visible_unit(db, owner_id, unit_id)
    if unit is None or unit.catalog_release_id is None:
        raise ClassroomNotFound
    release = await db.get(CatalogRelease, unit.catalog_release_id,
                           with_for_update=True, populate_existing=True)
    if release is None:
        raise ClassroomNotFound
    package = release_package(release)
    if action not in {"begin", "exit"} or return_resource_type not in {
            "explanation", "code", "exercise", "animation"}:
        raise CatalogError("CATALOG_DEMO_INVALID")
    digest = classroom_digest({"kind": "catalog_demo", "unit_id": str(unit_id),
                               "action": action, "resource_type": return_resource_type})
    previous = await _find_operation(db, owner_id=owner_id, idempotency_key=idempotency_key)
    if previous is not None:
        if previous.kind != "control" or previous.request_digest != digest:
            raise IdempotencyConflict
        if previous.result_snapshot is None:
            raise ClassroomReplayUnavailable
        return previous.result_snapshot, False
    session = await owned_classroom(db, owner_id=owner_id, unit_id=unit_id)
    if session is None:
        raise ClassroomNotFound
    if session.revision != expected_revision:
        raise ClassroomVersionConflict(session.revision)
    if action == "begin":
        if session.detour is not None:
            raise CatalogError("CATALOG_DEMO_ACTIVE")
        session.detour = {"kind": "catalog_demo", "release_id": str(release.id),
            "demo_digest": package.manifest["demo_digest"], "return_point": {
                "scene_key": session.scene_key, "scene_version": session.scene_version,
                "scene_progress": session.scene_progress, "paused": session.paused,
                "resource_type": return_resource_type}}
        session.paused = True
    else:
        detour = session.detour
        if (not isinstance(detour, dict) or detour.get("kind") != "catalog_demo"
                or detour.get("release_id") != str(release.id)
                or detour.get("demo_digest") != package.manifest["demo_digest"]):
            raise CatalogError("CATALOG_DEMO_NOT_ACTIVE")
        point = detour.get("return_point")
        if not isinstance(point, dict):
            raise CatalogError("CATALOG_DEMO_INVALID")
        session.scene_key = str(point["scene_key"])
        session.scene_version = int(point["scene_version"])
        session.scene_progress = int(point["scene_progress"])
        session.paused = bool(point["paused"])
        return_resource_type = str(point["resource_type"])
        session.detour = None
    session.revision += 1
    session.generation_id = uuid4()
    session.updated_at = utc_now()
    receipt = {"classroom": classroom_payload(session), "preset": True,
               "action": action, "return_resource_type": return_resource_type}
    db.add(ClassroomOperation(user_id=owner_id, learning_unit_id=unit_id, kind="control",
        idempotency_key=idempotency_key, request_digest=digest, base_revision=expected_revision,
        generation_id=session.generation_id, result_snapshot=receipt, status="published"))
    await db.commit()
    return receipt, True
