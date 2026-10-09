"""Bounded render recovery and one explicitly authorized, credential-free template fallback."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.animation_dsl_review import digest
from app.models.animation import AnimationJob
from app.models.animation_generation import AnimationPreparation
from app.models.auth import GuestSessionRecord
from app.services.animation_attempts import request_cleanup
from app.services.animation_dsl_handoff import _template_job
from app.services.animation_intent import intent_from_payload
from app.services.animation_job_qualification import animation_job_approved
from app.services.animation_jobs import append_animation_event
from app.services.durable_job_dispatch import enqueue_animation_job
from app.services.video_dsl_generation import VideoPlan, _template


async def authorized_template_fallback(
    db: AsyncSession, original: AnimationJob
) -> AnimationJob | None:
    """Caller holds original Job lock; terminal state and original session never change."""
    if (
        original.render_kind != "dsl"
        or original.status != "failed"
        or original.attempt < 2
        or original.cancel_requested
        or original.fallback_of is not None
        or original.generation_id is None
        or not await animation_job_approved(db, original, lock=True)
    ):
        return None
    existing = await db.scalar(
        select(AnimationJob).where(
            AnimationJob.fallback_of == original.id, AnimationJob.render_kind == "template"
        )
    )
    if existing is not None:
        return existing
    preparation = await db.get(AnimationPreparation, original.generation_id)
    if (
        preparation is None
        or not preparation.allow_template_fallback
        or preparation.user_id != original.user_id
        or preparation.stage != "handed_off"
    ):
        return None
    session = await db.scalar(
        select(GuestSessionRecord)
        .where(
            GuestSessionRecord.token_hash == preparation.originating_session_hash,
            GuestSessionRecord.user_id == original.user_id,
            GuestSessionRecord.expires_at > func.clock_timestamp(),
            GuestSessionRecord.expires_at == preparation.originating_session_expires_at,
        )
        .with_for_update(read=True)
    )
    if session is None:
        return None
    intent = intent_from_payload(preparation.intent)
    template = _template(intent)
    if template is None:
        return None
    tid, version, params = template
    plan = VideoPlan(
        "template_fallback",
        digest({"intent": intent.payload(), "reference": preparation.reference_sha256}),
        tid,
        version,
        params,
        error_code="DSL_RENDER_FAILED",
    )
    fallback = _template_job(preparation, plan)
    fallback.id = uuid4()
    fallback.idempotency_key = "dsl-render-fallback-" + str(original.id)
    fallback.request_digest = digest(
        {
            "fallback_of": str(original.id),
            "intent": preparation.intent,
            "generation_id": str(preparation.id),
        }
    )
    fallback.fallback_of = original.id
    fallback.fallback_reason_code = "DSL_RENDER_FAILED"
    if not await animation_job_approved(db, fallback, lock=True):
        return None
    # No later guest/session or credential version may extend the frozen authorization.
    now = await db.scalar(select(func.clock_timestamp()))
    if now is None or now >= preparation.originating_session_expires_at:
        return None
    db.add(fallback)
    await db.flush()
    await append_animation_event(
        db,
        owner_id=fallback.user_id,
        job_id=fallback.id,
        event_type="queued",
        payload={
            "stage": "queued",
            "progress": 0.0,
            "fallback_of": str(original.id),
            "source": "template_fallback",
            "reason_code": "DSL_RENDER_FAILED",
        },
    )
    enqueue_animation_job(db, fallback)
    return fallback


async def settle_dsl_failure(db: AsyncSession, job: AnimationJob, *, code: str) -> None:
    """Same transaction commits cleanup, bounded retry or final failure and fallback/outbox."""
    await request_cleanup(db, job)
    can_retry = (
        job.attempt < 2
        and not job.cancel_requested
        and await animation_job_approved(db, job, lock=True)
    )
    job.lease_token = job.lease_expires_at = None
    if can_retry:
        job.status, job.progress, job.error_code = "queued", 0.0, None
        job.dispatch_epoch += 1
        enqueue_animation_job(db, job)
        event, payload = "recovered", {"stage": "queued", "attempt": job.attempt}
    else:
        job.status, job.error_code = "failed", code
        fallback = await authorized_template_fallback(db, job)
        event, payload = "failed", {"stage": "failed", "code": code}
        if fallback is not None:
            payload["fallback_job_id"] = str(fallback.id)
            payload["fallback_source"] = "template_fallback"
    await append_animation_event(
        db, owner_id=job.user_id, job_id=job.id, event_type=event, payload=payload
    )
