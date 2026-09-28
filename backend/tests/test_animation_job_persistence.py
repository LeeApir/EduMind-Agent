"""PostgreSQL job idempotency, owner FKs, stable event replay and restart."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.animation import (
    AnimationJob,
    AnimationJobEvent,
    AnimationMedia,
    AnimationResourceBinding,
)
from app.models.auth import User
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_jobs import (
    AnimationEventCursorInvalid,
    AnimationIdempotencyConflict,
    AnimationTargetUnavailable,
    append_animation_event,
    replay_animation_events,
    reserve_animation_job,
)

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


async def _target(sessions: async_sessionmaker) -> tuple[User, LearningUnit, LearningScene]:
    async with sessions() as db:
        user = User(is_guest=True)
        db.add(user)
        await db.flush()
        unit = LearningUnit(user_id=user.id, title="链表插入", status="ready")
        db.add(unit)
        await db.flush()
        scene = LearningScene(
            learning_unit_id=unit.id, scene_key="animation", scene_order=1,
            scene_type="video", version=1, generation_status="complete",
            review_status="passed",
        )
        db.add(scene)
        await db.commit()
        return user, unit, scene


def test_job_replay_events_survive_reconnect_and_owner_isolation() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            user, unit, scene = await _target(sessions)
            other, other_unit, other_scene = await _target(sessions)
            request = {
                "learning_unit_id": unit.id, "scene_id": scene.id, "scene_version": 1,
                "template_id": "linked-list-insertion", "template_version": "1.0.0",
                "parameters": {"values": [1, 3, 5], "index": 1, "value": 2},
                "idempotency_key": "same-key",
            }
            async with sessions() as db:
                first = await reserve_animation_job(db, owner_id=user.id, **request)
                assert first.created and first.job.status == "queued"
                assert first.job.last_event_id == 1 and first.job.attempt == 0
                original_id = first.job.id
            async with sessions() as db:
                replay = await reserve_animation_job(db, owner_id=user.id, **request)
                assert not replay.created and replay.job.id == original_id
                with pytest.raises(AnimationIdempotencyConflict):
                    await reserve_animation_job(
                        db, owner_id=user.id,
                        **{**request, "parameters": {**request["parameters"], "value": 4}}
                    )
            async with sessions() as db:
                second = await reserve_animation_job(
                    db, owner_id=other.id,
                    **{**request, "learning_unit_id": other_unit.id,
                       "scene_id": other_scene.id},
                )
                assert second.created and second.job.id != original_id
            async def concurrent_reserve():
                async with sessions() as concurrent_db:
                    return await reserve_animation_job(
                        concurrent_db, owner_id=user.id,
                        **{**request, "idempotency_key": "concurrent-key"},
                    )

            concurrent = await asyncio.gather(concurrent_reserve(), concurrent_reserve())
            assert sorted(item.created for item in concurrent) == [False, True]
            assert concurrent[0].job.id == concurrent[1].job.id
            async with sessions() as db:
                event = await append_animation_event(
                    db, owner_id=user.id, job_id=original_id,
                    event_type="progress", payload={"stage": "render", "progress": 0.4},
                )
                await db.commit()
                assert event.event_id == 2
                with pytest.raises(ValueError, match="payload"):
                    await append_animation_event(
                        db, owner_id=user.id, job_id=original_id,
                        event_type="progress", payload={"path": "/private/media"},
                    )
        finally:
            await engine.dispose()

        restarted = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(restarted, expire_on_commit=False)
            async with sessions() as db:
                job, events = await replay_animation_events(
                    db, owner_id=user.id, job_id=original_id
                )
                assert job.last_event_id == 2 and [e.event_id for e in events] == [1, 2]
                _, later = await replay_animation_events(
                    db, owner_id=user.id, job_id=original_id, after=1
                )
                assert [e.event_id for e in later] == [2]
                with pytest.raises(AnimationEventCursorInvalid):
                    await replay_animation_events(
                        db, owner_id=user.id, job_id=original_id, after=3
                    )
                with pytest.raises(AnimationTargetUnavailable):
                    await replay_animation_events(
                        db, owner_id=other.id, job_id=original_id
                    )
                await db.rollback()
            with pytest.raises(IntegrityError):
                async with restarted.begin() as connection:
                    await connection.execute(
                        update(AnimationJob).where(AnimationJob.id == original_id)
                        .values(status="invented")
                    )
            with pytest.raises(IntegrityError):
                async with restarted.begin() as connection:
                    await connection.execute(
                        update(AnimationJob).where(AnimationJob.id == original_id)
                        .values(status="running", attempt=1)
                    )
            with pytest.raises(IntegrityError):
                async with sessions() as db:
                    db.add(AnimationJobEvent(
                        job_id=original_id, event_id=3, user_id=other.id,
                        event_type="progress", payload={"stage": "render"},
                    ))
                    await db.commit()
        finally:
            await restarted.dispose()

    asyncio.run(exercise())


def test_media_binding_requires_same_job_owner_and_target() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            user, unit, scene = await _target(sessions)
            other, _, _ = await _target(sessions)
            async with sessions() as db:
                reserved = await reserve_animation_job(
                    db, owner_id=user.id, learning_unit_id=unit.id,
                    scene_id=scene.id, scene_version=1,
                    template_id="linked-list-deletion", template_version="1.0.0",
                    parameters={"values": [1, 3], "index": 1},
                    idempotency_key=uuid4().hex,
                )
                job = reserved.job
                media = await db.scalar(select(AnimationMedia).where(
                    AnimationMedia.cache_key == job.cache_key,
                ))
                if media is None:
                    media = AnimationMedia(
                        cache_key=job.cache_key, template_id=job.template_id,
                        template_version=job.template_version,
                        review_rule_version=job.review_rule_version,
                        source_sha256=job.source_sha256,
                        image_digest=job.image_digest, font_digest=job.font_digest,
                        renderer_config_sha256=job.renderer_config_sha256,
                        subtitle_version=job.subtitle_version,
                        mp4_sha256="a" * 64, srt_sha256="b" * 64,
                        mp4_size=100, srt_size=100, duration_seconds=42,
                        review_status="passed",
                    )
                    db.add(media)
                    await db.flush()
                job.media_id = media.id
                job.status = "succeeded"
                job.progress = 1.0
                await db.commit()
            with pytest.raises(IntegrityError):
                async with sessions() as db:
                    db.add(AnimationResourceBinding(
                        user_id=other.id, job_id=job.id, media_id=media.id,
                        learning_unit_id=unit.id, scene_id=scene.id, scene_version=1,
                    ))
                    await db.commit()
            async with sessions() as db:
                bound = AnimationResourceBinding(
                    user_id=user.id, job_id=job.id, media_id=media.id,
                    learning_unit_id=unit.id, scene_id=scene.id, scene_version=1,
                )
                db.add(bound)
                await db.commit()
                assert await db.scalar(select(AnimationResourceBinding.id).where(
                    AnimationResourceBinding.user_id == user.id,
                    AnimationResourceBinding.job_id == job.id,
                )) == bound.id
        finally:
            await engine.dispose()

    asyncio.run(exercise())
