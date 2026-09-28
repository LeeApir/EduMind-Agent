"""PostgreSQL lease, recovery and owner-bound media publication for animation jobs."""

import asyncio
import hashlib
import json
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.animation_templates.insertion_plan import srt_for_insertion
from app.core.database import create_database_engine
from app.models.animation import (
    AnimationJob,
    AnimationJobEvent,
    AnimationMedia,
    AnimationResourceBinding,
)
from app.models.auth import User
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_cache import AnimationCache
from app.services.animation_jobs import reserve_animation_job
from app.services.animation_renderer import RenderedCandidate, RenderError
from app.services.animation_worker import (
    claim_animation_job,
    heartbeat_animation_job,
    publish_animation_job,
    reclaim_expired_animation_jobs,
    report_animation_progress,
    run_one_animation_job,
)

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


async def _clean(sessions: async_sessionmaker) -> None:
    async with sessions() as db:
        await db.execute(delete(AnimationResourceBinding))
        await db.execute(delete(AnimationJobEvent))
        await db.execute(delete(AnimationJob))
        await db.execute(delete(AnimationMedia))
        await db.commit()


async def _reserve(sessions: async_sessionmaker, *, value: int = 2) -> AnimationJob:
    async with sessions() as db:
        user = User(is_guest=True)
        db.add(user)
        await db.flush()
        unit = LearningUnit(user_id=user.id, title="链表动画", status="ready")
        db.add(unit)
        await db.flush()
        scene = LearningScene(
            learning_unit_id=unit.id, scene_key="video", scene_order=1,
            scene_type="video", version=1, generation_status="complete",
            review_status="passed",
        )
        db.add(scene)
        await db.commit()
    async with sessions() as db:
        reservation = await reserve_animation_job(
            db, owner_id=user.id, learning_unit_id=unit.id,
            scene_id=scene.id, scene_version=1,
            template_id="linked-list-insertion", template_version="1.0.0",
            parameters={"values": [1, 3, 5], "index": 1, "value": value},
            idempotency_key=uuid4().hex,
        )
        return reservation.job


def _fake_renderer(template_id: str, parameters: dict[str, object], *, work_root: Path):
    assert template_id == "linked-list-insertion"
    attempt = Path(tempfile.mkdtemp(prefix="fake-", dir=work_root))
    mp4, srt = attempt / "scene.mp4", attempt / "scene.srt"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypisom" + json.dumps(parameters, sort_keys=True).encode())
    srt.write_text(srt_for_insertion(), encoding="utf-8")
    return RenderedCandidate(
        attempt, mp4, srt, 36.0,
        hashlib.sha256(mp4.read_bytes()).hexdigest(),
        hashlib.sha256(srt.read_bytes()).hexdigest(),
    )


