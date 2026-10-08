"""Persistent epoch claims, independent cleanup, and real isolated Worker crash recovery."""

import asyncio
import os
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.animation import AnimationJob, AnimationJobAttempt, AnimationResourceBinding
from app.services.animation_attempts import launch_valid, transition
from app.services.animation_cache import AnimationCache
from app.services.animation_host import RenderHost, cleanup_once
from app.services.animation_worker import (
    claim_animation_job,
    heartbeat_animation_job,
    publish_animation_job,
    reclaim_expired_animation_jobs,
)
from app.services.durable_job_dispatch import DispatchMessage, route_queued_template_jobs
from tests.test_animation_worker import _clean, _fake_renderer, _reserve

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pg = pytest.mark.skipif(not URL, reason="isolated PG required")
docker = pytest.mark.skipif(
    not URL or os.getenv("EDUMIND_DOCKER_TESTS") != "1", reason="isolated PG/Docker required"
)


async def setup():
    engine = create_database_engine(URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    await _clean(sessions)
    job = await _reserve(sessions)
    await route_queued_template_jobs(sessions, (job.id,), backend="celery")
    async with sessions() as db:
        job = await db.get(AnimationJob, job.id)
    return engine, sessions, job


@pg
def test_duplicate_old_epoch_pg_poll_and_bounded_recovery(tmp_path):
    async def exercise():
        engine, sessions, job = await setup()
        try:
            assert await claim_animation_job(sessions) is None
            assert await claim_animation_job(sessions, message=DispatchMessage(job.id, 1)) is None
            claims = await asyncio.gather(
                *[
                    claim_animation_job(
                        sessions, message=DispatchMessage(job.id, job.dispatch_epoch)
                    )
                    for _ in range(2)
                ]
            )
            leases = [lease for lease in claims if lease is not None]
            assert len(leases) == 1
            old = leases[0]
            assert old.attempt == 1
            async with sessions() as db:
                attempt = await db.get(AnimationJobAttempt, old.token)
                assert attempt.launch_state == "prepared"
            assert await transition(sessions, old.token, "starting")
            assert await launch_valid(sessions, old.token)
            assert await heartbeat_animation_job(sessions, old)
            async with sessions() as db:
                await db.execute(
                    update(AnimationJob)
                    .where(AnimationJob.id == job.id)
                    .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
                )
                await db.commit()
            assert not await heartbeat_animation_job(sessions, old)
            assert await reclaim_expired_animation_jobs(sessions) == 1
            assert not await launch_valid(sessions, old.token)
            assert not await transition(sessions, old.token, "started")
            async with sessions() as db:
                current = await db.get(AnimationJob, job.id)
                attempt = await db.get(AnimationJobAttempt, old.token)
                assert (
                    current.status == "queued" and current.dispatch_epoch == old.dispatch_epoch + 1
                )
                assert attempt.launch_state == "cleanup_requested"
            assert (
                await claim_animation_job(
                    sessions, message=DispatchMessage(job.id, old.dispatch_epoch)
                )
                is None
            )
            new = await claim_animation_job(
                sessions, message=DispatchMessage(job.id, current.dispatch_epoch)
            )
            assert new.token != old.token and new.attempt == 2
            cache = AnimationCache(tmp_path, renderer=_fake_renderer)
            media = cache.resolve(new.template_id, new.parameters)
            assert not await publish_animation_job(sessions, old, cache=cache, media=media)
            assert await publish_animation_job(sessions, new, cache=cache, media=media)
            assert not await publish_animation_job(sessions, new, cache=cache, media=media)
            async with sessions() as db:
                bindings = (
                    await db.scalars(
                        select(AnimationResourceBinding).where(
                            AnimationResourceBinding.job_id == job.id
                        )
                    )
                ).all()
                assert len(bindings) == 1
            assert (
                await claim_animation_job(
                    sessions, message=DispatchMessage(job.id, current.dispatch_epoch)
                )
                is None
            )
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pg
def test_second_expiry_terminal_and_cleanup_intent():
    async def exercise():
        engine, sessions, job = await setup()
        try:
            epoch = job.dispatch_epoch
            for expected in (1, 2):
                lease = await claim_animation_job(sessions, message=DispatchMessage(job.id, epoch))
                assert lease.attempt == expected
                async with sessions() as db:
                    await db.execute(
                        update(AnimationJob)
                        .where(AnimationJob.id == job.id)
                        .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
                    )
                    await db.commit()
                assert await reclaim_expired_animation_jobs(sessions) == 1
                epoch += 1
            async with sessions() as db:
                result = await db.get(AnimationJob, job.id)
                assert result.status == "failed" and result.error_code == "RENDER_INTERRUPTED"
                attempts = (
                    await db.scalars(
                        select(AnimationJobAttempt).where(AnimationJobAttempt.job_id == job.id)
                    )
                ).all()
                assert len(attempts) == 2 and all(a.cleanup_requested_at for a in attempts)
            assert await reclaim_expired_animation_jobs(sessions) == 0
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@docker
def test_absent_then_late_container_is_recleaned_under_persistent_token(tmp_path):
    import subprocess
    import time

    from app.services.animation_renderer import IMAGE

    async def exercise():
        engine, sessions, job = await setup()
        lease = None
        try:
            lease = await claim_animation_job(
                sessions, message=DispatchMessage(job.id, job.dispatch_epoch)
            )
            assert await transition(sessions, lease.token, "starting")
            async with sessions() as db:
                await db.execute(
                    update(AnimationJob)
                    .where(AnimationJob.id == job.id)
                    .values(
                        status="cancelled",
                        cancel_requested=True,
                        lease_token=None,
                        lease_expires_at=None,
                    )
                )
                await db.commit()
            controller = RenderHost(sessions, lease.token, asyncio.get_running_loop())
            assert await asyncio.to_thread(controller.stop)
            async with sessions() as db:
                assert (await db.get(AnimationJobAttempt, lease.token)).launch_state == "absent"
            # Simulate a delayed successful Docker RPC after absence was confirmed.
            launch = await asyncio.to_thread(
                subprocess.run,
                [
                    "docker",
                    "run",
                    "-d",
                    "--rm",
                    "--name",
                    lease.container_name,
                    "--network",
                    "none",
                    "--read-only",
                    "--user",
                    "10001:10001",
                    IMAGE,
                    "python",
                    "-c",
                    "import time; time.sleep(60)",
                ],
                capture_output=True,
                timeout=5,
            )
            assert launch.returncode == 0
            started = time.monotonic()
            assert await cleanup_once(sessions) == 1
            assert time.monotonic() - started < 10
            assert not await transition(sessions, lease.token, "started")
            async with sessions() as db:
                row = await db.get(AnimationJobAttempt, lease.token)
                assert row.launch_state == "absent" and row.cleanup_done_at is not None
                assert (await db.get(AnimationJob, job.id)).status == "cancelled"
        finally:
            if lease:
                await asyncio.to_thread(
                    subprocess.run,
                    ["docker", "rm", "-f", lease.container_name],
                    capture_output=True,
                    timeout=5,
                )
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(
    not URL
    or os.getenv("EDUMIND_DOCKER_TESTS") != "1"
    or not os.getenv("EDUMIND_TEST_QUEUE_BROKER"),
    reason="isolated PG/Redis/Docker required",
)
@pytest.mark.parametrize("pool,death", [("solo", "parent"), ("prefork", "child")])
def test_real_worker_parent_death_broker_restart_and_single_publication(tmp_path, pool, death):
    import signal
    import subprocess
    import sys
    import time

    from app.services.animation_host import inventory
    from app.services.durable_job_dispatch import publish_dispatch_batch, reconcile_dispatches
    from app.workers.animation_queue import send_dispatch

    async def exercise():
        engine, sessions, job = await setup()
        backend = Path(__file__).parents[1]
        environment = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL"))
        }
        environment.update(
            EDUMIND_DATABASE_URL=URL,
            EDUMIND_ANIMATION_BROKER_URL=os.environ["EDUMIND_TEST_QUEUE_BROKER"],
            EDUMIND_ANIMATION_CACHE_ROOT=str(tmp_path / "cache"),
            EDUMIND_RENDER_LOCK_ROOT=str(tmp_path / "host-locks"),
        )
        processes = []
        output = (tmp_path / "worker.log").open("wb")
        controller_log = (tmp_path / "controller.log").open("wb")

        def launch():
            process = subprocess.Popen(
                [sys.executable, "-m", "app.workers.animation_consumer", "--pool=" + pool],
                cwd=backend,
                env=environment,
                stdout=output,
                stderr=output,
                start_new_session=True,
            )
            processes.append(process)
            return process

        async def wait_for(predicate, seconds=30):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                value = await predicate()
                if value:
                    return value
                await asyncio.sleep(0.1)
            raise AssertionError("Actual isolated Worker state timed out")

        async def active():
            async with sessions() as db:
                current = await db.get(AnimationJob, job.id)
                if current.status != "running":
                    return None
                row = await db.get(AnimationJobAttempt, current.lease_token)
                return current if row and row.launch_state == "started" else None

        async def succeeded():
            async with sessions() as db:
                current = await db.get(AnimationJob, job.id)
                assert current.status != "failed", current.error_code
                return current if current.status == "succeeded" else None

        try:
            # Dedicated known container only; no business Redis restart.
            controller = subprocess.Popen(
                [sys.executable, "scripts/run_animation_host_controller.py"],
                cwd=backend,
                env=environment,
                stdout=controller_log,
                stderr=controller_log,
                start_new_session=True,
            )
            processes.append(controller)
            first = launch()
            with pytest.MonkeyPatch.context() as patcher:
                patcher.setenv(
                    "EDUMIND_ANIMATION_BROKER_URL", environment["EDUMIND_ANIMATION_BROKER_URL"]
                )
                assert await publish_dispatch_batch(sessions, send_dispatch, limit=1) == 1
            old = await wait_for(active)
            killed_at = time.monotonic()
            if death == "parent":
                os.killpg(first.pid, signal.SIGKILL)
                await asyncio.to_thread(first.wait, 5)
            else:
                children = subprocess.run(
                    ["ps", "-axo", "pid=,ppid=,command="],
                    capture_output=True,
                    check=True,
                    timeout=2,
                )
                pids = [
                    int(line.split()[0])
                    for line in children.stdout.decode().splitlines()
                    if int(line.split()[1]) == first.pid
                    and "resource_tracker" not in line
                    and "semaphore_tracker" not in line
                ]
                assert len(pids) == 1
                os.kill(pids[0], signal.SIGKILL)
                assert first.poll() is None
            restart = await asyncio.to_thread(
                subprocess.run,
                ["docker", "restart", "edumind-phase1-queue-test-redis"],
                capture_output=True,
                timeout=15,
            )
            assert restart.returncode == 0

            async def recovered():
                async with sessions() as db:
                    current = await db.get(AnimationJob, job.id)
                    return (
                        current
                        if current.status == "queued"
                        and current.dispatch_epoch > old.dispatch_epoch
                        else None
                    )

            current = await wait_for(recovered, 40)
            assert time.monotonic() - killed_at < 40

            async def old_absent():
                return f"edumind-render-{old.lease_token.hex}" not in await asyncio.to_thread(
                    inventory
                )

            await wait_for(old_absent, 10)
            # Reaper emitted epoch2 outbox; publisher restores transport after restart.
            await reconcile_dispatches(sessions)
            second = launch()
            with pytest.MonkeyPatch.context() as patcher:
                patcher.setenv(
                    "EDUMIND_ANIMATION_BROKER_URL", environment["EDUMIND_ANIMATION_BROKER_URL"]
                )
                assert await publish_dispatch_batch(sessions, send_dispatch, limit=1) == 1
            result = await wait_for(succeeded, 45)
            assert result.attempt == 2 and result.dispatch_epoch == current.dispatch_epoch
            assert second.poll() is None and controller.poll() is None
            async with sessions() as db:
                rows = (
                    await db.scalars(
                        select(AnimationResourceBinding).where(
                            AnimationResourceBinding.job_id == job.id
                        )
                    )
                ).all()
                assert len(rows) == 1 and rows[0].user_id == job.user_id
                attempts = (
                    await db.scalars(
                        select(AnimationJobAttempt).where(AnimationJobAttempt.job_id == job.id)
                    )
                ).all()
                assert len(attempts) == 2
            assert (
                await claim_animation_job(
                    sessions, message=DispatchMessage(job.id, old.dispatch_epoch)
                )
                is None
            )
        finally:
            for process in processes:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        await asyncio.to_thread(process.wait, 5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        await asyncio.to_thread(process.wait, 5)
            output.close()
            controller_log.close()
            await cleanup_once(sessions)
            await engine.dispose()

    asyncio.run(exercise())


@pg
def test_attempt_migration_backfills_running_token_and_refuses_active_downgrade():
    import subprocess
    import sys

    async def exercise():
        engine, sessions, job = await setup()
        backend = Path(__file__).parents[1]
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL"))
        }
        env["EDUMIND_DATABASE_URL"] = URL

        async def migrate(target, direction):
            return await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "alembic", direction, target],
                cwd=backend,
                env=env,
                capture_output=True,
                timeout=15,
            )

        try:
            lease = await claim_animation_job(
                sessions, message=DispatchMessage(job.id, job.dispatch_epoch)
            )
            rejected = await migrate("0021_animation_dispatch", "downgrade")
            assert rejected.returncode != 0
            assert b"ACTIVE_RENDER_LEASES_REQUIRE_DRAIN" in rejected.stderr
            async with sessions() as db:
                assert await db.get(AnimationJobAttempt, lease.token) is not None
                await db.execute(
                    update(AnimationJob)
                    .where(AnimationJob.id == job.id)
                    .values(
                        status="queued",
                        lease_token=None,
                        lease_expires_at=None,
                    )
                )
                await db.commit()
            assert (await migrate("0021_animation_dispatch", "downgrade")).returncode == 0
            async with sessions() as db:
                await db.execute(
                    update(AnimationJob)
                    .where(AnimationJob.id == job.id)
                    .values(
                        status="running",
                        lease_token=lease.token,
                        lease_expires_at=func.clock_timestamp() + timedelta(seconds=30),
                    )
                )
                await db.commit()
            assert (await migrate("head", "upgrade")).returncode == 0
            async with sessions() as db:
                attempt = await db.get(AnimationJobAttempt, lease.token)
                assert attempt.job_id == job.id and attempt.attempt == 1
                assert attempt.dispatch_epoch == lease.dispatch_epoch
                assert attempt.dispatch_backend == "celery" and attempt.launch_state == "starting"
            assert await launch_valid(sessions, lease.token)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_consumer_registers_only_fixed_task_and_rejects_invalid_message(monkeypatch):
    from app.services.durable_job_dispatch import TASK_NAME
    from app.workers.animation_consumer import build_consumer, consume

    monkeypatch.setenv("EDUMIND_ANIMATION_BROKER_URL", "redis://localhost:1/0")
    app = build_consumer()
    try:
        assert set(app.tasks) == {TASK_NAME}
        assert app.backend.__class__.__name__ == "DisabledBackend"
        assert app.conf.accept_content == ["json"]
        assert app.conf.task_acks_late and app.conf.task_reject_on_worker_lost
        assert app.conf.worker_prefetch_multiplier == 1
    finally:
        app.close()
    monkeypatch.setattr(
        "app.workers.animation_consumer.create_database_engine",
        lambda: pytest.fail("invalid message must not reach PG or render"),
    )
    asyncio.run(consume({"schema_version": 1, "job_id": "invalid", "dispatch_epoch": 1}))


