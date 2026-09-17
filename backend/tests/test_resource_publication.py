"""Reviewed resources become immutable versions and remain owner-scoped."""

import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.learning_resource_schema import LearningResourceType
from app.agents.learning_unit_generator import PendingLearningResource
from app.agents.review_agent import ReviewOutcome
from app.agents.review_schema import ReviewVerdict
from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import LearningScene, LearningUnit
from app.services.owned_learning import published_resource
from app.services.resource_publication import record_reviewed_resource

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def candidate(markdown: str) -> PendingLearningResource:
    return PendingLearningResource(
        resource_type=LearningResourceType.EXPLANATION,
        content={"markdown": markdown},
        prompt_version="learning-resources-v1",
        model_id="generation-model",
        usage=None,
    )


def outcome(markdown: str, verdict: ReviewVerdict) -> ReviewOutcome:
    issues = () if verdict is ReviewVerdict.PASS else (
        {"area": "fact", "severity": "major", "message": "Incorrect relation."},
    )
    return ReviewOutcome(
        resource=candidate(markdown),
        verdict=verdict,
        issues=issues,
        review_model_id="review-model",
        correction_attempts=0,
    )


def test_publish_gate_versions_and_owner_reads_preserve_prior_visible_resource() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                owner, stranger = User(is_guest=True), User(is_guest=True)
                db.add_all([owner, stranger])
                await db.flush()
                unit = LearningUnit(user_id=owner.id, status="ready", title="链表")
                db.add(unit)
                await db.flush()
                scene = LearningScene(
                    learning_unit_id=unit.id,
                    scene_key="intro",
                    scene_order=1,
                    scene_type="explanation",
                    generation_status="complete",
                    review_status="passed",
                )
                db.add(scene)
                await db.flush()
                owner_id, stranger_id, unit_id, scene_id = owner.id, stranger.id, unit.id, scene.id
                await db.commit()

            async with sessions() as db:
                first = await record_reviewed_resource(
                    db,
                    owner_id=owner_id,
                    learning_unit_id=unit_id,
                    scene_id=scene_id,
                    knowledge_point_id="linked-list",
                    review=outcome("已审核版本", ReviewVerdict.PASS),
                )
                rejected = await record_reviewed_resource(
                    db,
                    owner_id=owner_id,
                    learning_unit_id=unit_id,
                    scene_id=scene_id,
                    review=outcome("错误候选", ReviewVerdict.REJECT),
                )
                replacement = await record_reviewed_resource(
                    db,
                    owner_id=owner_id,
                    learning_unit_id=unit_id,
                    scene_id=scene_id,
                    review=outcome("新版正式内容", ReviewVerdict.PASS),
                )
                await db.commit()

            assert [first.version, rejected.version, replacement.version] == [1, 2, 3]
            assert first.published_at is not None
            assert rejected.published_at is None
            assert rejected.review_status == "rejected"
            assert replacement.supersedes_id == first.id
            assert replacement.generation_metadata == {
                "provider": "configured_openai_compatible",
                "model_id": "generation-model",
                "prompt_version": "learning-resources-v1",
                "content_version": 3,
            }
            async with sessions() as db:
                visible_first = await published_resource(db, owner_id, first.id)
                visible_rejected = await published_resource(db, owner_id, rejected.id)
                visible_replacement = await published_resource(db, owner_id, replacement.id)
                foreign = await published_resource(db, stranger_id, replacement.id)
                assert visible_first is not None
                assert visible_first.content["markdown"] == "已审核版本"
                assert visible_rejected is None
                assert visible_replacement is not None
                assert visible_replacement.content["markdown"] == "新版正式内容"
                assert foreign is None
        finally:
            await engine.dispose()

    asyncio.run(exercise())
