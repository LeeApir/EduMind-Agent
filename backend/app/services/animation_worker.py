"""Separate PostgreSQL-leased worker for reviewed animation rendering and publication."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.animation import AnimationJob
from app.services.animation_cache import AnimationCache, CachedAnimation
from app.services.animation_jobs import append_animation_event
from app.services.animation_publication import bind_media, reviewed_media_row
from app.services.animation_renderer import RenderError
from app.services.catalog_animation_access import animation_target_approved

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
    template_id: str
    parameters: dict[str, object]

    @property
    def container_name(self) -> str:
        return f"edumind-render-{self.token.hex}"


def stop_animation_container(lease: JobLease) -> bool:
    """Remove only this attempt's named container after losing its lease."""
    try:
        result = subprocess.run(
            ["docker", "rm", "-f", lease.container_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=10, check=False,
        )
        if result.returncode == 0:
            return True
        absent = subprocess.run(
            ["docker", "inspect", lease.container_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=3, check=False,
        ).returncode != 0
        if not absent:
            logger.warning("Animation container termination failed for job %s", lease.job_id)
        return absent
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("Animation container termination unavailable for job %s", lease.job_id)
        return False


async def claim_animation_job(
    sessions: async_sessionmaker[AsyncSession],
) -> JobLease | None:
    """SKIP LOCKED keeps each claim short and allows independent workers."""
    async with sessions() as db:
        job = await db.scalar(
            select(AnimationJob)
            .where(AnimationJob.status == "queued", AnimationJob.attempt < 2,
                   AnimationJob.cancel_requested.is_(False))
            .order_by(AnimationJob.created_at, AnimationJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            await db.rollback()
            return None
        db_now = await db.scalar(select(func.clock_timestamp()))
        assert isinstance(db_now, datetime)
        token = uuid4()
        job.status = "running"
        job.attempt += 1
        job.lease_token = token
        job.lease_expires_at = db_now + timedelta(seconds=LEASE_SECONDS)
        job.progress = 0.05
        await append_animation_event(
            db, owner_id=job.user_id, job_id=job.id, event_type="running",
            payload={"stage": "rendering", "progress": 0.05, "attempt": job.attempt},
        )
        lease = JobLease(job.id, job.user_id, job.attempt, token,
                         job.template_id, dict(job.parameters))
        await db.commit()
        return lease


async def heartbeat_animation_job(
    sessions: async_sessionmaker[AsyncSession], lease: JobLease,
) -> bool:
    """An expired or replaced token cannot renew, even before the reaper runs."""
    async with sessions() as db:
        result = await db.execute(
            update(AnimationJob).where(
                AnimationJob.id == lease.job_id,
                AnimationJob.user_id == lease.owner_id,
                AnimationJob.status == "running",
                AnimationJob.attempt == lease.attempt,
                AnimationJob.lease_token == lease.token,
                AnimationJob.lease_expires_at > func.clock_timestamp(),
                AnimationJob.cancel_requested.is_(False),
            ).values(lease_expires_at=func.clock_timestamp() + timedelta(seconds=LEASE_SECONDS))
        )
        await db.commit()
        return result.rowcount == 1


async def _locked_current_job(db: AsyncSession, lease: JobLease) -> AnimationJob | None:
    return cast(AnimationJob | None, await db.scalar(select(AnimationJob).where(
        AnimationJob.id == lease.job_id,
        AnimationJob.user_id == lease.owner_id,
        AnimationJob.status == "running",
        AnimationJob.attempt == lease.attempt,
        AnimationJob.lease_token == lease.token,
        AnimationJob.lease_expires_at > func.clock_timestamp(),
        AnimationJob.cancel_requested.is_(False),
    ).with_for_update()))


async def report_animation_progress(
    sessions: async_sessionmaker[AsyncSession], lease: JobLease,
    *, stage: str, progress: float,
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
            db, owner_id=lease.owner_id, job_id=lease.job_id,
            event_type="progress", payload={"stage": stage, "progress": progress},
        )
        await db.commit()
        return True


async def fail_animation_job(
    sessions: async_sessionmaker[AsyncSession], lease: JobLease, *, code: str,
) -> bool:
    async with sessions() as db:
        failed = await db.scalar(
            update(AnimationJob).where(
                AnimationJob.id == lease.job_id,
                AnimationJob.user_id == lease.owner_id,
                AnimationJob.status == "running",
                AnimationJob.attempt == lease.attempt,
                AnimationJob.lease_token == lease.token,
                AnimationJob.lease_expires_at > func.clock_timestamp(),
                AnimationJob.cancel_requested.is_(False),
            ).values(
                status="failed", error_code=code,
                lease_token=None, lease_expires_at=None,
            ).returning(AnimationJob.id)
        )
        if failed is None:
            await db.rollback()
            return False
        await append_animation_event(
            db, owner_id=lease.owner_id, job_id=lease.job_id,
            event_type="failed", payload={"stage": "failed", "code": code},
        )
        await db.commit()
        return True


async def reclaim_expired_animation_jobs(
    sessions: async_sessionmaker[AsyncSession], *, limit: int = 20,
) -> int:
    """On restart, retry once; never turn a missing process into an immediate GET failure."""
    async with sessions() as db:
        jobs = (
            await db.scalars(select(AnimationJob).where(
                AnimationJob.status == "running",
                AnimationJob.lease_expires_at <= func.clock_timestamp(),
            ).order_by(AnimationJob.lease_expires_at).limit(limit)
                .with_for_update(skip_locked=True))
        ).all()
        for job in jobs:
            job.lease_token = None
            job.lease_expires_at = None
            if job.attempt < 2 and not job.cancel_requested:
                job.status = "queued"
                job.progress = 0.0
                event_type = "recovered"
                payload: dict[str, object] = {"stage": "queued", "attempt": job.attempt}
            else:
                job.status = "failed"
                job.error_code = "RENDER_INTERRUPTED"
                event_type = "failed"
                payload = {"stage": "failed", "code": "RENDER_INTERRUPTED"}
            await append_animation_event(
                db, owner_id=job.user_id, job_id=job.id,
                event_type=event_type, payload=payload,
            )
        await db.commit()
        return len(jobs)


async def publish_animation_job(
    sessions: async_sessionmaker[AsyncSession], lease: JobLease,
    *, cache: AnimationCache, media: CachedAnimation,
) -> bool:
    """Current lease alone may bind verified shared bytes to this owner and scene."""
    async with sessions() as db:
        job = await _locked_current_job(db, lease)
        if job is None:
            await db.rollback()
            return False
        if not await animation_target_approved(db, owner_id=job.user_id,
                unit_id=job.learning_unit_id, scene_id=job.scene_id,
                scene_version=job.scene_version, template_id=job.template_id,
                template_version=job.template_version, lock_release=True):
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
        final_cas = await db.scalar(
            update(AnimationJob).where(
                AnimationJob.id == lease.job_id,
                AnimationJob.user_id == lease.owner_id,
                AnimationJob.status == "running",
                AnimationJob.attempt == lease.attempt,
                AnimationJob.lease_token == lease.token,
                AnimationJob.lease_expires_at > func.clock_timestamp(),
                AnimationJob.cancel_requested.is_(False),
            ).values(
                media_id=record.id, status="succeeded", progress=1.0,
                lease_token=None, lease_expires_at=None,
            ).returning(AnimationJob.id)
        )
        if final_cas is None:
            await db.rollback()
            return False
        bind_media(db, job, record)
        await append_animation_event(
            db, owner_id=job.user_id, job_id=job.id, event_type="succeeded",
            payload={"stage": "completed", "progress": 1.0, "media_id": str(record.id)},
        )
        await db.commit()
        return True


async def _heartbeat_until_stopped(
    sessions: async_sessionmaker[AsyncSession], lease: JobLease,
    stop: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    next_heartbeat = loop.time() + HEARTBEAT_SECONDS
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=CANCEL_POLL_SECONDS)
        except TimeoutError:
            async with sessions() as db:
                current = await db.scalar(select(AnimationJob.id).where(
                    AnimationJob.id == lease.job_id,
                    AnimationJob.status == "running",
                    AnimationJob.attempt == lease.attempt,
                    AnimationJob.lease_token == lease.token,
                    AnimationJob.cancel_requested.is_(False),
                ))
            if current is None:
                await asyncio.to_thread(stop_animation_container, lease)
                return
            if loop.time() >= next_heartbeat:
                if not await heartbeat_animation_job(sessions, lease):
                    await asyncio.to_thread(stop_animation_container, lease)
                    return
                next_heartbeat = loop.time() + HEARTBEAT_SECONDS


async def run_one_animation_job(
    sessions: async_sessionmaker[AsyncSession], *, cache: AnimationCache | None = None,
) -> UUID | None:
    """One bounded worker step; ordinary learning requests never render inline."""
    lease = await claim_animation_job(sessions)
    if lease is None:
        return None
    trusted_cache = cache or AnimationCache()
    stop = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat_until_stopped(sessions, lease, stop))
    try:
        media = await asyncio.to_thread(
            trusted_cache.resolve, lease.template_id, lease.parameters,
            container_name=lease.container_name,
        )
        if not await report_animation_progress(
            sessions, lease, stage="validating", progress=0.8,
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
    return lease.job_id
