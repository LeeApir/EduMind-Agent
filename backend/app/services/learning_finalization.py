"""Turn generated candidates into one student-visible, reviewed learning unit."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.learning_resource_schema import LearningResourceType
from app.agents.learning_unit_generator import LearningResourceRequest, LearningUnitGenerator
from app.agents.review_agent import ReviewAgent, ReviewOutcome
from app.models.learning import GeneratedResource, LearningScene, LearningUnit
from app.services.provider_gateway import ProviderGateway
from app.services.resource_publication import ResourcePublicationError, record_reviewed_resource


@dataclass(frozen=True, slots=True)
class FinalizedLearningUnit:
    """A committed finalization result, safe to turn into a public SSE event."""

    published: bool
    learning_unit_id: UUID | None
    scene_id: UUID | None
    scene_version: int | None
    resource_ids: tuple[UUID, ...]


async def finalize_learning_unit(
    db: AsyncSession,
    *,
    owner_id: UUID,
    goal: str,
    code_language: str,
    gateway: ProviderGateway,
) -> FinalizedLearningUnit:
    """Generate, review, and atomically expose a complete first learning scene.

    Candidates are retained for audit, but a failed generation or review leaves the
    unit non-ready and the scene non-passed, so owner-scoped read APIs cannot expose
    any partial or rejected material.
    """
    title = goal.strip()[:200]
    unit = LearningUnit(
        user_id=owner_id,
        title=title,
        learning_objectives={"goal": goal.strip()},
        outline={
            "scene_key": "intro",
            "resource_types": [kind.value for kind in LearningResourceType],
        },
        status="draft",
    )
    db.add(unit)
    await db.flush()
    scene = LearningScene(
        learning_unit_id=unit.id,
        scene_key="intro",
        scene_order=1,
        scene_type="first_learning",
        input_snapshot={"goal": goal.strip(), "code_language": code_language},
        generation_status="pending",
        review_status="pending",
    )
    db.add(scene)
    await db.flush()

    generation = await LearningUnitGenerator(gateway).generate(
        LearningResourceRequest(
            knowledge_point=title,
            learner_goal=goal,
            code_language=code_language,
        )
    )
    reviews: list[ReviewOutcome] = []
    for candidate in generation.resources:
        reviews.append(await ReviewAgent(gateway).review(candidate))

    expected_types = set(LearningResourceType)
    generated_types = {candidate.resource_type for candidate in generation.resources}
    all_approved = (
        not generation.failures
        and generated_types == expected_types
        and len(generation.resources) == len(expected_types)
        and all(review.approved for review in reviews)
    )
    persisted: list[GeneratedResource] = []
    try:
        for review in reviews:
            persisted.append(
                await record_reviewed_resource(
                    db,
                    owner_id=owner_id,
                    learning_unit_id=unit.id,
                    scene_id=scene.id,
                    review=review,
                )
            )
    except ResourcePublicationError:
        await db.rollback()
        raise

    if all_approved:
        scene.generation_status = "complete"
        scene.review_status = "passed"
        unit.status = "ready"
        unit.review_summary = {"verdict": "pass", "resource_count": len(persisted)}
    else:
        scene.generation_status = "failed" if generation.failures else "complete"
        scene.review_status = "rejected"
        unit.status = "failed"
        unit.review_summary = {
            "verdict": "reject",
            "generation_failure_count": len(generation.failures),
            "rejected_resource_count": sum(not review.approved for review in reviews),
        }
    await db.commit()

    if not all_approved:
        return FinalizedLearningUnit(False, None, None, None, ())
    return FinalizedLearningUnit(
        True,
        unit.id,
        scene.id,
        scene.version,
        tuple(resource.id for resource in persisted),
    )
