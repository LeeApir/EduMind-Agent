"""Real isolated PG outbox transactions/concurrency/loss recovery; no Provider calls."""

import asyncio
import os
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import ConfigurationError
from app.core.database import create_database_engine
from app.models.animation import AnimationDispatchOutbox, AnimationJob
from app.services.animation_jobs import AnimationIdempotencyConflict, reserve_animation_job
from app.services.animation_lifecycle import cancel_animation_job, retry_animation_job
from app.services.animation_worker import claim_animation_job
from app.services.durable_job_dispatch import (
    DispatchMessage,
    claim_dispatches,
    dispatch_backend,
    finish_dispatch,
    publish_dispatch_batch,
    reconcile_dispatches,
    route_queued_template_jobs,
)
from app.workers.animation_queue import create_queue_app
from tests.test_animation_job_persistence import _target
from tests.test_animation_worker import _clean

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pg = pytest.mark.skipif(not URL, reason="isolated PostgreSQL URL not set")


def test_fixed_transport_configuration(monkeypatch):
    monkeypatch.setenv("EDUMIND_ANIMATION_BROKER_URL", "redis://127.0.0.1:1/0")
    app = create_queue_app()
    assert app.conf.result_backend is None
    assert app.conf.task_ignore_result and not app.conf.task_store_errors_even_if_ignored
    assert app.conf.accept_content == ["json"]
    assert not app.conf.task_create_missing_queues and not app.conf.task_publish_retry
    assert not app.conf.worker_enable_remote_control and not app.conf.task_send_sent_event
    assert app.conf.broker_transport_options["visibility_timeout"] == 300
    assert list(app.conf.task_routes) == ["edumind.render_animation.v1"]
    app.close()
    monkeypatch.setenv("EDUMIND_ANIMATION_BROKER_URL", "amqp://private")
    with pytest.raises(ConfigurationError):
        create_queue_app()
    monkeypatch.delenv("EDUMIND_ANIMATION_DISPATCH", raising=False)
    assert dispatch_backend() == "pg_poll"
    monkeypatch.setenv("EDUMIND_ANIMATION_DISPATCH", "secret-value")
    with pytest.raises(ConfigurationError) as error:
        dispatch_backend()
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize(
    "alteration",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"dispatch_epoch": True},
        {"dispatch_epoch": 0},
        {"dispatch_epoch": 2147483648},
        {"dispatch_epoch": "1"},
        {"job_id": "not-uuid"},
        {"owner": "user"},
        {"api_key": "sensitive"},
        {"source": "command"},
        {"session": "cookie"},
        {"parameters": {}},
    ],
)
def test_message_rejects_extra_or_invalid_data(alteration):
    value = DispatchMessage(uuid4(), 1).payload()
    value.update(alteration)
    with pytest.raises(ValueError, match="INVALID_DISPATCH_MESSAGE"):
        DispatchMessage.parse(value)


def test_message_roundtrip():
    message = DispatchMessage(uuid4(), 1)
    assert DispatchMessage.parse(message.payload()) == message
    assert set(message.payload()) == {"schema_version", "job_id", "dispatch_epoch"}


async def reserve(sessions, *, backend="celery"):
    user, unit, scene = await _target(sessions)
    request = dict(
        owner_id=user.id,
        learning_unit_id=unit.id,
        scene_id=scene.id,
        scene_version=1,
        template_id="linked-list-insertion",
        template_version="1.0.0",
        parameters={"values": [1, 3], "index": 1, "value": 2},
        idempotency_key=uuid4().hex,
    )
    with patch.dict(os.environ, EDUMIND_ANIMATION_DISPATCH=backend):
        async with sessions() as db:
            receipt = await reserve_animation_job(db, **request)
    return receipt.job, request


async def rows(sessions, job_id):
    async with sessions() as db:
        return (
            await db.scalars(
                select(AnimationDispatchOutbox)
                .where(AnimationDispatchOutbox.job_id == job_id)
                .order_by(AnimationDispatchOutbox.dispatch_epoch)
            )
        ).all()


