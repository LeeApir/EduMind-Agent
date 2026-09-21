"""PostgreSQL persistence of versioned learning data."""

import asyncio
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import GeneratedResource, LearningScene, LearningUnit, StudentProfile

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def test_versioned_snapshots_survive_new_connection_and_enforce_review_boundary() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        write_engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(write_engine, expire_on_commit=False)
            async with sessions() as db:
                user = User(is_guest=True)
                db.add(user)
                await db.flush()
                profile_v1 = StudentProfile(
                    user_id=user.id,
                    version=1,
                    initial_query="我想学习链表插入",
                    learning_goals={"topic": "linked-list insertion"},
                    evidence={"learning_goals": {"source": "initial_query", "confidence": 0.9}},
                )
                profile_v2 = StudentProfile(
                    user_id=user.id,
                    version=2,
                    initial_query="我想学习链表插入",
                    learning_goals={"topic": "linked-list insertion", "language": "c"},
                    evidence={"learning_goals": {"source": "user_feedback", "confidence": 1.0}},
                )
                unit = LearningUnit(
                    user_id=user.id,
                    title="链表插入",
                    status="ready",
                    profile_snapshot={"version": 2},
                    outline={"scenes": ["intro"]},
                )
                db.add_all([profile_v1, profile_v2, unit])
                await db.flush()
                scene_v1 = LearningScene(
                    learning_unit_id=unit.id,
                    scene_key="intro",
                    scene_order=1,
                    scene_type="explanation",
                    version=1,
                    generation_status="complete",
                    review_status="passed",
                )
                scene_v2 = LearningScene(
                    learning_unit_id=unit.id,
                    scene_key="intro",
                    scene_order=1,
                    scene_type="explanation",
                    version=2,
                    generation_status="complete",
                    review_status="pending",
                )
                db.add_all([scene_v1, scene_v2])
                await db.flush()
                published = GeneratedResource(
                    user_id=user.id,
                    learning_unit_id=unit.id,
                    scene_id=scene_v1.id,
                    resource_type="explanation",
                    content={"markdown": "先保存 next 指针。"},
                    review_status="passed",
                    review_comments={"summary": "accurate"},
                    version=1,
                    published_at=datetime.now(timezone.utc),
                )
                candidate = GeneratedResource(
                    user_id=user.id,
                    learning_unit_id=unit.id,
                    scene_id=scene_v2.id,
                    resource_type="explanation",
                    content={"markdown": "待审核内容"},
                    review_status="pending",
                    version=2,
                )
                db.add_all([published, candidate])
                await db.commit()
                user_id = user.id
                unit_id = unit.id
                published_id = published.id
                candidate_id = candidate.id
        finally:
            await write_engine.dispose()

        read_engine = create_database_engine(TEST_DATABASE_URL)
        try:
            read_sessions = async_sessionmaker(read_engine)
            async with read_sessions() as db:
                profiles = (
                    await db.scalars(
                        select(StudentProfile)
                        .where(StudentProfile.user_id == user_id)
                        .order_by(StudentProfile.version)
                    )
                ).all()
                assert [profile.version for profile in profiles] == [1, 2]
                assert profiles[0].knowledge_base is None
                assert profiles[1].evidence == {
                    "learning_goals": {"source": "user_feedback", "confidence": 1.0}
                }
                loaded_unit = await db.get(LearningUnit, unit_id)
                assert loaded_unit is not None
                assert loaded_unit.profile_snapshot == {"version": 2}
                scenes = (
                    await db.scalars(
                        select(LearningScene)
                        .where(LearningScene.learning_unit_id == unit_id)
                        .order_by(LearningScene.version)
                    )
                ).all()
                assert [scene.version for scene in scenes] == [1, 2]
                resources = (
                    await db.scalars(
                        select(GeneratedResource)
                        .where(GeneratedResource.learning_unit_id == unit_id)
                        .order_by(GeneratedResource.version)
                    )
                ).all()
                assert [resource.version for resource in resources] == [1, 2]
                assert resources[0].review_status == "passed"
                assert resources[0].published_at is not None
                assert resources[1].review_status == "pending"
                assert resources[1].published_at is None

            with pytest.raises(IntegrityError):
                async with read_engine.begin() as connection:
                    await connection.execute(
                        update(GeneratedResource)
                        .where(GeneratedResource.id == candidate_id)
                        .values(published_at=datetime.now(timezone.utc))
                    )
            with pytest.raises(IntegrityError):
                async with read_engine.begin() as connection:
                    await connection.execute(
                        update(GeneratedResource)
                        .where(GeneratedResource.id == published_id)
                        .values(content={"markdown": "silently changed"})
                    )
        finally:
            await read_engine.dispose()

    asyncio.run(exercise())
