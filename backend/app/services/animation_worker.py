"""Separate PostgreSQL-leased worker for reviewed animation rendering and publication."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.animation import AnimationJob
from app.services.animation_attempts import record_attempt, request_cleanup
from app.services.animation_cache import AnimationCache, CachedAnimation
from app.services.animation_host import RenderHost
from app.services.animation_job_qualification import animation_job_approved
from app.services.animation_jobs import append_animation_event
from app.services.animation_publication import bind_media, reviewed_media_row
from app.services.animation_renderer import RenderError
from app.services.durable_job_dispatch import DispatchMessage, enqueue_animation_job

LEASE_SECONDS = 30
HEARTBEAT_SECONDS = 10
CANCEL_POLL_SECONDS = 1
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobLease:
    job_id: UUID
    owner_id: UUID
    attempt: int
    token: UUID
    template_id: str | None
    parameters: dict[str, object]
    dispatch_backend: str = "pg_poll"
    dispatch_epoch: int = 1

    @property
    def container_name(self) -> str:
        return f"edumind-render-{self.token.hex}"


async def claim_animation_job(
    sessions: async_sessionmaker[AsyncSession],
    *,
    message: DispatchMessage | None = None,
) -> JobLease | None:
    """SKIP LOCKED keeps each claim short and allows independent workers."""
    async with sessions() as db:
        job = await db.scalar(
            select(AnimationJob)
            .where(
                AnimationJob.dispatch_backend == ("celery" if message else "pg_poll"),
                AnimationJob.id == message.job_id if message else true(),
                AnimationJob.dispatch_epoch == message.dispatch_epoch if message else true(),
                AnimationJob.status == "queued",
                AnimationJob.attempt < 2,
                AnimationJob.cancel_requested.is_(False),
            )
            .order_by(AnimationJob.created_at, AnimationJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            await db.rollback()
            return None
        if not await animation_job_approved(db, job, lock=True):
            job.status, job.error_code = "failed", "ANIMATION_TARGET_UNAVAILABLE"
            await append_animation_event(
                db,
                owner_id=job.user_id,
                job_id=job.id,
                event_type="failed",
                payload={"stage": "failed", "code": job.error_code},
            )
            await db.commit()
            return None
        db_now = await db.scalar(select(func.clock_timestamp()))
        assert isinstance(db_now, datetime)
        token = uuid4()
        job.status = "running"
        job.attempt += 1
        job.lease_token = token
        job.lease_expires_at = db_now + timedelta(seconds=LEASE_SECONDS)
        job.progress = 0.05
        record_attempt(db, job)
        await append_animation_event(
            db,
            owner_id=job.user_id,
            job_id=job.id,
            event_type="running",
            payload={"stage": "rendering", "progress": 0.05, "attempt": job.attempt},
        )
        lease = JobLease(
            job.id,
            job.user_id,
            job.attempt,
            token,
            job.template_id,
            dict(job.parameters),
            job.dispatch_backend,
            job.dispatch_epoch,
        )
        await db.commit()
        return lease


async def heartbeat_animation_job(
    sessions: async_sessionmaker[AsyncSession],
    lease: JobLease,
) -> bool:
    """An expired or replaced token cannot renew, even before the reaper runs."""
    async with sessions() as db:
        result = await db.execute(
            update(AnimationJob)
            .where(
                AnimationJob.id == lease.job_id,
                AnimationJob.user_id == lease.owner_id,
                AnimationJob.status == "running",
                AnimationJob.dispatch_backend == lease.dispatch_backend,
                AnimationJob.dispatch_epoch == lease.dispatch_epoch,
                AnimationJob.attempt == lease.attempt,
                AnimationJob.lease_token == lease.token,
                AnimationJob.lease_expires_at > func.clock_timestamp(),
                AnimationJob.cancel_requested.is_(False),
            )
            .values(lease_expires_at=func.clock_timestamp() + timedelta(seconds=LEASE_SECONDS))
        )
        await db.commit()
        return result.rowcount == 1


async def _locked_current_job(db: AsyncSession, lease: JobLease) -> AnimationJob | None:
    return cast(
        AnimationJob | None,
        await db.scalar(
            select(AnimationJob)
            .where(
                AnimationJob.id == lease.job_id,
                AnimationJob.user_id == lease.owner_id,
                AnimationJob.status == "running",
                AnimationJob.dispatch_backend == lease.dispatch_backend,
                AnimationJob.dispatch_epoch == lease.dispatch_epoch,
                AnimationJob.attempt == lease.attempt,
                AnimationJob.lease_token == lease.token,
                AnimationJob.lease_expires_at > func.clock_timestamp(),
                AnimationJob.cancel_requested.is_(False),
            )
            .with_for_update()
        ),
    )


async def report_animation_progress(
    sessions: async_sessionmaker[AsyncSession],
    lease: JobLease,
    *,
    stage: str,
    progress: float,
) -> bool:
    async with sessions() as db:
        job = await _locked_current_job(db, lease)
        if job is None:
            await db.rollback()
            return False
        if progress < job.progress or progress >= 1:
            raise ValueError("invalid animation progress")
        job.progress = progress
        await append_animation_event(
            db,
            owner_id=lease.owner_id,
            job_id=lease.job_id,
            event_type="progress",
            payload={"stage": stage, "progress": progress},
        )
        await db.commit()
        return True


async def fail_animation_job(
    sessions: async_sessionmaker[AsyncSession],
    lease: JobLease,
    *,
    code: str,
) -> bool:
    async with sessions() as db:
        job = await _locked_current_job(db, lease)
        if job is None:
            return False
        await request_cleanup(db, job)
        job.status, job.error_code = "failed", code
        job.lease_token = job.lease_expires_at = None
        await append_animation_event(
            db,
            owner_id=lease.owner_id,
            job_id=lease.job_id,
            event_type="failed",
            payload={"stage": "failed", "code": code},
        )
        await db.commit()
        return True


async def reclaim_expired_animation_jobs(
    sessions: async_sessionmaker[AsyncSession],
    *,
    limit: int = 20,
) -> int:
    """On restart, retry once; never turn a missing process into an immediate GET failure."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("INVALID_RECOVERY_BATCH")
    async with sessions() as db:
        jobs = (
            await db.scalars(
                select(AnimationJob)
                .where(
                    AnimationJob.status == "running",
                    AnimationJob.lease_expires_at <= func.clock_timestamp(),
                )
                .order_by(AnimationJob.lease_expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for job in jobs:
            if job.render_kind == "dsl":
                from app.services.animation_dsl_failure import settle_dsl_failure

                await settle_dsl_failure(db, job, code="RENDER_INTERRUPTED")
                continue
            await request_cleanup(db, job)
            job.lease_token = None
            job.lease_expires_at = None
            if job.attempt < 2 and not job.cancel_requested:
                job.status = "queued"
                job.progress = 0.0
                job.dispatch_epoch += 1
                enqueue_animation_job(db, job)
                event_type = "recovered"
                payload: dict[str, object] = {"stage": "queued", "attempt": job.attempt}
            else:
                job.status = "failed"
                job.error_code = "RENDER_INTERRUPTED"
                event_type = "failed"
                payload = {"stage": "failed", "code": "RENDER_INTERRUPTED"}
            await append_animation_event(
                db,
                owner_id=job.user_id,
                job_id=job.id,
                event_type=event_type,
                payload=payload,
            )
        await db.commit()
        return len(jobs)


async def publish_animation_job(
    sessions: async_sessionmaker[AsyncSession],
    lease: JobLease,
    *,
    cache: AnimationCache,
    media: CachedAnimation,
) -> bool:
    """Current lease alone may bind verified shared bytes to this owner and scene."""
    async with sessions() as db:
        job = await _locked_current_job(db, lease)
        if job is None:
            await db.rollback()
            return False
        if job.render_kind != "template" or not await animation_job_approved(db, job, lock=True):
            await db.rollback()
            await fail_animation_job(sessions, lease, code="ANIMATION_TARGET_UNAVAILABLE")
            return False
        if media.cache_key != job.cache_key or media.template_version != job.template_version:
            await db.rollback()
            await fail_animation_job(sessions, lease, code="TEMPLATE_VERSION_CHANGED")
            return False
        if not cache.validate(media, job.parameters):
            await db.rollback()
            await fail_animation_job(sessions, lease, code="MEDIA_INVALID")
            return False
        record = await reviewed_media_row(db, job, media)
        if record is None:
            await db.rollback()
            await fail_animation_job(sessions, lease, code="MEDIA_INVALID")
            return False
        await request_cleanup(db, job)
        final_cas = await db.scalar(
            update(AnimationJob)
            .where(
                AnimationJob.id == lease.job_id,
                AnimationJob.user_id == lease.owner_id,
                AnimationJob.status == "running",
                AnimationJob.dispatch_backend == lease.dispatch_backend,
                AnimationJob.dispatch_epoch == lease.dispatch_epoch,
                AnimationJob.attempt == lease.attempt,
                AnimationJob.lease_token == lease.token,
                AnimationJob.lease_expires_at > func.clock_timestamp(),
                AnimationJob.cancel_requested.is_(False),
            )
            .values(
                media_id=record.id,
                status="succeeded",
                progress=1.0,
                lease_token=None,
                lease_expires_at=None,
            )
            .returning(AnimationJob.id)
        )
        if final_cas is None:
            await db.rollback()
            return False
        bind_media(db, job, record)
        await append_animation_event(
            db,
            owner_id=job.user_id,
            job_id=job.id,
            event_type="succeeded",
            payload={"stage": "completed", "progress": 1.0, "media_id": str(record.id)},
        )
        await db.commit()
        return True


async def _heartbeat_until_stopped(
    sessions: async_sessionmaker[AsyncSession],
    lease: JobLease,
    stop: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    controller = RenderHost(sessions, lease.token, loop)
    next_heartbeat = loop.time() + HEARTBEAT_SECONDS
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=CANCEL_POLL_SECONDS)
        except TimeoutError:
            try:
                async with asyncio.timeout(1):
                    async with sessions() as db:
                        current = await _locked_current_job(db, lease)
                        valid = current is not None
                        await db.rollback()
                    if valid and loop.time() >= next_heartbeat:
                        valid = await heartbeat_animation_job(sessions, lease)
                        next_heartbeat = loop.time() + HEARTBEAT_SECONDS
                if not valid:
                    await asyncio.to_thread(controller.stop)
                    return
            except Exception:
                await asyncio.to_thread(controller.stop)
                return


async def run_one_animation_job(
    sessions: async_sessionmaker[AsyncSession],
    *,
    cache: AnimationCache | None = None,
    lease: JobLease | None = None,
) -> UUID | None:
    """One bounded worker step; ordinary learning requests never render inline."""
    lease = lease or await claim_animation_job(sessions)
    if lease is None:
        return None
    if lease.template_id is None:
        from app.services.animation_dsl_publication import publish_dsl_job
        from app.services.animation_job_qualification import current_animation_graph
        from app.workers.dsl_render import DSLRenderResult, render_dsl_job

        graph = current_animation_graph()
        async with sessions() as db:
            job = await _locked_current_job(db, lease)
            candidate_id = job.candidate_id if job is not None else None
        if candidate_id is None:
            await fail_animation_job(sessions, lease, code="DSL_RENDER_UNAVAILABLE")
            return lease.job_id

        async def complete(result: "DSLRenderResult") -> bool:
            return await publish_dsl_job(sessions, graph, lease, result)

        async def failure(code: str) -> bool:
            from app.services.animation_dsl_failure import settle_dsl_failure

            async with sessions() as db:
                current = await _locked_current_job(db, lease)
                if current is None:
                    return False
                await settle_dsl_failure(db, current, code=code)
                await db.commit()
                return True

        await render_dsl_job(
            sessions, graph, lease, candidate_id, complete=complete, failure=failure
        )
        return lease.job_id
    controller = RenderHost(sessions, lease.token, asyncio.get_running_loop())
    trusted_cache = cache or AnimationCache()
    stop = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat_until_stopped(sessions, lease, stop))
    try:
        media = await asyncio.to_thread(
            trusted_cache.resolve,
            lease.template_id,
            lease.parameters,
            container_name=lease.container_name,
            controller=controller,
        )
        if not await report_animation_progress(
            sessions,
            lease,
            stage="validating",
            progress=0.8,
        ):
            return lease.job_id
        await publish_animation_job(sessions, lease, cache=trusted_cache, media=media)
    except RenderError as error:
        await fail_animation_job(sessions, lease, code=str(error))
    except Exception:
        await fail_animation_job(sessions, lease, code="RENDER_FAILED")
    finally:
        stop.set()
        await heartbeat
        await asyncio.to_thread(controller.stop)
    return lease.job_id