async def setup():
    engine = create_database_engine(URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await _clean(sessions)
    return engine, sessions


@pg
def test_transaction_idempotency_rollback_and_default_route(monkeypatch):
    async def exercise():
        engine, sessions = await setup()
        try:
            job, request = await reserve(sessions)
            assert job.dispatch_backend == "celery" and job.dispatch_epoch == 1
            assert len(await rows(sessions, job.id)) == 1

            async def replay():
                async with sessions() as db:
                    return await reserve_animation_job(db, **request)

            receipts = await asyncio.gather(replay(), replay())
            assert all(r.job.id == job.id and not r.created for r in receipts)
            assert len(await rows(sessions, job.id)) == 1
            async with sessions() as db:
                assert (await db.get(AnimationJob, job.id)).last_event_id == 1
                with pytest.raises(AnimationIdempotencyConflict):
                    await reserve_animation_job(
                        db, **{**request, "parameters": {"values": [1, 3], "index": 1, "value": 5}}
                    )
            pg_job, _ = await reserve(sessions, backend="pg_poll")
            assert not await rows(sessions, pg_job.id)
            with patch(
                "app.services.animation_jobs.enqueue_animation_job",
                side_effect=RuntimeError("rollback"),
            ):
                async with sessions() as db:
                    with pytest.raises(RuntimeError):
                        await reserve_animation_job(
                            db, **{**request, "idempotency_key": "rollback-key"}
                        )
            async with sessions() as db:
                assert not await db.scalar(
                    select(AnimationJob.id).where(AnimationJob.idempotency_key == "rollback-key")
                )
            # API caller death after commit changes nothing; fresh session discovers the outbox.
            stored = (await rows(sessions, job.id))[0]
            assert stored.state == "pending" and stored.transport_attempts == 0
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pg
def test_broker_failure_backoff_and_payload(monkeypatch):
    async def exercise():
        engine, sessions = await setup()
        try:
            job, _ = await reserve(sessions)
            calls = []

            async def unavailable(claim):
                calls.append(claim.message.payload())
                raise RuntimeError("secret broker URL")

            assert await publish_dispatch_batch(sessions, unavailable, limit=1) == 1
            assert calls == [DispatchMessage(job.id, 1).payload()]
            row = (await rows(sessions, job.id))[0]
            assert row.state == "pending" and row.error_code == "BROKER_UNAVAILABLE"
            async with sessions() as db:
                stored = await db.get(AnimationJob, job.id)
                assert (
                    stored.status == "queued" and stored.attempt == 0 and stored.last_event_id == 1
                )
                await db.execute(
                    update(AnimationDispatchOutbox)
                    .where(AnimationDispatchOutbox.id == row.id)
                    .values(next_attempt_at=func.clock_timestamp(), transport_attempts=10)
                )
                await db.commit()
            await publish_dispatch_batch(sessions, unavailable, limit=1)
            row = (await rows(sessions, job.id))[0]
            async with sessions() as db:
                now = await db.scalar(select(func.clock_timestamp()))
                assert 58 <= (row.next_attempt_at - now).total_seconds() <= 60
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pg
def test_duplicate_publish_claims_expired_token_and_sent_message_loss():
    async def exercise():
        engine, sessions = await setup()
        try:
            job, _ = await reserve(sessions)
            # Isolate due rows from other scenarios without deleting any Jobs.
            async with sessions() as db:
                await db.execute(
                    update(AnimationDispatchOutbox)
                    .where(
                        AnimationDispatchOutbox.job_id != job.id,
                        AnimationDispatchOutbox.state == "pending",
                    )
                    .values(next_attempt_at=func.clock_timestamp() + timedelta(days=1))
                )
                await db.commit()
            left, right = await asyncio.gather(
                claim_dispatches(sessions, limit=1), claim_dispatches(sessions, limit=1)
            )
            claims = left + right
            assert len(claims) == 1
            first = claims[0]
            async with sessions() as db:
                await db.execute(
                    update(AnimationDispatchOutbox)
                    .where(AnimationDispatchOutbox.id == first.outbox_id)
                    .values(publisher_expires_at=func.clock_timestamp() - timedelta(seconds=1))
                )
                await db.commit()
            assert not await finish_dispatch(sessions, first, sent=True)
            await reconcile_dispatches(sessions)
            second = (await claim_dispatches(sessions, limit=1))[0]
            assert second.message == first.message and second.token != first.token
            assert await finish_dispatch(sessions, second, sent=True)
            async with sessions() as db:
                await db.execute(
                    update(AnimationDispatchOutbox)
                    .where(AnimationDispatchOutbox.id == second.outbox_id)
                    .values(last_sent_at=func.clock_timestamp() - timedelta(seconds=61))
                )
                await db.commit()
            # Simulate broker flush: no message receipt is required to recover a sent row.
            await reconcile_dispatches(sessions)
            third = (await claim_dispatches(sessions, limit=1))[0]
            assert third.message.job_id == job.id and third.outbox_id == first.outbox_id
            assert await finish_dispatch(sessions, third, sent=True)
            async with sessions() as db:
                stored = await db.get(AnimationJob, job.id)
                assert (
                    stored.status == "queued" and stored.attempt == 0 and stored.last_event_id == 1
                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pg
def test_missing_outbox_live_publisher_cancel_retry_and_routing():
    async def exercise():
        engine, sessions = await setup()
        try:
            job, request = await reserve(sessions)
            async with sessions() as db:
                await db.execute(
                    delete(AnimationDispatchOutbox).where(AnimationDispatchOutbox.job_id == job.id)
                )
                await db.commit()
            await reconcile_dispatches(sessions)
            assert len(await rows(sessions, job.id)) == 1
            assert await route_queued_template_jobs(sessions, (job.id,), backend="pg_poll") == 1
            assert (await rows(sessions, job.id))[0].state == "obsolete"
            assert await route_queued_template_jobs(sessions, (job.id,), backend="celery") == 1
            outbox = await rows(sessions, job.id)
            assert [r.dispatch_epoch for r in outbox] == [1, 3]
            async with sessions() as db:
                await db.execute(
                    update(AnimationDispatchOutbox)
                    .where(
                        AnimationDispatchOutbox.job_id != job.id,
                        AnimationDispatchOutbox.state == "pending",
                    )
                    .values(next_attempt_at=func.clock_timestamp() + timedelta(days=1))
                )
                await db.commit()
            claim = (await claim_dispatches(sessions, limit=1))[0]
            await reconcile_dispatches(sessions)
            assert (await rows(sessions, job.id))[-1].publisher_token == claim.token
            async with sessions() as db:
                await cancel_animation_job(
                    db, owner_id=request["owner_id"], job_id=job.id, idempotency_key=uuid4().hex
                )
            await reconcile_dispatches(sessions)
            assert all(r.state == "obsolete" for r in await rows(sessions, job.id))
            assert not await finish_dispatch(sessions, claim, sent=True)
            with patch.dict(os.environ, EDUMIND_ANIMATION_DISPATCH="celery"):
                async with sessions() as db:
                    new, created = await retry_animation_job(
                        db,
                        owner_id=request["owner_id"],
                        job_id=job.id,
                        idempotency_key="new-retry-key",
                    )
                    assert created and new.id != job.id and new.retry_of == job.id
                assert len(await rows(sessions, new.id)) == 1
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pg
def test_pg_worker_cannot_steal_celery_job():
    async def exercise():
        engine, sessions = await setup()
        try:
            job, _ = await reserve(sessions)
            async with sessions() as db:
                await db.execute(
                    update(AnimationJob)
                    .where(
                        AnimationJob.dispatch_backend == "pg_poll", AnimationJob.status == "queued"
                    )
                    .values(status="cancelled", cancel_requested=True)
                )
                await db.commit()
            assert await claim_animation_job(sessions) is None
            async with sessions() as db:
                stored = await db.get(AnimationJob, job.id)
                assert stored.status == "queued" and stored.attempt == 0
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_transport_child_timeout_and_cancellation_kill_without_sensitive_env(monkeypatch):
    from app.services.durable_job_dispatch import DispatchClaim
    from app.workers.animation_queue import send_dispatch

    async def exercise():
        seen = []

        class Process:
            returncode = None
            killed = False

            async def wait(self):
                if not self.killed:
                    await asyncio.Future()
                self.returncode = -9
                return -9

            def kill(self):
                self.killed = True

        process = Process()

        async def create(*args, **kwargs):
            seen.append((args, kwargs))
            return process

        monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "synthetic-do-not-inherit")
        monkeypatch.setenv("EDUMIND_CREDENTIAL_KEK", "synthetic-do-not-inherit")
        monkeypatch.setenv("EDUMIND_DATABASE_URL", "synthetic-do-not-inherit")
        monkeypatch.setenv("EDUMIND_ANIMATION_BROKER_URL", "redis://private")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
        claim = DispatchClaim(uuid4(), uuid4(), DispatchMessage(uuid4(), 1))
        task = asyncio.create_task(send_dispatch(claim))
        while not seen:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.killed
        args, kwargs = seen[0]
        assert "synthetic-do-not-inherit" not in str(kwargs["env"])
        assert set(kwargs["env"]) <= {"PATH", "SYSTEMROOT", "EDUMIND_ANIMATION_BROKER_URL"}
        assert set(__import__("json").loads(args[-1])) == {
            "schema_version",
            "job_id",
            "dispatch_epoch",
        }

    asyncio.run(exercise())


@pg
def test_migration_backfill_and_active_job_downgrade_guard():
    import importlib.util
    from pathlib import Path

    from sqlalchemy import text

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    spec = importlib.util.spec_from_file_location(
        "queue_migration", Path(__file__).parents[1] / "alembic/versions/0021_animation_dispatch.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def exercise():
        engine, sessions = await setup()
        try:
            job, _ = await reserve(sessions)
            async with engine.connect() as connection:
                transaction = await connection.begin()

                def guarded(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        with pytest.raises(RuntimeError, match="ACTIVE_CELERY_JOBS"):
                            module.downgrade()

                await connection.run_sync(guarded)
                await transaction.rollback()
            assert await route_queued_template_jobs(sessions, (job.id,), backend="pg_poll") == 1
            async with engine.connect() as connection:
                transaction = await connection.begin()

                def roundtrip(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        module.downgrade()
                        module.upgrade()
                    value = sync.execute(
                        text(
                            "SELECT dispatch_backend, dispatch_epoch "
                            "FROM animation_jobs WHERE id=:id"
                        ),
                        {"id": job.id},
                    ).one()
                    assert value == ("pg_poll", 1)

                await connection.run_sync(roundtrip)
                await transaction.rollback()
            async with sessions() as db:
                stored = await db.get(AnimationJob, job.id)
                assert stored.dispatch_epoch == 2 and stored.last_event_id == 1
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pg
def test_cache_hit_creates_no_outbox(tmp_path):
    from app.services.animation_cache import AnimationCache
    from tests.test_animation_worker import _fake_renderer

    async def exercise():
        engine, sessions = await setup()
        try:
            user, unit, scene = await _target(sessions)
            parameters = {"values": [1, 3, 5], "index": 1, "value": 2}
            cache = AnimationCache(tmp_path, renderer=_fake_renderer)
            await asyncio.to_thread(cache.resolve, "linked-list-insertion", parameters)
            with patch.dict(os.environ, EDUMIND_ANIMATION_DISPATCH="celery"):
                async with sessions() as db:
                    result = await reserve_animation_job(
                        db,
                        owner_id=user.id,
                        learning_unit_id=unit.id,
                        scene_id=scene.id,
                        scene_version=1,
                        template_id="linked-list-insertion",
                        template_version="1.0.0",
                        parameters=parameters,
                        idempotency_key=uuid4().hex,
                        cache=cache,
                    )
            assert result.job.status == "succeeded" and result.job.attempt == 0
            assert not await rows(sessions, result.job.id)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(
    not URL or not os.getenv("EDUMIND_TEST_QUEUE_BROKER"), reason="isolated PG/Redis not set"
)
def test_actual_fixed_celery_publish_and_acl_broker_failure_recovery(monkeypatch):
    import base64
    import json
    import time

    from redis import Redis
    from redis.exceptions import ResponseError

    from app.workers.animation_queue import send_dispatch

    async def exercise():
        engine, sessions = await setup()
        broker = Redis.from_url(os.environ["EDUMIND_TEST_QUEUE_BROKER"])
        queue_key = "edumind.animation:edumind.animation.v1"
        try:
            assert broker.ping()
            broker.delete(queue_key)
            with pytest.raises(ResponseError):
                broker.flushdb()
            with pytest.raises(ResponseError):
                broker.set("outside-authorized-prefix", "forbidden")
            job, _ = await reserve(sessions)
            monkeypatch.setenv(
                "EDUMIND_ANIMATION_BROKER_URL", os.environ["EDUMIND_TEST_QUEUE_BROKER"]
            )
            assert await publish_dispatch_batch(sessions, send_dispatch, limit=1) == 1
            assert (await rows(sessions, job.id))[0].state == "sent"
            assert broker.llen(queue_key) == 1
            transported = json.loads(broker.lpop(queue_key))
            assert transported["headers"]["task"] == "edumind.render_animation.v1"
            assert transported["content-type"] == "application/json"
            arguments, kwargs, extra = json.loads(base64.b64decode(transported["body"]))
            assert arguments == [DispatchMessage(job.id, 1).payload()] and kwargs == {}
            assert all(
                extra.get(key) is None for key in ("callbacks", "errbacks", "chain", "chord")
            )
            assert "synthetic_queue_test_only_password" not in str(transported)
            # Remove the actual sent message before any consumer: reconciliation recovers it.
            async with sessions() as db:
                await db.execute(
                    update(AnimationDispatchOutbox)
                    .where(AnimationDispatchOutbox.job_id == job.id)
                    .values(last_sent_at=func.clock_timestamp() - timedelta(seconds=61))
                )
                await db.commit()
            await reconcile_dispatches(sessions)
            monkeypatch.setenv("EDUMIND_ANIMATION_BROKER_URL", "redis://127.0.0.1:1/0")
            started = time.monotonic()
            assert await publish_dispatch_batch(sessions, send_dispatch, limit=1) == 1
            assert time.monotonic() - started < 5
            row = (await rows(sessions, job.id))[0]
            assert row.state == "pending" and row.error_code == "BROKER_UNAVAILABLE"
            async with sessions() as db:
                stored = await db.get(AnimationJob, job.id)
                assert stored.status == "queued" and stored.attempt == 0
                await db.execute(
                    update(AnimationDispatchOutbox)
                    .where(AnimationDispatchOutbox.id == row.id)
                    .values(next_attempt_at=func.clock_timestamp())
                )
                await db.commit()
            monkeypatch.setenv(
                "EDUMIND_ANIMATION_BROKER_URL", os.environ["EDUMIND_TEST_QUEUE_BROKER"]
            )
            assert await publish_dispatch_batch(sessions, send_dispatch, limit=1) == 1
            repeated = json.loads(broker.lpop(queue_key))
            assert repeated["headers"]["id"] == transported["headers"]["id"]
            assert json.loads(base64.b64decode(repeated["body"]))[0] == arguments
        finally:
            broker.close()
            await engine.dispose()

    asyncio.run(exercise())
