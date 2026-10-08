"""Celery cancellation transactions and unchanged PG-authoritative SSE contracts."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.animation import (
    AnimationDispatchOutbox,
    AnimationJob,
    AnimationJobAttempt,
    AnimationJobEvent,
)
from app.services.animation_attempts import transition
from app.services.animation_cache import AnimationCache
from app.services.animation_lifecycle import cancel_animation_job, retry_animation_job
from app.services.animation_worker import (
    claim_animation_job,
    heartbeat_animation_job,
    publish_animation_job,
)
from app.services.durable_job_dispatch import (
    DispatchMessage,
    claim_dispatches,
    finish_dispatch,
    publish_dispatch_batch,
)
from tests import test_animation_events_api as sse
from tests.test_animation_worker import _clean, _fake_renderer, _reserve

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="isolated PostgreSQL required")


@pytest.mark.parametrize(
    "contract",
    [
        sse.test_terminal_sse_replays_only_new_events_across_client_restart,
        sse.test_gap_returns_expired_and_snapshot_cursor_recovers,
        sse.test_disconnect_does_not_change_job_or_render_count,
        sse.test_live_stream_delivers_progress_and_closes_on_terminal,
        sse.test_expired_cookie_ends_open_stream_and_connection_limit_rejects,
    ],
    ids=["replay-owner-restart", "expired-cursor", "disconnect", "live-terminal", "session-expiry"],
)
def test_existing_sse_contract_with_celery_route(contract, monkeypatch):
    monkeypatch.setenv("EDUMIND_ANIMATION_DISPATCH", "celery")

    async def claim(sessions):
        async with sessions() as db:
            job = await db.scalar(
                select(AnimationJob).where(
                    AnimationJob.status == "queued",
                    AnimationJob.dispatch_backend == "celery",
                )
            )
            assert job is not None
            message = DispatchMessage(job.id, job.dispatch_epoch)
        return await claim_animation_job(sessions, message=message)

    monkeypatch.setattr(sse, "claim_animation_job", claim)
    contract(monkeypatch)


@pytest.mark.parametrize("running", [False, True], ids=["queued", "running"])
def test_cancel_obsoletes_inflight_delivery_and_retry_is_new_receipt(
    running, tmp_path, monkeypatch
):
    monkeypatch.setenv("EDUMIND_ANIMATION_DISPATCH", "celery")

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await _clean(sessions)
            job = await _reserve(sessions)
            assert job.dispatch_backend == "celery"
            (delivery,) = await claim_dispatches(sessions, limit=1)
            lease = None
            if running:
                lease = await claim_animation_job(sessions, message=delivery.message)
                assert await transition(sessions, lease.token, "starting")
            key = uuid4().hex
            async with sessions() as db:
                cancelled = await cancel_animation_job(
                    db,
                    owner_id=job.user_id,
                    job_id=job.id,
                    idempotency_key=key,
                )
                assert cancelled.status == "cancelled"
            assert not await finish_dispatch(sessions, delivery, sent=True)
            assert await claim_animation_job(sessions, message=delivery.message) is None
            async with sessions() as db:
                box = await db.get(AnimationDispatchOutbox, delivery.outbox_id)
                assert box.state == "obsolete" and box.publisher_token is None
                current = await db.get(AnimationJob, job.id)
                assert current.lease_token is None and current.attempt == int(running)
                events = (
                    await db.scalars(
                        select(AnimationJobEvent)
                        .where(
                            AnimationJobEvent.job_id == job.id,
                        )
                        .order_by(AnimationJobEvent.event_id)
                    )
                ).all()
                assert [e.event_type for e in events] == (
                    ["queued", "running", "cancelled"] if running else ["queued", "cancelled"]
                )
                last = current.last_event_id
                replay = await cancel_animation_job(
                    db,
                    owner_id=job.user_id,
                    job_id=job.id,
                    idempotency_key=key,
                )
                assert replay.last_event_id == last
            if lease:
                assert not await transition(sessions, lease.token, "started")
                assert not await heartbeat_animation_job(sessions, lease)
                cache = AnimationCache(tmp_path, renderer=_fake_renderer)
                media = cache.resolve(lease.template_id, lease.parameters)
                assert not await publish_animation_job(sessions, lease, cache=cache, media=media)
                async with sessions() as db:
                    attempt = await db.get(AnimationJobAttempt, lease.token)
                    assert attempt.launch_state == "cleanup_requested"
                    assert attempt.cleanup_requested_at and attempt.cleanup_done_at is None
            retry_key = uuid4().hex
            async with sessions() as db:
                retried, created = await retry_animation_job(
                    db,
                    owner_id=job.user_id,
                    job_id=job.id,
                    idempotency_key=retry_key,
                )
                assert created and retried.id != job.id and retried.retry_of == job.id
                assert retried.dispatch_backend == "celery" and retried.attempt == 0
            async with sessions() as db:
                replayed, created = await retry_animation_job(
                    db,
                    owner_id=job.user_id,
                    job_id=job.id,
                    idempotency_key=retry_key,
                )
                assert not created and replayed.id == retried.id
                boxes = (
                    await db.scalars(
                        select(AnimationDispatchOutbox).where(
                            AnimationDispatchOutbox.job_id == retried.id,
                        )
                    )
                ).all()
                assert len(boxes) == 1 and boxes[0].state == "pending"
                assert (await db.get(AnimationJob, job.id)).status == "cancelled"
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_cancel_commit_failure_rolls_back_job_cleanup_outbox_and_event(monkeypatch):
    monkeypatch.setenv("EDUMIND_ANIMATION_DISPATCH", "celery")

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await _clean(sessions)
            job = await _reserve(sessions)
            (delivery,) = await claim_dispatches(sessions, limit=1)
            lease = await claim_animation_job(sessions, message=delivery.message)
            assert await transition(sessions, lease.token, "starting")
            async with sessions() as db:

                async def unavailable():
                    raise ConnectionError("TEST_ONLY_COMMIT_UNAVAILABLE")

                monkeypatch.setattr(db, "commit", unavailable)
                with pytest.raises(ConnectionError):
                    await cancel_animation_job(
                        db,
                        owner_id=job.user_id,
                        job_id=job.id,
                        idempotency_key=uuid4().hex,
                    )
            async with sessions() as db:
                current = await db.get(AnimationJob, job.id)
                attempt = await db.get(AnimationJobAttempt, lease.token)
                box = await db.get(AnimationDispatchOutbox, delivery.outbox_id)
                assert current.status == "running" and current.lease_token == lease.token
                assert not current.cancel_requested and current.last_event_id == 2
                assert attempt.launch_state == "starting" and attempt.cleanup_requested_at is None
                assert box.state == "sending" and box.publisher_token == delivery.token
                assert (
                    await db.scalars(
                        select(AnimationJobEvent).where(
                            AnimationJobEvent.job_id == job.id,
                            AnimationJobEvent.event_type == "cancelled",
                        )
                    )
                ).all() == []
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_broker_send_failure_keeps_queued_and_never_emits_success(monkeypatch):
    monkeypatch.setenv("EDUMIND_ANIMATION_DISPATCH", "celery")

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await _clean(sessions)
            job = await _reserve(sessions)

            observed = []

            async def unavailable(claim):
                observed.append(claim.message.job_id)
                raise ConnectionError("TEST_ONLY_BROKER_UNAVAILABLE")

            # The return value counts processed deliveries, including failed sends.
            assert await publish_dispatch_batch(sessions, unavailable, limit=1) == 1
            assert observed == [job.id]
            async with sessions() as db:
                current = await db.get(AnimationJob, job.id)
                assert (
                    current.status == "queued" and current.attempt == 0 and current.media_id is None
                )
                events = (
                    await db.scalars(
                        select(AnimationJobEvent).where(
                            AnimationJobEvent.job_id == job.id,
                        )
                    )
                ).all()
                assert [e.event_type for e in events] == ["queued"]
                box = await db.scalar(
                    select(AnimationDispatchOutbox).where(
                        AnimationDispatchOutbox.job_id == job.id,
                    )
                )
                assert box.state == "pending" and box.error_code == "BROKER_UNAVAILABLE"
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "contract",
    [
        "test_concurrent_cancel_and_publish_commit_only_one_terminal",
        "test_cancelling_running_job_stops_its_container_within_ten_seconds",
    ],
)
def test_shared_cancel_publish_contract_with_celery_lease(contract, tmp_path, monkeypatch):
    from app.services.animation_worker import run_one_animation_job
    from tests import test_animation_job_api as api

    if contract.endswith("within_ten_seconds") and os.getenv("EDUMIND_DOCKER_TESTS") != "1":
        pytest.skip("actual Docker required")
    monkeypatch.setenv("EDUMIND_ANIMATION_DISPATCH", "celery")

    async def claim(sessions):
        async with sessions() as db:
            job = await db.scalar(
                select(AnimationJob).where(
                    AnimationJob.status == "queued",
                    AnimationJob.dispatch_backend == "celery",
                )
            )
            assert job is not None
            message = DispatchMessage(job.id, job.dispatch_epoch)
        return await claim_animation_job(sessions, message=message)

    async def run(sessions, *, cache):
        lease = await claim(sessions)
        assert lease is not None
        return await run_one_animation_job(sessions, cache=cache, lease=lease)

    monkeypatch.setattr(api, "claim_animation_job", claim)
    monkeypatch.setattr(api, "run_one_animation_job", run)
    getattr(api, contract)(tmp_path, monkeypatch)
