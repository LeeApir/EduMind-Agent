"""Job->attempt lock order. Host mutexes never overlap these mutating transactions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.animation import AnimationJob, AnimationJobAttempt


def record_attempt(db: AsyncSession, job: AnimationJob) -> None:
    assert job.lease_token is not None
    db.add(
        AnimationJobAttempt(
            token=job.lease_token,
            job_id=job.id,
            attempt=job.attempt,
            dispatch_backend=job.dispatch_backend,
            dispatch_epoch=job.dispatch_epoch,
            launch_state="prepared",
        )
    )


async def request_cleanup(db: AsyncSession, job: AnimationJob) -> None:
    if job.lease_token is None:
        return
    row = await db.get(AnimationJobAttempt, job.lease_token, with_for_update=True)
    if row is None or row.job_id != job.id:
        return
    now = await db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    row.launch_state = "cleanup_requested"
    row.cleanup_requested_at = now
    row.cleanup_done_at = None


async def launch_valid(sessions: async_sessionmaker[AsyncSession], token: UUID) -> bool:
    """Nonlocking read allowed under host mutex; current PG lease is mandatory."""
    async with sessions() as db:
        return (
            await db.scalar(
                select(AnimationJob.id)
                .join(AnimationJobAttempt, AnimationJobAttempt.job_id == AnimationJob.id)
                .where(
                    AnimationJobAttempt.token == token,
                    AnimationJobAttempt.launch_state.in_(("starting", "started")),
                    AnimationJobAttempt.cleanup_requested_at.is_(None),
                    AnimationJob.lease_token == token,
                    AnimationJob.status == "running",
                    AnimationJob.cancel_requested.is_(False),
                    AnimationJob.attempt == AnimationJobAttempt.attempt,
                    AnimationJob.dispatch_epoch == AnimationJobAttempt.dispatch_epoch,
                    AnimationJob.dispatch_backend == AnimationJobAttempt.dispatch_backend,
                    AnimationJob.lease_expires_at > func.clock_timestamp(),
                )
            )
            is not None
        )


async def transition(sessions: async_sessionmaker[AsyncSession], token: UUID, stage: str) -> bool:
    if stage not in ("starting", "started", "cleanup_requested", "absent"):
        raise ValueError("INVALID_ATTEMPT_STAGE")
    async with sessions() as db:
        job_id = await db.scalar(
            select(AnimationJobAttempt.job_id).where(AnimationJobAttempt.token == token)
        )
        if job_id is None:
            return False
        job = await db.get(AnimationJob, job_id, with_for_update=True)
        row = await db.get(AnimationJobAttempt, token, with_for_update=True)
        if job is None or row is None:
            return False
        now = await db.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        if stage in ("starting", "started"):
            expected = "prepared" if stage == "starting" else "starting"
            if (
                row.launch_state != expected
                or row.cleanup_requested_at is not None
                or job.status != "running"
                or job.cancel_requested
                or job.lease_token != token
                or job.dispatch_epoch != row.dispatch_epoch
                or job.attempt != row.attempt
                or job.dispatch_backend != row.dispatch_backend
                or job.lease_expires_at is None
                or job.lease_expires_at <= now
            ):
                return False
        else:
            row.cleanup_requested_at = row.cleanup_requested_at or now
            row.cleanup_done_at = now if stage == "absent" else None
        row.launch_state = stage
        await db.commit()
        return True
