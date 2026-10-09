"""Owner-scoped cancellation and explicit retry of durable animation jobs."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.animation import AnimationDispatchOutbox, AnimationJob
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_attempts import request_cleanup
from app.services.animation_cache import runtime_identity
from app.services.animation_job_qualification import animation_job_approved
from app.services.animation_jobs import (
    AnimationIdempotencyConflict,
    AnimationTargetUnavailable,
    _digest,
    append_animation_event,
)
from app.services.animation_templates import cache_identity, load_template
from app.services.durable_job_dispatch import dispatch_backend, enqueue_animation_job
from app.services.learning_owner_lock import lock_learning_owner


class AnimationJobStateConflict(ValueError):
    code = "JOB_STATE_CONFLICT"


async def owned_animation_job(
    db: AsyncSession,
    *,
    owner_id: UUID,
    job_id: UUID,
    lock: bool = False,
) -> AnimationJob:
    query = select(AnimationJob).where(
        AnimationJob.id == job_id,
        AnimationJob.user_id == owner_id,
    )
    if lock:
        query = query.with_for_update()
    job = await db.scalar(query)
    if job is None:
        raise AnimationTargetUnavailable("Animation job is unavailable.")
    if not await animation_job_approved(db, job, lock=lock):
        raise AnimationTargetUnavailable("Reviewed course is unavailable.")
    return job


async def cancel_animation_job(
    db: AsyncSession,
    *,
    owner_id: UUID,
    job_id: UUID,
    idempotency_key: str,
) -> AnimationJob:
    try:
        reused = await db.scalar(
            select(AnimationJob).where(
                AnimationJob.user_id == owner_id,
                AnimationJob.cancel_idempotency_key == idempotency_key,
            )
        )
        if reused is not None and reused.id != job_id:
            raise AnimationIdempotencyConflict("Cancellation key conflicts.")
        job = await owned_animation_job(db, owner_id=owner_id, job_id=job_id, lock=True)
        if job.status == "cancelled" and job.cancel_idempotency_key == idempotency_key:
            await db.commit()
            return job
        if job.status not in {"queued", "running"}:
            raise AnimationJobStateConflict("Animation job cannot be cancelled.")
        await request_cleanup(db, job)
        outboxes = (
            await db.scalars(
                select(AnimationDispatchOutbox)
                .where(
                    AnimationDispatchOutbox.job_id == job.id,
                )
                .with_for_update()
            )
        ).all()
        for row in outboxes:
            row.state = "obsolete"
            row.publisher_token = row.publisher_expires_at = None
        job.status = "cancelled"
        job.cancel_requested = True
        job.cancel_idempotency_key = idempotency_key
        job.lease_token = None
        job.lease_expires_at = None
        await append_animation_event(
            db,
            owner_id=owner_id,
            job_id=job.id,
            event_type="cancelled",
            payload={"stage": "cancelled"},
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
    db: AsyncSession,
    *,
    owner_id: UUID,
    job_id: UUID,
    idempotency_key: str,
) -> tuple[AnimationJob, bool]:
    """A retry is a new receipt; the original terminal row never changes."""
    try:
        await lock_learning_owner(db, owner_id)
        existing = await db.scalar(
            select(AnimationJob).where(
                AnimationJob.user_id == owner_id,
                AnimationJob.action_kind == "retry",
                AnimationJob.idempotency_key == idempotency_key,
            )
        )
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
        target = await db.scalar(
            select(LearningScene)
            .join(
                LearningUnit,
                LearningUnit.id == LearningScene.learning_unit_id,
            )
            .where(
                LearningUnit.id == original.learning_unit_id,
                LearningUnit.user_id == owner_id,
                LearningUnit.status == "ready",
                LearningScene.id == original.scene_id,
                LearningScene.version == original.scene_version,
                LearningScene.generation_status == "complete",
                LearningScene.review_status == "passed",
            )
        )
        if target is None:
            raise AnimationTargetUnavailable("Reviewed scene is unavailable.")
        if original.render_kind == "dsl":
            # Reuse an approved candidate under a fresh render receipt, never replay model sends.
            from app.services.animation_dsl_candidates import qualified_candidate
            from app.services.animation_dsl_compiler import compile_animation_dsl
            from app.services.animation_job_qualification import current_animation_graph
            from app.workers.dsl_render import dsl_cache_key, job_knowledge_point

            if original.candidate_id is None:
                raise AnimationJobStateConflict()
            candidate = await qualified_candidate(
                db,
                current_animation_graph(),
                owner=owner_id,
                candidate_id=original.candidate_id,
                lock=True,
            )
            compiled = compile_animation_dsl(
                candidate.canonical_dsl,
                knowledge_point_id=job_knowledge_point(candidate.canonical_dsl),
            )
            if dsl_cache_key(compiled, candidate.binding_sha256, owner_id) != original.cache_key:
                raise AnimationJobStateConflict("DSL versions changed")
            job = AnimationJob(
                id=uuid4(),
                user_id=owner_id,
                learning_unit_id=original.learning_unit_id,
                scene_id=original.scene_id,
                scene_version=original.scene_version,
                action_kind="retry",
                idempotency_key=idempotency_key,
                request_digest=digest,
                parameters_digest=original.parameters_digest,
                parameters=original.parameters,
                template_id=None,
                template_version=None,
                render_kind="dsl",
                candidate_id=original.candidate_id,
                generation_id=original.generation_id,
                review_rule_version=original.review_rule_version,
                source_sha256=original.source_sha256,
                image_digest=original.image_digest,
                font_digest=original.font_digest,
                renderer_config_sha256=original.renderer_config_sha256,
                subtitle_version=original.subtitle_version,
                cache_key=original.cache_key,
                dispatch_backend=dispatch_backend(),
                dispatch_epoch=1,
                status="queued",
                attempt=0,
                progress=0.0,
                last_event_id=0,
                cancel_requested=False,
                retry_of=original.id,
            )
            db.add(job)
            await db.flush()
            await append_animation_event(
                db,
                owner_id=owner_id,
                job_id=job.id,
                event_type="queued",
                payload={"stage": "queued", "progress": 0.0},
            )
            enqueue_animation_job(db, job)
            await db.commit()
            return job, True
        if original.template_id is None:
            raise AnimationJobStateConflict()
        spec = load_template(original.template_id, require_executable=True)
        if spec.template_version != original.template_version:
            raise AnimationJobStateConflict("Reviewed template version changed.")
        runtime = runtime_identity(original.template_id)
        job = AnimationJob(
            id=uuid4(),
            user_id=owner_id,
            learning_unit_id=original.learning_unit_id,
            scene_id=original.scene_id,
            scene_version=original.scene_version,
            action_kind="retry",
            idempotency_key=idempotency_key,
            request_digest=digest,
            parameters_digest=original.parameters_digest,
            parameters=original.parameters,
            template_id=original.template_id,
            template_version=spec.template_version,
            review_rule_version=spec.review["rule_version"],
            source_sha256=runtime.source_sha256,
            image_digest=runtime.image_digest,
            font_digest=runtime.font_digest,
            renderer_config_sha256=runtime.renderer_config_sha256,
            subtitle_version=runtime.subtitle_version,
            cache_key=cache_identity(spec, original.parameters, runtime),
            dispatch_backend=dispatch_backend(),
            dispatch_epoch=1,
            status="queued",
            attempt=0,
            progress=0.0,
            last_event_id=0,
            cancel_requested=False,
            retry_of=original.id,
        )
        db.add(job)
        await db.flush()
        await append_animation_event(
            db,
            owner_id=owner_id,
            job_id=job.id,
            event_type="queued",
            payload={"stage": "queued", "progress": 0.0},
        )
        enqueue_animation_job(db, job)
        await db.commit()
        return job, True
    except Exception:
        await db.rollback()
        raise
