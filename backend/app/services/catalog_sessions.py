"""Atomic fixed-node enrollment, with no model or free-text goal parsing."""

from copy import deepcopy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.profile_events import PROFILE_MERGE_RULE_VERSION
from app.models.catalog import CatalogRelease
from app.models.learning import (
    GeneratedResource,
    LearningOperation,
    LearningScene,
    LearningUnit,
    StudentProfile,
    utc_now,
)
from app.services.catalog_package import CatalogError, content_digest
from app.services.catalog_publication import release_package
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.learning_operations import IdempotencyConflict, request_digest
from app.services.learning_owner_lock import lock_learning_owner
from app.services.owned_learning import latest_profile, visible_unit
from app.services.path_versions import plan_or_replan_path
from app.services.profile_updates import snapshot_profile


async def catalog_listing(db: AsyncSession) -> dict[str, object]:
    graph = default_knowledge_graph_repository()
    releases = (await db.scalars(select(CatalogRelease).where(
        CatalogRelease.status == "approved").order_by(CatalogRelease.approved_at.desc(),
                                                     CatalogRelease.id))).all()
    entries: list[dict[str, object]] = []
    for release in releases:
        try:
            package = release_package(release)
        except (CatalogError, ValueError, TypeError, KeyError):
            continue
        entries.append({"id": str(release.id), "package_id": release.package_id,
                        "version": release.version, "digest": package.digest,
                        "nodes": [{"id": node.id, "name": node.name,
                                   "description": node.description,
                                   "prerequisites": list(node.prerequisites)}
                                  for node in graph.all_nodes()]})
    return {"status": "ready" if entries else "not_ready", "releases": entries}


async def create_catalog_session(
    db: AsyncSession, *, owner_id: UUID, release_id: UUID, node_id: str,
    idempotency_key: str,
) -> tuple[dict[str, object], bool]:
    """One transaction includes operation, profile, path and three reviewed resources."""
    await lock_learning_owner(db, owner_id)
    goal = f"catalog:{release_id}:{node_id}"
    digest = request_digest(goal=goal, preferred_language="C")
    previous = await db.scalar(select(LearningOperation).where(
        LearningOperation.user_id == owner_id,
        LearningOperation.idempotency_key == idempotency_key))
    if previous is not None:
        if previous.request_digest != digest:
            raise IdempotencyConflict("Idempotency key was reused for another request.")
        if previous.learning_unit_id is None or await visible_unit(
                db, owner_id, previous.learning_unit_id) is None:
            raise CatalogError("CATALOG_NOT_READY")
        return {"learning_unit_id": str(previous.learning_unit_id),
                "scene_id": str(previous.scene_id), "scene_version": 1,
                "release_id": str(release_id), "node_id": node_id}, False
    # Lock serializes enrollment with withdrawal; never publish from a stale approval.
    release = await db.get(CatalogRelease, release_id, with_for_update=True)
    if release is None:
        raise CatalogError("CATALOG_NOT_READY")
    package = release_package(release)
    graph = default_knowledge_graph_repository()
    node = graph.get_node(node_id)
    if node is None or node_id not in package.nodes:
        raise CatalogError("CATALOG_NODE_NOT_FOUND")
    profile = await latest_profile(db, owner_id)
    if profile is None:
        profile = StudentProfile(user_id=owner_id, version=1,
            merge_rule_version=PROFILE_MERGE_RULE_VERSION,
            initial_query="学习课程目录", evidence={})
        db.add(profile)
        await db.flush()
    path, _ = await plan_or_replan_path(db, owner_id=owner_id,
        target_node_id=node_id, graph=graph, trigger_reason="initial_plan", commit=False)
    unit = LearningUnit(user_id=owner_id, catalog_release_id=release.id,
        knowledge_point_id=node_id, title=node.name, status="ready",
        learning_objectives={"items": list(node.learning_objectives)},
        profile_snapshot=snapshot_profile(profile),
        outline={"path_snapshot": {"target_node_id": node_id, "version": path.version},
                 "origin_type": "curated", "release_digest": package.digest},
        review_summary={"kind": "human_approval", "release_id": str(release.id)})
    db.add(unit)
    await db.flush()
    scene = LearningScene(learning_unit_id=unit.id, scene_key="intro", scene_order=1,
        scene_type="catalog", generation_status="complete", review_status="passed",
        input_snapshot={"release_id": str(release.id), "node_id": node_id})
    db.add(scene)
    await db.flush()
    for kind, content in package.nodes[node_id].items():
        db.add(GeneratedResource(user_id=owner_id, learning_unit_id=unit.id, scene_id=scene.id,
            knowledge_point_id=node_id, resource_type=kind, content=deepcopy(content),
            origin_type="curated", catalog_release_id=release.id,
            catalog_content_digest=content_digest(content), review_status="passed",
            published_at=utc_now(), version=1,
            generation_metadata={"content_schema_version": "catalog-content-v1"}))
    db.add(LearningOperation(user_id=owner_id, idempotency_key=idempotency_key,
        request_digest=digest, goal=goal, preferred_language="C", status="published",
        learning_unit_id=unit.id, scene_id=scene.id, published_scene_version=1))
    await db.commit()
    return {"learning_unit_id": str(unit.id), "scene_id": str(scene.id), "scene_version": 1,
            "release_id": str(release.id), "node_id": node_id}, True
