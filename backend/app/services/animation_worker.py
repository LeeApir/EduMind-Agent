"""Separate PostgreSQL-leased worker for reviewed animation rendering and publication."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.animation import AnimationJob, AnimationMedia, AnimationResourceBinding
from app.services.animation_cache import AnimationCache, CachedAnimation
from app.services.animation_jobs import append_animation_event
from app.services.animation_renderer import RenderError

LEASE_SECONDS = 30
HEARTBEAT_SECONDS = 10


@dataclass(frozen=True)
class JobLease:
    job_id: UUID
    owner_id: UUID
    attempt: int
    token: UUID
    template_id: str
    parameters: dict[str, object]


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
        await db.commit()
        return JobLease(job.id, job.user_id, job.attempt, token,
                        job.template_id, dict(job.parameters))


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
        if media.cache_key != job.cache_key or media.template_version != job.template_version:
            await db.rollback()
            await fail_animation_job(sessions, lease, code="TEMPLATE_VERSION_CHANGED")
            return False
        if not cache.validate(media, job.parameters):
            await db.rollback()
            await fail_animation_job(sessions, lease, code="MEDIA_INVALID")
            return False
        runtime_fields = (
            "source_sha256", "image_digest", "font_digest", "renderer_config_sha256",
            "subtitle_version",
        )
        values: dict[str, object] = {
            "id": uuid4(), "cache_key": media.cache_key,
            "template_id": job.template_id, "template_version": job.template_version,
            "review_rule_version": job.review_rule_version,
            **{field: getattr(job, field) for field in runtime_fields},
            "mp4_sha256": media.mp4_sha256, "srt_sha256": media.srt_sha256,
            "mp4_size": media.mp4_path.stat().st_size,
            "srt_size": media.srt_path.stat().st_size,
            "duration_seconds": media.duration_seconds,
            "review_status": "passed",
        }
        await db.execute(
            pg_insert(AnimationMedia).values(**values)
            .on_conflict_do_nothing(index_elements=[AnimationMedia.cache_key])
        )
        record = await db.scalar(select(AnimationMedia).where(
            AnimationMedia.cache_key == media.cache_key,
        ))
        if record is None or (
            record.review_status != "passed"
            or record.mp4_sha256 != media.mp4_sha256
            or record.srt_sha256 != media.srt_sha256
            or any(getattr(record, field) != getattr(job, field) for field in runtime_fields)
        ):
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
        db.add(AnimationResourceBinding(
            user_id=job.user_id, job_id=job.id, media_id=record.id,
            learning_unit_id=job.learning_unit_id, scene_id=job.scene_id,
            scene_version=job.scene_version,
        ))
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
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_SECONDS)
        except TimeoutError:
            if not await heartbeat_animation_job(sessions, lease):
                return


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