@docker
def test_launch_confirmation_loss_cleans_actual_container_within_ten_seconds(monkeypatch):
    import subprocess
    import time

    from app.services import animation_host
    from app.services.animation_renderer import IMAGE

    async def exercise():
        engine, sessions, job = await setup()
        lease = await claim_animation_job(
            sessions, message=DispatchMessage(job.id, job.dispatch_epoch)
        )
        controller = RenderHost(sessions, lease.token, asyncio.get_running_loop())
        original = animation_host._docker
        launched = []

        def lose_confirmation(command, **kwargs):
            result = original(command, **kwargs)
            if command[0] == "run":
                assert result.returncode == 0
                launched.append(True)
                raise subprocess.TimeoutExpired("docker", 3)
            return result

        monkeypatch.setattr(animation_host, "_docker", lose_confirmation)
        try:
            started = time.monotonic()
            with pytest.raises(subprocess.TimeoutExpired):
                await asyncio.to_thread(
                    controller.launch,
                    [
                        "run",
                        "-d",
                        "--rm",
                        "--name",
                        lease.container_name,
                        "--network",
                        "none",
                        "--read-only",
                        "--user",
                        "10001:10001",
                        IMAGE,
                        "python",
                        "-c",
                        "import time; time.sleep(60)",
                    ],
                )
            assert launched == [True]
            assert lease.container_name not in await asyncio.to_thread(animation_host.inventory)
            assert time.monotonic() - started < 10
            async with sessions() as db:
                attempt = await db.get(AnimationJobAttempt, lease.token)
                assert attempt.launch_state == "absent" and attempt.cleanup_done_at is not None
            assert not await transition(sessions, lease.token, "started")
        finally:
            await asyncio.to_thread(controller.stop)
            await engine.dispose()

    asyncio.run(exercise())
