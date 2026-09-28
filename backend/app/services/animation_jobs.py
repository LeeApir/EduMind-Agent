"""Owner-scoped durable animation request receipts and replayable event rows."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.animation import AnimationJob, AnimationJobEvent
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_cache import AnimationCache, runtime_identity
from app.services.animation_publication import bind_media, reviewed_media_row
from app.services.animation_templates import cache_identity, load_template, normalize_parameters
from app.services.learning_owner_lock import lock_learning_owner


class AnimationIdempotencyConflict(ValueError):
    code = "IDEMPOTENCY_CONFLICT"


class AnimationTargetUnavailable(ValueError):
    code = "ANIMATION_TARGET_UNAVAILABLE"


class AnimationEventCursorInvalid(ValueError):
    code = "EVENT_CURSOR_INVALID"


class AnimationEventCursorExpired(ValueError):
    code = "EVENT_CURSOR_EXPIRED"


@dataclass(frozen=True)
class AnimationReservation:
    job: AnimationJob
    created: bool


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def animation_request_digest(
    *, learning_unit_id: UUID, scene_id: UUID, scene_version: int,
    template_id: str, template_version: str, parameters: Mapping[str, object],
    action_kind: str = "request",
) -> str:
    """The idempotency comparison excludes owner but includes every request field."""
    return _digest({
        "action_kind": action_kind,
        "learning_unit_id": str(learning_unit_id),
        "scene_id": str(scene_id),
        "scene_version": scene_version,
        "template_id": template_id,
        "template_version": template_version,
        "parameters": parameters,
    })


async def reserve_animation_job(
    db: AsyncSession,
    *,
    owner_id: UUID,
    learning_unit_id: UUID,
    scene_id: UUID,
    scene_version: int,
    template_id: str,
    template_version: str,
    parameters: dict[str, object],
    idempotency_key: str,
    cache: AnimationCache | None = None,
) -> AnimationReservation:
    """Atomically create queued job+event or replay the original owner/key result."""
    digest = animation_request_digest(
        learning_unit_id=learning_unit_id, scene_id=scene_id,
        scene_version=scene_version, template_id=template_id,
        template_version=template_version, parameters=parameters,
    )
    try:
        await lock_learning_owner(db, owner_id)
        existing = await db.scalar(select(AnimationJob).where(
            AnimationJob.user_id == owner_id,
            AnimationJob.action_kind == "request",
            AnimationJob.idempotency_key == idempotency_key,
        ))
        if existing is not None:
            if existing.request_digest != digest:
                raise AnimationIdempotencyConflict("Animation request key conflicts.")
            await db.commit()
            return AnimationReservation(existing, False)
        target = await db.scalar(
            select(LearningScene)
            .join(LearningUnit, LearningScene.learning_unit_id == LearningUnit.id)
            .where(
                LearningUnit.id == learning_unit_id,
                LearningUnit.user_id == owner_id,
                LearningUnit.status == "ready",
                LearningScene.id == scene_id,
                LearningScene.version == scene_version,
                LearningScene.generation_status == "complete",
                LearningScene.review_status == "passed",
            )
        )
        if target is None:
            raise AnimationTargetUnavailable("Reviewed scene is unavailable.")
        spec = load_template(template_id, require_executable=True)
        if spec.template_version != template_version:
            raise AnimationTargetUnavailable("Reviewed template version is unavailable.")
        normalized = normalize_parameters(spec, parameters)
        runtime = runtime_identity(template_id)
        job = AnimationJob(
            id=uuid4(), user_id=owner_id, learning_unit_id=learning_unit_id,
            scene_id=scene_id, scene_version=scene_version,
            action_kind="request", idempotency_key=idempotency_key,
            request_digest=digest, parameters_digest=_digest(normalized),
            parameters=normalized, template_id=template_id,
            template_version=template_version,
            review_rule_version=spec.review["rule_version"],
            source_sha256=runtime.source_sha256,
            image_digest=runtime.image_digest,
            font_digest=runtime.font_digest,
            renderer_config_sha256=runtime.renderer_config_sha256,
            subtitle_version=runtime.subtitle_version,
            cache_key=cache_identity(spec, normalized, runtime),
            status="queued", attempt=0, progress=0.0, last_event_id=0,
            cancel_requested=False,
        )
        db.add(job)
        await db.flush()
        hit = await asyncio.to_thread(cache.lookup, template_id, normalized) if cache else None
        if hit is not None:
            record = await reviewed_media_row(db, job, hit)
            if record is None:
                raise AnimationTargetUnavailable("Reviewed animation media is unavailable.")
            job.status = "succeeded"
            job.progress = 1.0
            job.media_id = record.id
            await db.flush()
            bind_media(db, job, record)
            await append_animation_event(
                db, owner_id=owner_id, job_id=job.id, event_type="succeeded",
                payload={"stage": "completed", "progress": 1.0, "media_id": str(record.id)},
            )
        else:
            await append_animation_event(
                db, owner_id=owner_id, job_id=job.id, event_type="queued",
                payload={"stage": "queued", "progress": 0.0},
            )
        await db.commit()
        return AnimationReservation(job, True)
    except Exception:
        await db.rollback()
        raise


async def append_animation_event(
    db: AsyncSession, *, owner_id: UUID, job_id: UUID,
    event_type: str, payload: dict[str, object],
) -> AnimationJobEvent:
    """Lock the job; the caller commits this event together with its state change."""
    if event_type not in {
        "queued", "running", "progress", "succeeded", "failed", "cancelled", "recovered"
    }:
        raise ValueError("invalid animation event")
    if set(payload) - {"stage", "progress", "code", "media_id", "attempt"}:
        raise ValueError("invalid animation event payload")
    stage, progress, code, media_id, attempt = (
        payload.get("stage"), payload.get("progress"), payload.get("code"),
        payload.get("media_id"), payload.get("attempt"),
    )
    if stage is not None and (
        not isinstance(stage, str) or not re.fullmatch(r"[a-z_]{1,32}", stage)
    ):
        raise ValueError("invalid animation event stage")
    if progress is not None:
        if type(progress) not in (int, float):
            raise ValueError("invalid animation event progress")
        assert isinstance(progress, (int, float))
        if not 0 <= progress <= 1:
            raise ValueError("invalid animation event progress")
    if code is not None and (
        not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,64}", code)
    ):
        raise ValueError("invalid animation event code")
    if media_id is not None:
        try:
            UUID(str(media_id))
        except ValueError as error:
            raise ValueError("invalid animation media id") from error
    if attempt is not None and (type(attempt) is not int or not 0 <= attempt <= 2):
        raise ValueError("invalid animation event attempt")
    job = await db.scalar(select(AnimationJob).where(
        AnimationJob.id == job_id, AnimationJob.user_id == owner_id,
    ).with_for_update())
    if job is None:
        raise AnimationTargetUnavailable("Animation job is unavailable.")
    job.last_event_id += 1
    event = AnimationJobEvent(
        job_id=job_id, event_id=job.last_event_id, user_id=owner_id,
        event_type=event_type, payload=payload,
    )
    db.add(event)
    return event


async def replay_animation_events(
    db: AsyncSession, *, owner_id: UUID, job_id: UUID, after: int = 0,
) -> tuple[AnimationJob, tuple[AnimationJobEvent, ...]]:
    job = await db.scalar(select(AnimationJob).where(
        AnimationJob.id == job_id, AnimationJob.user_id == owner_id,
    ))
    if job is None:
        raise AnimationTargetUnavailable("Animation job is unavailable.")
    if after < 0 or after > job.last_event_id:
        raise AnimationEventCursorInvalid("Invalid animation event cursor.")
    events = (
        await db.scalars(select(AnimationJobEvent).where(
            AnimationJobEvent.job_id == job_id,
            AnimationJobEvent.user_id == owner_id,
            AnimationJobEvent.event_id > after,
        ).order_by(AnimationJobEvent.event_id))
    ).all()
    if (events and events[0].event_id != after + 1) or (
        not events and after < job.last_event_id
    ):
        raise AnimationEventCursorExpired("Animation event cursor has expired.")
    return job, tuple(events)
