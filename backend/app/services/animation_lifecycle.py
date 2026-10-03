"""Owner-scoped cancellation and explicit retry of durable animation jobs."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.animation import AnimationJob
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_cache import runtime_identity
from app.services.animation_jobs import (
    AnimationIdempotencyConflict,
    AnimationTargetUnavailable,
    _digest,
    append_animation_event,
)
from app.services.animation_templates import cache_identity, load_template
from app.services.catalog_animation_access import animation_target_approved
from app.services.learning_owner_lock import lock_learning_owner


class AnimationJobStateConflict(ValueError):
    code = "JOB_STATE_CONFLICT"


async def owned_animation_job(
    db: AsyncSession, *, owner_id: UUID, job_id: UUID,
    lock: bool = False,
) -> AnimationJob:
    query = select(AnimationJob).where(
        AnimationJob.id == job_id, AnimationJob.user_id == owner_id,
    )
    if lock:
        query = query.with_for_update()
    job = await db.scalar(query)
    if job is None:
        raise AnimationTargetUnavailable("Animation job is unavailable.")
    if not await animation_target_approved(db, owner_id=owner_id, unit_id=job.learning_unit_id,
            scene_id=job.scene_id, scene_version=job.scene_version, template_id=job.template_id,
            template_version=job.template_version, lock_release=lock):
        raise AnimationTargetUnavailable("Reviewed course is unavailable.")
    return job


async def cancel_animation_job(
    db: AsyncSession, *, owner_id: UUID, job_id: UUID, idempotency_key: str,
) -> AnimationJob:
    try:
        reused = await db.scalar(select(AnimationJob).where(
            AnimationJob.user_id == owner_id,
            AnimationJob.cancel_idempotency_key == idempotency_key,
        ))
        if reused is not None and reused.id != job_id:
            raise AnimationIdempotencyConflict("Cancellation key conflicts.")
        job = await owned_animation_job(db, owner_id=owner_id, job_id=job_id, lock=True)
        if job.status == "cancelled" and job.cancel_idempotency_key == idempotency_key:
            await db.commit()
            return job
        if job.status not in {"queued", "running"}:
            raise AnimationJobStateConflict("Animation job cannot be cancelled.")
        job.status = "cancelled"
        job.cancel_requested = True
        job.cancel_idempotency_key = idempotency_key
        job.lease_token = None
        job.lease_expires_at = None
        await append_animation_event(
            db, owner_id=owner_id, job_id=job.id,
            event_type="cancelled", payload={"stage": "cancelled"},
        )
        await db.commit()
        return job
    except IntegrityError as error:
        await db.rollback()
        raise AnimationIdempotencyConflict("Cancellation key conflicts.") from error
    except Exception:
        await db.rollback()
        raise


async def retry_animation_job(
    db: AsyncSession, *, owner_id: UUID, job_id: UUID, idempotency_key: str,
) -> tuple[AnimationJob, bool]:
    """A retry is a new receipt; the original terminal row never changes."""
    try:
        await lock_learning_owner(db, owner_id)
        existing = await db.scalar(select(AnimationJob).where(
            AnimationJob.user_id == owner_id,
            AnimationJob.action_kind == "retry",
            AnimationJob.idempotency_key == idempotency_key,
        ))
        digest = _digest({"retry_of": str(job_id)})
        if existing is not None:
            if existing.request_digest != digest:
                raise AnimationIdempotencyConflict("Retry key conflicts.")
            await owned_animation_job(db, owner_id=owner_id, job_id=existing.id, lock=True)
            await db.commit()
            return existing, False
        original = await owned_animation_job(db, owner_id=owner_id, job_id=job_id, lock=True)
        if original.status not in {"failed", "cancelled"}:
            raise AnimationJobStateConflict("Animation job cannot be retried.")
        target = await db.scalar(select(LearningScene).join(
            LearningUnit, LearningUnit.id == LearningScene.learning_unit_id,
        ).where(
            LearningUnit.id == original.learning_unit_id,
            LearningUnit.user_id == owner_id,
            LearningUnit.status == "ready",
            LearningScene.id == original.scene_id,
            LearningScene.version == original.scene_version,
            LearningScene.generation_status == "complete",
            LearningScene.review_status == "passed",
        ))
        if target is None:
            raise AnimationTargetUnavailable("Reviewed scene is unavailable.")
        spec = load_template(original.template_id, require_executable=True)
        if spec.template_version != original.template_version:
            raise AnimationJobStateConflict("Reviewed template version changed.")
        runtime = runtime_identity(original.template_id)
        job = AnimationJob(
            id=uuid4(), user_id=owner_id,
            learning_unit_id=original.learning_unit_id,
            scene_id=original.scene_id, scene_version=original.scene_version,
            action_kind="retry", idempotency_key=idempotency_key,
            request_digest=digest, parameters_digest=original.parameters_digest,
            parameters=original.parameters, template_id=original.template_id,
            template_version=spec.template_version,
            review_rule_version=spec.review["rule_version"],
            source_sha256=runtime.source_sha256, image_digest=runtime.image_digest,
            font_digest=runtime.font_digest,
            renderer_config_sha256=runtime.renderer_config_sha256,
            subtitle_version=runtime.subtitle_version,
            cache_key=cache_identity(spec, original.parameters, runtime),
            status="queued", attempt=0, progress=0.0, last_event_id=0,
            cancel_requested=False, retry_of=original.id,
        )
        db.add(job)
        await db.flush()
        await append_animation_event(
            db, owner_id=owner_id, job_id=job.id,
            event_type="queued", payload={"stage": "queued", "progress": 0.0},
        )
        await db.commit()
        return job, True
    except Exception:
        await db.rollback()
        raise
