"""Persist reviewed resource versions without exposing rejected candidates."""

from datetime import datetime, timezone
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.learning_resource_schema import ResourceSchemaError, validate_learning_resource
from app.agents.review_agent import ReviewOutcome
from app.models.learning import GeneratedResource, LearningScene, LearningUnit

_PROVIDER_ID = "deepseek_responses"


class ResourcePublicationError(ValueError):
    """Safe rejection before a resource can be persisted or published."""

    def __init__(self) -> None:
        super().__init__("Resource cannot be published from the supplied review result.")


async def _owned_scene(
    db: AsyncSession, *, owner_id: UUID, learning_unit_id: UUID, scene_id: UUID
) -> LearningScene | None:
    return cast(
        LearningScene | None,
        await db.scalar(
            select(LearningScene)
            .join(LearningUnit, LearningUnit.id == LearningScene.learning_unit_id)
            .where(
                LearningScene.id == scene_id,
                LearningScene.learning_unit_id == learning_unit_id,
                LearningUnit.user_id == owner_id,
            )
        ),
    )


async def record_reviewed_resource(
    db: AsyncSession,
    *,
    owner_id: UUID,
    learning_unit_id: UUID,
    scene_id: UUID,
    review: ReviewOutcome,
    knowledge_point_id: str | None = None,
) -> GeneratedResource:
    """Store a new immutable candidate; only an approved schema-valid one is published."""
    resource = review.resource
    try:
        envelope = validate_learning_resource(
            {
                "resource_type": resource.resource_type.value,
                "prompt_version": resource.prompt_version,
                "content": resource.content,
            },
            expected_type=resource.resource_type,
        )
    except ResourceSchemaError:
        raise ResourcePublicationError from None
    scene = await _owned_scene(
        db, owner_id=owner_id, learning_unit_id=learning_unit_id, scene_id=scene_id
    )
    if scene is None:
        raise ResourcePublicationError

    latest_version = await db.scalar(
        select(func.max(GeneratedResource.version)).where(
            GeneratedResource.scene_id == scene.id,
            GeneratedResource.resource_type == resource.resource_type.value,
        )
    )
    version = 1 if latest_version is None else int(latest_version) + 1
    previous_published = await db.scalar(
        select(GeneratedResource)
        .where(
            GeneratedResource.scene_id == scene.id,
            GeneratedResource.resource_type == resource.resource_type.value,
            GeneratedResource.review_status == "passed",
            GeneratedResource.published_at.is_not(None),
        )
        .order_by(GeneratedResource.version.desc())
        .limit(1)
    )
    content = envelope["content"]
    assert isinstance(content, dict)
    review_comments: dict[str, object] = {
        "review_version": "resource-review-v1",
        "verdict": review.verdict.value,
        "issues": [dict(issue) for issue in review.issues],
        "correction_attempts": review.correction_attempts,
        "review_model_id": review.review_model_id,
    }
    metadata: dict[str, object] = {
        "provider": _PROVIDER_ID,
        "model_id": resource.model_id,
        "prompt_version": resource.prompt_version,
        "content_version": version,
    }
    persisted = GeneratedResource(
        user_id=owner_id,
        learning_unit_id=learning_unit_id,
        scene_id=scene.id,
        knowledge_point_id=knowledge_point_id,
        resource_type=resource.resource_type.value,
        content=content,
        generated_by="LearningUnitGenerator",
        review_comments=review_comments,
        review_status="passed" if review.approved else "rejected",
        version=version,
        supersedes_id=previous_published.id if review.approved and previous_published else None,
        generation_metadata=metadata,
        published_at=datetime.now(timezone.utc) if review.approved else None,
    )
    db.add(persisted)
    await db.flush()
    return persisted
