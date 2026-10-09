"""Current course authority is separate from immutable path/mastery snapshots."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.product_mode import catalog_only
from app.models.catalog import CatalogRelease
from app.models.learning import LearningUnit
from app.services.catalog_publication import release_package
from app.services.owned_learning import published_scenes


async def path_learning_availability(
    db: AsyncSession, *, owner_id: UUID, node_ids: Iterable[str]
) -> list[dict[str, object]]:
    """Revalidate actual signed releases or complete owner-reviewed units at read time."""
    nodes = sorted(set(node_ids))
    available: dict[str, dict[str, object]] = {}
    releases = (
        await db.scalars(
            select(CatalogRelease)
            .where(CatalogRelease.status == "approved")
            .order_by(CatalogRelease.approved_at.desc(), CatalogRelease.id)
        )
    ).all()
    for release in releases:
        # Integrity errors propagate, rather than masquerading as a missing course.
        package = release_package(release)
        for node in nodes:
            if node in package.nodes and node not in available:
                available[node] = {
                    "node_id": node,
                    "status": "available",
                    "reason": "approved_catalog",
                    "catalog_release_id": str(release.id),
                    "learning_unit_id": None,
                }
    if not catalog_only():
        units = (
            await db.scalars(
                select(LearningUnit)
                .where(
                    LearningUnit.user_id == owner_id,
                    LearningUnit.status == "ready",
                    LearningUnit.knowledge_point_id.in_(nodes),
                )
                .order_by(LearningUnit.created_at.desc(), LearningUnit.id)
            )
        ).all()
        for unit in units:
            unit_node = unit.knowledge_point_id
            if unit_node is None or unit_node in available:
                continue
            resources = await published_scenes(db, owner_id, unit.id)
            if {
                resource.resource_type
                for _, resource in resources
                if resource.knowledge_point_id == unit_node
            } >= {
                "explanation",
                "code",
                "exercise",
            }:
                available[unit_node] = {
                    "node_id": unit_node,
                    "status": "available",
                    "reason": "reviewed_owner_unit",
                    "catalog_release_id": None,
                    "learning_unit_id": str(unit.id),
                }
    return [
        available.get(
            node,
            {
                "node_id": node,
                "status": "unavailable",
                "reason": "no_reviewed_course",
                "catalog_release_id": None,
                "learning_unit_id": None,
            },
        )
        for node in nodes
    ]
