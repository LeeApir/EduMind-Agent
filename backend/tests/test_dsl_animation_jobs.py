"""Preparation receipt lifecycle; publication/API/worker tests follow in the same T028 task."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_animation_dsl_review import GRAPH, target

from app.core.database import create_database_engine
from app.models.animation_generation import AnimationPreparation
from app.models.auth import GuestSessionRecord
from app.models.learning import utc_now
from app.services.animation_intent import intent_from_payload
from app.services.animation_jobs import AnimationIdempotencyConflict, AnimationTargetUnavailable
from app.services.animation_preparation import (
    AnimationPreparationLimit,
    advance_preparation,
    cancel_preparation,
    fail_preparation,
    owned_preparation,
    preparation_payload,
    reserve_preparation,
)

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="dedicated PostgreSQL required")


def intent():
    return intent_from_payload(
        {
            "knowledge_point_id": "array",
            "operation": "compare",
            "parameters": {"values": [1, 2]},
            "presentation": "standard",
        }
    )


async def setup(sessions, *, seconds=3600):
    ids = await target(sessions)
    session_hash = uuid4().hex * 2
    async with sessions() as db, db.begin():
        db.add(
            GuestSessionRecord(
                token_hash=session_hash,
                user_id=ids[0],
                created_at=utc_now(),
                expires_at=utc_now() + timedelta(seconds=seconds),
            )
        )
    return ids, session_hash


async def reserve(sessions, ids, session_hash, key=None):
    async with sessions() as db:
        return await reserve_preparation(
            db,
            GRAPH,
            owner=ids[0],
            session_hash=session_hash,
            unit_id=ids[1],
            scene_id=ids[2],
            scene_version=1,
            intent=intent(),
            idempotency_key=key or str(uuid4()),
        )


def test_pg_preparation_replay_binding_cancel_and_safe_snapshot():
    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            ids, session_hash = await setup(sessions)
            key = str(uuid4())
            original = await reserve(sessions, ids, session_hash, key)
            replay = await reserve(sessions, ids, session_hash, key)
            a, b = original.operation, replay.operation
            assert original.created and not replay.created and a.id == b.id
            assert a.execution_token == b.execution_token and a.deadline == b.deadline
            assert set(preparation_payload(a)) == {"id", "stage", "deadline"}
            assert 179 < (a.deadline - a.created_at).total_seconds() <= 180
            async with sessions() as db:
                with pytest.raises(AnimationIdempotencyConflict):
                    await reserve_preparation(
                        db,
                        GRAPH,
                        owner=ids[0],
                        session_hash=session_hash,
                        unit_id=ids[1],
                        scene_id=ids[2],
                        scene_version=1,
                        intent=intent(),
                        idempotency_key=key,
                        allow_template_fallback=True,
                    )
            async with sessions() as db:
                assert not await advance_preparation(
                    db,
                    GRAPH,
                    owner=ids[0],
                    session_hash=session_hash,
                    operation_id=a.id,
                    execution_token=uuid4(),
                    stage="generating",
                )
                assert await advance_preparation(
                    db,
                    GRAPH,
                    owner=ids[0],
                    session_hash=session_hash,
                    operation_id=a.id,
                    execution_token=a.execution_token,
                    stage="generating",
                )
            async with sessions() as db:
                with pytest.raises(AnimationTargetUnavailable):
                    await cancel_preparation(
                        db,
                        owner=ids[0],
                        session_hash=session_hash,
                        operation_id=a.id,
                        execution_token=uuid4(),
                    )
                await cancel_preparation(
                    db,
                    owner=ids[0],
                    session_hash=session_hash,
                    operation_id=a.id,
                    execution_token=a.execution_token,
                )
            async with sessions() as db:
                assert not await advance_preparation(
                    db,
                    GRAPH,
                    owner=ids[0],
                    session_hash=session_hash,
                    operation_id=a.id,
                    execution_token=a.execution_token,
                    stage="reviewing",
                )
                with pytest.raises(AnimationTargetUnavailable):
                    await owned_preparation(
                        db, owner=uuid4(), session_hash=session_hash, operation_id=a.id
                    )
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_pg_preparation_concurrent_two_limit_and_immutable_identity():
    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            ids, session_hash = await setup(sessions)
            outcomes = await asyncio.gather(
                *(reserve(sessions, ids, session_hash) for _ in range(3)),
                return_exceptions=True,
            )
            assert sum(isinstance(x, AnimationPreparationLimit) for x in outcomes) == 1
            successes = [x for x in outcomes if not isinstance(x, Exception)]
            assert len(successes) == 2
            row = successes[0].operation
            for column, value in [
                ("deadline", "deadline + interval '1 second'"),
                ("execution_token", "gen_random_uuid()"),
                ("originating_session_hash", "repeat('f',64)"),
            ]:
                async with sessions() as db:
                    with pytest.raises(DBAPIError):
                        await db.execute(
                            text(
                                f"UPDATE animation_preparations SET {column}={value} WHERE id=:id"
                            ),
                            {"id": row.id},
                        )
                        await db.commit()
            async with sessions() as db:
                await advance_preparation(
                    db,
                    GRAPH,
                    owner=ids[0],
                    session_hash=session_hash,
                    operation_id=row.id,
                    execution_token=row.execution_token,
                    stage="compiled",
                )
            async with sessions() as db:
                with pytest.raises(DBAPIError):
                    await db.execute(
                        text("UPDATE animation_preparations SET stage='reserved' WHERE id=:id"),
                        {"id": row.id},
                    )
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_pg_preparation_expired_original_session_cannot_be_replaced():
    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            ids, original_session = await setup(sessions, seconds=1)
            key = str(uuid4())
            first = await reserve(sessions, ids, original_session, key)
            assert first.operation.deadline == first.operation.originating_session_expires_at
            await asyncio.sleep(1.1)
            async with sessions() as db:
                assert not await fail_preparation(
                    db,
                    owner=ids[0],
                    operation_id=first.operation.id,
                    execution_token=uuid4(),
                    code="ANIMATION_UNAVAILABLE",
                )
                assert await fail_preparation(
                    db,
                    owner=ids[0],
                    operation_id=first.operation.id,
                    execution_token=first.operation.execution_token,
                    code="ANIMATION_UNAVAILABLE",
                )
                assert not await fail_preparation(
                    db,
                    owner=ids[0],
                    operation_id=first.operation.id,
                    execution_token=first.operation.execution_token,
                    code="ANIMATION_UNAVAILABLE",
                )
                with pytest.raises(ValueError):
                    await fail_preparation(
                        db,
                        owner=ids[0],
                        operation_id=first.operation.id,
                        execution_token=first.operation.execution_token,
                        code="raw-provider-secret",
                    )
            new_session = uuid4().hex * 2
            async with sessions() as db, db.begin():
                db.add(
                    GuestSessionRecord(
                        token_hash=new_session,
                        user_id=ids[0],
                        created_at=utc_now(),
                        expires_at=utc_now() + timedelta(hours=1),
                    )
                )
            with pytest.raises(AnimationTargetUnavailable):
                await reserve(sessions, ids, new_session, key)
            fresh = await reserve(sessions, ids, new_session)
            assert fresh.operation.id != first.operation.id
            async with sessions() as db:
                retired = await db.scalar(
                    select(AnimationPreparation).where(
                        AnimationPreparation.id == first.operation.id,
                    )
                )
                assert retired.stage == "failed"
                assert retired.error_code == "ANIMATION_PREPARATION_EXPIRED"
                assert retired.execution_token == first.operation.execution_token
                assert retired.originating_session_hash == original_session
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_pg_explicit_render_kind_candidate_and_media_owner_constraints(monkeypatch):
    from test_dsl_render_worker import seed

    from app.models.animation import AnimationMedia
    from app.services.animation_worker import fail_animation_job

    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            a, cid_a = await seed(sessions)
            b, cid_b = await seed(sessions)
            # These synthetic byte descriptors check SQL provenance only, never media acceptance.
            async with sessions() as db, db.begin():
                media = AnimationMedia(
                    cache_key=uuid4().hex * 2,
                    render_kind="dsl",
                    user_id=a.owner_id,
                    candidate_id=cid_a,
                    template_id=None,
                    template_version=None,
                    review_rule_version="constraint-fixture",
                    source_sha256="1" * 64,
                    image_digest="sha256:" + "2" * 64,
                    font_digest="3" * 64,
                    renderer_config_sha256="4" * 64,
                    subtitle_version="constraint-fixture",
                    mp4_sha256="5" * 64,
                    srt_sha256="6" * 64,
                    mp4_size=1,
                    srt_size=1,
                    duration_seconds=30,
                    review_status="passed",
                    source_versions={},
                )
                db.add(media)
                await db.flush()
                mid = media.id
            mutations = [
                ("UPDATE animation_jobs SET template_id='fake' WHERE id=:id", {"id": a.job_id}),
                (
                    "UPDATE animation_jobs SET candidate_id=:cid WHERE id=:id",
                    {"id": a.job_id, "cid": cid_b},
                ),
                (
                    "UPDATE animation_jobs SET media_id=:mid WHERE id=:id",
                    {"id": b.job_id, "mid": mid},
                ),
                (
                    "UPDATE animation_media SET user_id=:owner WHERE id=:id",
                    {"id": mid, "owner": b.owner_id},
                ),
                ("UPDATE animation_media SET render_kind='template' WHERE id=:id", {"id": mid}),
            ]
            for sql, parameters in mutations:
                async with sessions() as db:
                    with pytest.raises(DBAPIError):
                        await db.execute(text(sql), parameters)
                        await db.commit()
            await fail_animation_job(sessions, a, code="DSL_RENDER_INTERRUPTED")
            await fail_animation_job(sessions, b, code="DSL_RENDER_INTERRUPTED")
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(os.getenv("EDUMIND_DOCKER_TESTS") != "1", reason="actual Docker required")
def test_pg_real_private_dsl_publication_access_corruption_and_revoke(monkeypatch, tmp_path):
    from test_dsl_render_worker import seed

    from app.models.animation import AnimationJob
    from app.services.animation_cache import AnimationCache
    from app.services.animation_dsl_candidates import revoke_candidate
    from app.services.animation_dsl_media_cache import AnimationDSLMediaCache
    from app.services.animation_dsl_publication import publish_dsl_job
    from app.services.animation_media import (
        MediaUnavailable,
        open_verified_media,
        owned_reviewed_media,
    )
    from app.workers.dsl_render import render_dsl_job

    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    private_cache = AnimationDSLMediaCache(tmp_path / "approved")

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            lease, cid = await seed(sessions)

            async def complete(result):
                return await publish_dsl_job(sessions, GRAPH, lease, result, cache=private_cache)

            result = await render_dsl_job(
                sessions, GRAPH, lease, cid, work_root=tmp_path / "attempts", complete=complete
            )
            assert result.error_code is None and result.qualification is not None
            async with sessions() as db:
                job = await db.get(AnimationJob, lease.job_id)
                assert job.status == "succeeded" and job.media_id is not None
                mid = job.media_id
                media = await owned_reviewed_media(db, owner_id=lease.owner_id, media_id=mid)
                assert media is not None and media.render_kind == "dsl"
                assert media.template_id is None and media.template_version is None
                assert media.user_id == lease.owner_id and media.candidate_id == cid
                assert media.source_versions["binding"] == result.qualification.binding_sha256
                assert await owned_reviewed_media(db, owner_id=uuid4(), media_id=mid) is None
            hit = private_cache.lookup(
                lease.owner_id, result.qualification.cache_key, result.qualification.compiled
            )
            assert hit is not None
            from fastapi.testclient import TestClient

            from app.core.auth import token_hash
            from app.main import app
            from app.models.auth import GuestSessionRecord

            cookie = "TEST_ONLY_DSL_MEDIA_SESSION"
            async with sessions() as db, db.begin():
                db.add(
                    GuestSessionRecord(
                        token_hash=token_hash(cookie),
                        user_id=lease.owner_id,
                        created_at=utc_now(),
                        expires_at=utc_now() + timedelta(minutes=10),
                    )
                )
            monkeypatch.setenv("EDUMIND_DATABASE_URL", URL)
            monkeypatch.setenv("EDUMIND_ANIMATION_CACHE_ROOT", str(private_cache.base))
            with TestClient(app, base_url="https://testserver") as client:
                client.cookies.set("edumind_session", cookie)
                downloaded = client.get(
                    f"/api/animation-media/{mid}/mp4?download=true", headers={"Range": "bytes=0-3"}
                )
                assert downloaded.status_code == 206 and len(downloaded.content) == 4
                assert downloaded.headers["X-Animation-Generated-By"] == "reviewed-manim-dsl"
                assert "X-Animation-Template-ID" not in downloaded.headers
                assert "X-Animation-Template-Version" not in downloaded.headers
                import json

                assert (
                    json.loads(downloaded.headers["X-Animation-Source-Versions"])
                    == media.source_versions
                )
                assert "attachment" in downloaded.headers["Content-Disposition"]
                subtitles = client.get(f"/api/animation-media/{mid}/srt")
                assert (
                    subtitles.status_code == 200
                    and subtitles.text == result.qualification.compiled.subtitles
                )
            assert (
                private_cache.lookup(
                    uuid4(), result.qualification.cache_key, result.qualification.compiled
                )
                is None
            )
            fd = open_verified_media(
                media, extension="mp4", cache=AnimationCache(private_cache.base)
            )
            assert fd.size == media.mp4_size
            fd.close()
            linked_cache = tmp_path / "symlink-cache"
            linked_cache.symlink_to(private_cache.base, target_is_directory=True)
            with pytest.raises(MediaUnavailable):
                open_verified_media(media, extension="mp4", cache=AnimationCache(linked_cache))
            import time

            from app.services.animation_dsl_gc import collect_private_dsl_orphans

            for path in (hit.mp4_path, hit.srt_path):
                os.utime(path, (time.time() - 90000, time.time() - 90000))
            assert (
                await collect_private_dsl_orphans(
                    sessions, private_cache, owner=lease.owner_id, key=hit.cache_key
                )
                == 0
            )  # Formal immutable references survive age and later withdrawal.
            hit.mp4_path.chmod(0o600)
            hit.mp4_path.write_bytes(b"corrupt")
            assert (
                private_cache.lookup(
                    lease.owner_id, result.qualification.cache_key, result.qualification.compiled
                )
                is None
            )
            with pytest.raises(MediaUnavailable):
                open_verified_media(
                    media, extension="mp4", cache=AnimationCache(private_cache.base)
                )
            async with sessions() as db, db.begin():
                await revoke_candidate(db, GRAPH, owner=lease.owner_id, candidate_id=cid)
            async with sessions() as db:
                assert await owned_reviewed_media(db, owner_id=lease.owner_id, media_id=mid) is None
                job = await db.get(AnimationJob, lease.job_id)
                assert job.status == "succeeded" and job.media_id == mid
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(os.getenv("EDUMIND_DOCKER_TESTS") != "1", reason="actual Docker required")
def test_pg_publication_before_withdrawal_commit_preserves_history_denies_reads(
    monkeypatch, tmp_path
):
    import threading

    from test_dsl_render_worker import seed

    from app.models.animation import AnimationJob
    from app.services.animation_dsl_candidates import revoke_candidate
    from app.services.animation_dsl_media_cache import AnimationDSLMediaCache
    from app.services.animation_dsl_publication import publish_dsl_job
    from app.services.animation_media import owned_reviewed_media
    from app.workers.dsl_render import render_dsl_job

    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    started, release = threading.Event(), threading.Event()
    private_cache = AnimationDSLMediaCache(tmp_path / "approved")
    publish = private_cache.publish_locked

    def blocked(*args):
        started.set()
        assert release.wait(10)
        return publish(*args)

    monkeypatch.setattr(private_cache, "publish_locked", blocked)

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            lease, cid = await seed(sessions)

            async def complete(result):
                return await publish_dsl_job(sessions, GRAPH, lease, result, cache=private_cache)

            async def withdraw():
                async with sessions() as db, db.begin():
                    await revoke_candidate(db, GRAPH, owner=lease.owner_id, candidate_id=cid)

            rendering = asyncio.create_task(
                render_dsl_job(
                    sessions, GRAPH, lease, cid, work_root=tmp_path / "attempts", complete=complete
                )
            )
            assert await asyncio.to_thread(started.wait, 20)
            withdrawing = asyncio.create_task(withdraw())
            await asyncio.sleep(0.05)
            assert not withdrawing.done()  # Publication holds the common qualification locks.
            release.set()
            result = await rendering
            assert result.error_code is None
            await withdrawing
            async with sessions() as db:
                job = await db.get(AnimationJob, lease.job_id)
                assert job.status == "succeeded" and job.media_id is not None
                assert (
                    await owned_reviewed_media(db, owner_id=lease.owner_id, media_id=job.media_id)
                    is None
                )
        finally:
            release.set()
            await engine.dispose()

    asyncio.run(exercise())


def test_pg_current_dsl_migration_downgrade_retains_provenance(monkeypatch):
    import subprocess
    import sys
    from pathlib import Path

    from test_dsl_render_worker import seed

    from app.services.animation_worker import fail_animation_job

    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            lease, _ = await seed(sessions)
            await fail_animation_job(sessions, lease, code="DSL_RENDER_INTERRUPTED")
            env = {
                k: v
                for k, v in os.environ.items()
                if not k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL"))
            }
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "downgrade", "0024_animation_preparations"],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            assert result.returncode != 0
            assert "Cannot downgrade retained DSL job/media provenance" in result.stderr
            async with sessions() as db:
                assert await db.scalar(text("SELECT version_num FROM alembic_version")) == (
                    "0025_animation_dsl_media"
                )
                assert (
                    await db.scalar(
                        text("SELECT count(*) FROM animation_jobs WHERE id=:id"),
                        {"id": lease.job_id},
                    )
                    == 1
                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_pg_atomic_dsl_handoff_reuses_candidate_and_cancel_wins(monkeypatch):
    from test_animation_dsl_review import GENERATION, RAW, FakeGateway

    from app.agents.animation_dsl_review import AnimationDSLReviewAgent, digest
    from app.models.animation import AnimationJob
    from app.models.animation_dsl import DSLCandidate
    from app.services.animation_dsl_candidates import admit_current_policy, build_dsl_reference
    from app.services.animation_dsl_handoff import handoff_video_plan
    from app.services.video_dsl_generation import VideoPlan

    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            ids, session_hash = await setup(sessions)
            first = await reserve(sessions, ids, session_hash)
            async with sessions() as db, db.begin():
                await admit_current_policy(db)
                reference = await build_dsl_reference(
                    db, GRAPH, owner=ids[0], unit_id=ids[1], scene_id=ids[2], version=1
                )
            outcome = await AnimationDSLReviewAgent(FakeGateway()).review(
                RAW.replace('"arrays"', '"array"'),
                reference=reference,
                generation_source=GENERATION,
                animation_intent=intent().payload(),
            )
            assert outcome.approved
            plan = VideoPlan(
                "generated_dsl",
                digest({"intent": intent().payload(), "reference": reference.sha256}),
                outcome=outcome,
            )
            jobs = []
            for reservation in (first, await reserve(sessions, ids, session_hash)):
                async with sessions() as db:
                    job = await handoff_video_plan(
                        db,
                        GRAPH,
                        owner=ids[0],
                        session_hash=session_hash,
                        operation_id=reservation.operation.id,
                        execution_token=reservation.operation.execution_token,
                        plan=plan,
                    )
                    assert job is not None and job.render_kind == "dsl" and job.status == "queued"
                    assert job.template_id is None and job.template_version is None
                    jobs.append(job)
            assert jobs[0].candidate_id == jobs[1].candidate_id
            assert jobs[0].cache_key == jobs[1].cache_key
            assert jobs[0].generation_id != jobs[1].generation_id
            async with sessions() as db:
                assert (
                    len(
                        (
                            await db.scalars(
                                select(DSLCandidate).where(DSLCandidate.user_id == ids[0])
                            )
                        ).all()
                    )
                    == 1
                )
                original = await db.get(AnimationPreparation, first.operation.id)
                assert original.stage == "handed_off" and original.job_id == jobs[0].id
                await cancel_preparation(
                    db,
                    owner=ids[0],
                    session_hash=session_hash,
                    operation_id=first.operation.id,
                    idempotency_key=str(uuid4()),
                )
                assert original.stage == "handed_off"  # Use Job cancellation after handoff.
            pending = await reserve(sessions, ids, session_hash)
            async with sessions() as db:
                await cancel_preparation(
                    db,
                    owner=ids[0],
                    session_hash=session_hash,
                    operation_id=pending.operation.id,
                    execution_token=pending.operation.execution_token,
                )
                assert (
                    await handoff_video_plan(
                        db,
                        GRAPH,
                        owner=ids[0],
                        session_hash=session_hash,
                        operation_id=pending.operation.id,
                        execution_token=pending.operation.execution_token,
                        plan=plan,
                    )
                    is None
                )
                assert (
                    await db.scalar(
                        select(AnimationJob).where(
                            AnimationJob.generation_id == pending.operation.id
                        )
                    )
                    is None
                )
            # Queued test receipts are explicitly cancelled to keep the shared test queue clean.
            from app.services.animation_lifecycle import cancel_animation_job

            for job in jobs:
                async with sessions() as db:
                    await cancel_animation_job(
                        db, owner_id=ids[0], job_id=job.id, idempotency_key=str(uuid4())
                    )
            for winner in ("cancel", "handoff"):
                racing = (await reserve(sessions, ids, session_hash)).operation

                async def loser():
                    async with sessions() as other:
                        if winner == "cancel":
                            return await handoff_video_plan(
                                other,
                                GRAPH,
                                owner=ids[0],
                                session_hash=session_hash,
                                operation_id=racing.id,
                                execution_token=racing.execution_token,
                                plan=plan,
                            )
                        return await cancel_preparation(
                            other,
                            owner=ids[0],
                            session_hash=session_hash,
                            operation_id=racing.id,
                            idempotency_key=str(uuid4()),
                        )

                async with sessions() as db:
                    await owned_preparation(
                        db,
                        owner=ids[0],
                        session_hash=session_hash,
                        operation_id=racing.id,
                        lock=True,
                    )
                    waiting = asyncio.create_task(loser())
                    await asyncio.sleep(0.1)
                    assert not waiting.done()  # The opposite operation contends on this PG lock.
                    if winner == "cancel":
                        await cancel_preparation(
                            db,
                            owner=ids[0],
                            session_hash=session_hash,
                            operation_id=racing.id,
                            execution_token=racing.execution_token,
                        )
                        assert await waiting is None
                        async with sessions() as check:
                            assert (
                                await check.scalar(
                                    select(AnimationJob.id).where(
                                        AnimationJob.generation_id == racing.id
                                    )
                                )
                                is None
                            )
                    else:
                        published = await handoff_video_plan(
                            db,
                            GRAPH,
                            owner=ids[0],
                            session_hash=session_hash,
                            operation_id=racing.id,
                            execution_token=racing.execution_token,
                            plan=plan,
                        )
                        snapshot = await waiting
                        assert snapshot.stage == "handed_off" and snapshot.job_id == published.id
                        async with sessions() as check:
                            await cancel_animation_job(
                                check,
                                owner_id=ids[0],
                                job_id=published.id,
                                idempotency_key=str(uuid4()),
                            )
        finally:
            await engine.dispose()

    asyncio.run(exercise())