def test_concurrent_claim_and_single_publication_per_owner(tmp_path: Path) -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            await _clean(sessions)
            first, second = await _reserve(sessions), await _reserve(sessions)
            leases = await asyncio.gather(
                claim_animation_job(sessions), claim_animation_job(sessions)
            )
            assert all(lease is not None for lease in leases)
            assert {lease.job_id for lease in leases if lease} == {first.id, second.id}
            cache = AnimationCache(tmp_path, renderer=_fake_renderer)
            for lease in leases:
                assert lease is not None
                assert await heartbeat_animation_job(sessions, lease)
                assert await report_animation_progress(
                    sessions, lease, stage="validating", progress=0.8,
                )
                media = cache.resolve(lease.template_id, lease.parameters)
                assert await publish_animation_job(sessions, lease, cache=cache, media=media)
                assert not await publish_animation_job(sessions, lease, cache=cache, media=media)
            async with sessions() as db:
                jobs = (await db.scalars(select(AnimationJob).where(
                    AnimationJob.id.in_((first.id, second.id)),
                ))).all()
                assert all(job.status == "succeeded" and job.last_event_id == 4 for job in jobs)
                assert len({job.media_id for job in jobs}) == 1
                assert len((await db.scalars(select(AnimationMedia))).all()) == 1
                bindings = (await db.scalars(select(AnimationResourceBinding))).all()
                assert len(bindings) == 2
                assert {binding.user_id for binding in bindings} == {job.user_id for job in jobs}
                assert (await db.scalars(select(AnimationJobEvent.event_id).where(
                    AnimationJobEvent.job_id == first.id
                ).order_by(AnimationJobEvent.event_id))).all() == [1, 2, 3, 4]
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_expired_lease_recovers_once_and_old_attempt_cannot_publish(tmp_path: Path) -> None:
    assert TEST_DATABASE_URL is not None

    async def expire(sessions: async_sessionmaker, job_id) -> None:
        async with sessions() as db:
            await db.execute(update(AnimationJob).where(AnimationJob.id == job_id).values(
                lease_expires_at=func.clock_timestamp() - timedelta(seconds=1)
            ))
            await db.commit()

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            await _clean(sessions)
            job = await _reserve(sessions)
            old = await claim_animation_job(sessions)
            assert old is not None and old.job_id == job.id
            await expire(sessions, job.id)
            assert not await heartbeat_animation_job(sessions, old)
            restarted_engine = create_database_engine(TEST_DATABASE_URL)
            try:
                restarted_sessions = async_sessionmaker(restarted_engine, expire_on_commit=False)
                assert await reclaim_expired_animation_jobs(restarted_sessions) == 1
                new = await claim_animation_job(restarted_sessions)
            finally:
                await restarted_engine.dispose()
            assert new is not None and new.attempt == 2 and new.token != old.token
            cache = AnimationCache(tmp_path, renderer=_fake_renderer)
            media = cache.resolve(new.template_id, new.parameters)
            assert not await publish_animation_job(sessions, old, cache=cache, media=media)
            assert await publish_animation_job(sessions, new, cache=cache, media=media)
            exhausted = await _reserve(sessions, value=4)
            first = await claim_animation_job(sessions)
            assert first is not None and first.job_id == exhausted.id
            await expire(sessions, exhausted.id)
            assert await reclaim_expired_animation_jobs(sessions) == 1
            second = await claim_animation_job(sessions)
            assert second is not None and second.attempt == 2
            await expire(sessions, exhausted.id)
            assert await reclaim_expired_animation_jobs(sessions) == 1
            assert await claim_animation_job(sessions) is None
            async with sessions() as db:
                loaded = await db.get(AnimationJob, exhausted.id)
                assert loaded is not None and loaded.status == "failed"
                assert loaded.error_code == "RENDER_INTERRUPTED"
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_corrupt_media_fails_without_binding_or_overwriting_learning(tmp_path: Path) -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            await _clean(sessions)
            job = await _reserve(sessions)
            lease = await claim_animation_job(sessions)
            assert lease is not None
            cache = AnimationCache(tmp_path, renderer=_fake_renderer)
            media = cache.resolve(lease.template_id, lease.parameters)
            media.mp4_path.chmod(0o644)
            media.mp4_path.write_bytes(b"broken")
            assert not await publish_animation_job(sessions, lease, cache=cache, media=media)
            async with sessions() as db:
                loaded = await db.get(AnimationJob, job.id)
                assert loaded is not None and loaded.status == "failed"
                assert loaded.error_code == "MEDIA_INVALID" and loaded.media_id is None
                assert (await db.scalars(select(AnimationResourceBinding))).all() == []
                unit = await db.get(LearningUnit, job.learning_unit_id)
                assert unit is not None and unit.status == "ready"
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_render_failure_preserves_existing_learning_resource(tmp_path: Path) -> None:
    assert TEST_DATABASE_URL is not None

    def broken_renderer(template_id: str, parameters: dict[str, object], *, work_root: Path):
        raise RenderError("RENDER_UNAVAILABLE")

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            await _clean(sessions)
            job = await _reserve(sessions)
            async with sessions() as db:
                unit = await db.get(LearningUnit, job.learning_unit_id)
                assert unit is not None
                unit.outline = {"summary": "已审核的讲解"}
                await db.commit()
            processed = await run_one_animation_job(
                sessions, cache=AnimationCache(tmp_path, renderer=broken_renderer),
            )
            assert processed == job.id
            async with sessions() as db:
                loaded = await db.get(AnimationJob, job.id)
                unit = await db.get(LearningUnit, job.learning_unit_id)
                assert loaded is not None and loaded.status == "failed"
                assert loaded.error_code == "RENDER_UNAVAILABLE"
                assert loaded.media_id is None and loaded.last_event_id == 3
                assert unit is not None and unit.outline == {"summary": "已审核的讲解"}
                assert (await db.scalars(select(AnimationMedia))).all() == []
                assert (await db.scalars(select(AnimationResourceBinding))).all() == []
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(os.getenv("EDUMIND_DOCKER_TESTS") != "1", reason="needs Docker")
def test_real_job_render_persists_media_and_events(tmp_path: Path) -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            await _clean(sessions)
            job = await _reserve(sessions, value=8)
            processed = await run_one_animation_job(sessions, cache=AnimationCache(tmp_path))
            assert processed == job.id
            async with sessions() as db:
                loaded = await db.get(AnimationJob, job.id)
                assert loaded is not None and loaded.status == "succeeded"
                assert loaded.media_id is not None and loaded.last_event_id == 4
                bindings = (await db.scalars(select(AnimationResourceBinding))).all()
                assert len(bindings) == 1 and bindings[0].user_id == job.user_id
                assert bindings[0].media_id == loaded.media_id
                media = await db.get(AnimationMedia, loaded.media_id)
                assert media is not None and media.review_status == "passed"
                assert media.duration_seconds == 36
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(os.getenv("EDUMIND_DOCKER_TESTS") != "1", reason="needs Docker")
def test_separate_worker_process_claims_persisted_job() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            await _clean(sessions)
            job = await _reserve(sessions, value=9)
            backend = Path(__file__).resolve().parents[1]
            environment = {**os.environ, "EDUMIND_DATABASE_URL": TEST_DATABASE_URL}
            worker = await asyncio.create_subprocess_exec(
                sys.executable, str(backend / "scripts" / "run_animation_worker.py"),
                "--once", cwd=backend, env=environment,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(worker.communicate(), timeout=150)
            assert worker.returncode == 0, stderr.decode()
            assert str(job.id).encode() in stdout
            async with sessions() as db:
                loaded = await db.get(AnimationJob, job.id)
                assert loaded is not None and loaded.status == "succeeded"
                assert loaded.media_id is not None
                assert len((await db.scalars(select(AnimationResourceBinding).where(
                    AnimationResourceBinding.job_id == job.id,
                ))).all()) == 1
        finally:
            await engine.dispose()

    asyncio.run(exercise())
