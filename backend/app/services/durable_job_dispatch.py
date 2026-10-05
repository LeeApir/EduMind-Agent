"""Transactional animation outbox; PG receipts survive arbitrary broker delivery loss."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from os import getenv
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import ConfigurationError
from app.models.animation import AnimationDispatchOutbox, AnimationJob

TASK_NAME = "edumind.render_animation.v1"
QUEUE_NAME = "edumind.animation.v1"
DispatchBackend = Literal["pg_poll", "celery"]


def dispatch_backend() -> DispatchBackend:
    value = getenv("EDUMIND_ANIMATION_DISPATCH", "pg_poll")
    if value not in ("pg_poll", "celery"):
        raise ConfigurationError("EDUMIND_ANIMATION_DISPATCH must be pg_poll or celery.")
    return value  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class DispatchMessage:
    job_id: UUID
    dispatch_epoch: int

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "job_id": str(self.job_id),
            "dispatch_epoch": self.dispatch_epoch,
        }

    @classmethod
    def parse(cls, value: object) -> "DispatchMessage":
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "job_id", "dispatch_epoch"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or type(value["dispatch_epoch"]) is not int
            or not 1 <= value["dispatch_epoch"] <= 2147483647
            or not isinstance(value["job_id"], str)
            or len(value["job_id"]) != 36
        ):
            raise ValueError("INVALID_DISPATCH_MESSAGE")
        try:
            job_id = UUID(value["job_id"])
        except ValueError:
            raise ValueError("INVALID_DISPATCH_MESSAGE") from None
        if str(job_id) != value["job_id"]:
            raise ValueError("INVALID_DISPATCH_MESSAGE")
        return cls(job_id, value["dispatch_epoch"])


def enqueue_animation_job(db: AsyncSession, job: AnimationJob) -> None:
    """Caller holds Job lock and commits this row with Job/event, never sends here."""
    if job.dispatch_backend == "celery" and job.status == "queued" and not job.cancel_requested:
        db.add(
            AnimationDispatchOutbox(
                id=uuid4(),
                job_id=job.id,
                dispatch_epoch=job.dispatch_epoch,
                schema_version=1,
                task_name=TASK_NAME,
                state="pending",
                transport_attempts=0,
            )
        )


@dataclass(frozen=True, slots=True)
class DispatchClaim:
    outbox_id: UUID
    token: UUID
    message: DispatchMessage


def eligible(job: AnimationJob | None, epoch: int) -> bool:
    return bool(
        job is not None
        and job.dispatch_backend == "celery"
        and job.dispatch_epoch == epoch
        and job.status == "queued"
        and not job.cancel_requested
    )


async def claim_dispatches(
    sessions: async_sessionmaker[AsyncSession],
    *,
    limit: int = 100,
) -> tuple[DispatchClaim, ...]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("INVALID_DISPATCH_BATCH")
    async with sessions() as db:
        now = await db.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        rows = (
            await db.scalars(
                select(AnimationDispatchOutbox)
                .where(
                    or_(
                        (AnimationDispatchOutbox.state == "pending")
                        & (AnimationDispatchOutbox.next_attempt_at <= now),
                        (AnimationDispatchOutbox.state == "sending")
                        & (AnimationDispatchOutbox.publisher_expires_at <= now),
                    )
                )
                .order_by(AnimationDispatchOutbox.next_attempt_at, AnimationDispatchOutbox.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        claims = []
        for row in rows:
            # No Job lock while holding outbox; stale eligibility may send once more.
            job = await db.get(AnimationJob, row.job_id)
            if not eligible(job, row.dispatch_epoch):
                row.state = "obsolete"
                row.publisher_token = row.publisher_expires_at = None
                continue
            token = uuid4()
            row.state = "sending"
            row.publisher_token = token
            row.publisher_expires_at = now + timedelta(seconds=30)
            row.transport_attempts += 1
            claims.append(
                DispatchClaim(row.id, token, DispatchMessage(row.job_id, row.dispatch_epoch))
            )
        await db.commit()
        return tuple(claims)


async def finish_dispatch(
    sessions: async_sessionmaker[AsyncSession],
    claim: DispatchClaim,
    *,
    sent: bool,
) -> bool:
    async with sessions() as db:
        row = await db.scalar(
            select(AnimationDispatchOutbox)
            .where(
                AnimationDispatchOutbox.id == claim.outbox_id,
                AnimationDispatchOutbox.state == "sending",
                AnimationDispatchOutbox.publisher_token == claim.token,
                AnimationDispatchOutbox.publisher_expires_at > func.clock_timestamp(),
            )
            .with_for_update()
        )
        if row is None:
            await db.rollback()
            return False
        now = await db.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        row.state = "sent" if sent else "pending"
        row.publisher_token = row.publisher_expires_at = None
        if sent:
            row.last_sent_at = now
            row.error_code = None
        else:
            row.error_code = "BROKER_UNAVAILABLE"
            row.next_attempt_at = now + timedelta(
                seconds=min(60, 2 ** min(6, row.transport_attempts - 1))
            )
        await db.commit()
        return True


async def publish_dispatch_batch(
    sessions: async_sessionmaker[AsyncSession],
    send: Callable[[DispatchClaim], Awaitable[None]],
    *,
    limit: int = 100,
) -> int:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("INVALID_DISPATCH_BATCH")
    count = 0
    for _ in range(limit):
        claims = await claim_dispatches(sessions, limit=1)
        if not claims:
            break
        claim = claims[0]
        count += 1
        try:
            await send(claim)
        except Exception:
            # Never persist transport exception text, URLs or credentials.
            await finish_dispatch(sessions, claim, sent=False)
        else:
            await finish_dispatch(sessions, claim, sent=True)
    return count


async def reconcile_dispatches(
    sessions: async_sessionmaker[AsyncSession],
    *,
    limit: int = 100,
) -> int:
    """Repair missing/sent-but-lost rows, with Job->outbox lock order and bounded batches."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("INVALID_DISPATCH_BATCH")
    async with sessions() as db:
        # Select only work requiring repair, so a fixed first 100 cannot starve later Jobs.
        current = (
            select(AnimationDispatchOutbox.id)
            .where(
                AnimationDispatchOutbox.job_id == AnimationJob.id,
                AnimationDispatchOutbox.dispatch_epoch == AnimationJob.dispatch_epoch,
            )
            .exists()
        )
        repair = (
            select(AnimationDispatchOutbox.id)
            .where(
                AnimationDispatchOutbox.job_id == AnimationJob.id,
                or_(
                    AnimationDispatchOutbox.dispatch_epoch != AnimationJob.dispatch_epoch,
                    AnimationJob.status != "queued",
                    AnimationJob.cancel_requested.is_(True),
                    AnimationJob.dispatch_backend != "celery",
                    (
                        (AnimationDispatchOutbox.state == "sent")
                        & (
                            AnimationDispatchOutbox.last_sent_at
                            <= func.clock_timestamp() - timedelta(seconds=60)
                        )
                    ),
                    (
                        (AnimationDispatchOutbox.state == "sending")
                        & (AnimationDispatchOutbox.publisher_expires_at <= func.clock_timestamp())
                    ),
                ),
                AnimationDispatchOutbox.state != "obsolete",
            )
            .exists()
        )
        jobs = (
            await db.scalars(
                select(AnimationJob)
                .where(
                    or_(
                        (AnimationJob.dispatch_backend == "celery")
                        & (AnimationJob.status == "queued")
                        & AnimationJob.cancel_requested.is_(False)
                        & ~current,
                        repair,
                    )
                )
                .order_by(AnimationJob.created_at, AnimationJob.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        now = await db.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        for job in jobs:
            rows = (
                await db.scalars(
                    select(AnimationDispatchOutbox)
                    .where(
                        AnimationDispatchOutbox.job_id == job.id,
                    )
                    .with_for_update()
                )
            ).all()
            matching = False
            for row in rows:
                if not eligible(job, row.dispatch_epoch):
                    row.state = "obsolete"
                    row.publisher_token = row.publisher_expires_at = None
                    continue
                matching = True
                if (
                    row.state == "sending"
                    and row.publisher_expires_at is not None
                    and row.publisher_expires_at <= now
                ) or (
                    row.state == "sent"
                    and row.last_sent_at is not None
                    and row.last_sent_at <= now - timedelta(seconds=60)
                ):
                    row.state = "pending"
                    row.next_attempt_at = now
                    row.publisher_token = row.publisher_expires_at = None
            if not matching and eligible(job, job.dispatch_epoch):
                enqueue_animation_job(db, job)
        await db.commit()
        return len(jobs)


async def route_queued_template_jobs(
    sessions: async_sessionmaker[AsyncSession],
    job_ids: tuple[UUID, ...],
    *,
    backend: DispatchBackend,
) -> int:
    """Explicit operator migration/rollback only; never rewrite active leases or terminal jobs."""
    if backend not in ("pg_poll", "celery") or not 1 <= len(job_ids) <= 100:
        raise ValueError("INVALID_DISPATCH_MIGRATION")
    from app.services.catalog_animation_access import animation_target_approved

    async with sessions() as db:
        jobs = (
            await db.scalars(
                select(AnimationJob)
                .where(
                    AnimationJob.id.in_(job_ids),
                    AnimationJob.status == "queued",
                    AnimationJob.cancel_requested.is_(False),
                )
                .order_by(AnimationJob.id)
                .with_for_update()
            )
        ).all()
        changed = 0
        for job in jobs:
            if job.dispatch_backend == backend:
                continue
            if job.template_id not in ("linked-list-insertion", "linked-list-deletion"):
                raise ValueError("RENDERER_UNAVAILABLE")
            if not await animation_target_approved(
                db,
                owner_id=job.user_id,
                unit_id=job.learning_unit_id,
                scene_id=job.scene_id,
                scene_version=job.scene_version,
                template_id=job.template_id,
                template_version=job.template_version,
                lock_release=True,
            ):
                raise ValueError("ANIMATION_TARGET_UNAVAILABLE")
            rows = (
                await db.scalars(
                    select(AnimationDispatchOutbox)
                    .where(
                        AnimationDispatchOutbox.job_id == job.id,
                    )
                    .with_for_update()
                )
            ).all()
            for row in rows:
                row.state = "obsolete"
                row.publisher_token = row.publisher_expires_at = None
            job.dispatch_backend = backend
            job.dispatch_epoch += 1
            enqueue_animation_job(db, job)
            changed += 1
        await db.commit()
        return changed
