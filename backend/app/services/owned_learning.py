"""Owner-scoped reads of persisted learning data."""

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import GeneratedResource, LearningScene, LearningUnit, StudentProfile
from app.services.catalog_publication import approved_release, resource_provenance_valid


async def latest_profile(db: AsyncSession, owner_id: UUID) -> StudentProfile | None:
    """Return only the current user's latest profile snapshot."""
    return cast(
        StudentProfile | None,
        await db.scalar(
            select(StudentProfile)
            .where(StudentProfile.user_id == owner_id)
            .order_by(StudentProfile.version.desc())
            .limit(1)
        ),
    )


async def visible_unit(db: AsyncSession, owner_id: UUID, unit_id: UUID) -> LearningUnit | None:
    """Hide internal or foreign units from student-facing reads."""
    unit = cast(
        LearningUnit | None,
        await db.scalar(
            select(LearningUnit).where(
                LearningUnit.id == unit_id,
                LearningUnit.user_id == owner_id,
                LearningUnit.status == "ready",
            )
        ),
    )

    if unit is not None and unit.catalog_release_id is not None:
        if await approved_release(db, unit.catalog_release_id) is None:
            return None
    return unit


async def published_resource(
    db: AsyncSession, owner_id: UUID, resource_id: UUID
) -> GeneratedResource | None:
    """Require both resource and parent unit ownership plus review publication."""
    resource = cast(
        GeneratedResource | None,
        await db.scalar(
            select(GeneratedResource)
            .join(LearningUnit, LearningUnit.id == GeneratedResource.learning_unit_id)
            .join(LearningScene, LearningScene.id == GeneratedResource.scene_id)
            .where(
                GeneratedResource.id == resource_id,
                GeneratedResource.user_id == owner_id,
                LearningUnit.user_id == owner_id,
                LearningUnit.status == "ready",
                LearningScene.learning_unit_id == LearningUnit.id,
                LearningScene.review_status == "passed",
                GeneratedResource.review_status == "passed",
                GeneratedResource.published_at.is_not(None),
            )
        ),
    )

    if resource is not None:
        unit = await db.get(LearningUnit, resource.learning_unit_id)
        if unit is None or not await resource_provenance_valid(db, resource, unit):
            return None
    return resource


async def published_scenes(
    db: AsyncSession, owner_id: UUID, unit_id: UUID
) -> list[tuple[LearningScene, GeneratedResource]]:
    """Only return reviewed scene-resource pairs owned by the current user."""
    result = await db.execute(
        select(LearningScene, GeneratedResource)
        .join(GeneratedResource, GeneratedResource.scene_id == LearningScene.id)
        .join(LearningUnit, LearningUnit.id == LearningScene.learning_unit_id)
        .where(
            LearningUnit.id == unit_id,
            LearningUnit.user_id == owner_id,
            LearningUnit.status == "ready",
            GeneratedResource.user_id == owner_id,
            GeneratedResource.learning_unit_id == unit_id,
            LearningScene.review_status == "passed",
            GeneratedResource.review_status == "passed",
            GeneratedResource.published_at.is_not(None),
        )
        .order_by(LearningScene.scene_order, LearningScene.version, GeneratedResource.version)
    )
    unit = await visible_unit(db, owner_id, unit_id)
    if unit is None:
        return []
    return [(scene, resource) for scene, resource in result.all()
            if await resource_provenance_valid(db, resource, unit)]
