"""Atomic holder/session/target qualified preparation -> credential-free render receipt."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import AsyncIterator
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.animation_dsl_review import REVIEW_VERSION, binding, canonical, digest
from app.models.animation import AnimationJob, AnimationMedia
from app.models.animation_dsl import DSLCandidate, DSLCandidateRevocation, DSLReviewRecord
from app.models.animation_generation import AnimationPreparation
from app.services.animation_cache import AnimationCache, runtime_identity
from app.services.animation_dsl_candidates import (
    DSLCandidateUnavailable,
    build_dsl_reference,
    policy_manifest,
    qualified_candidate,
    save_dsl_review,
)
from app.services.animation_dsl_compiler import compile_animation_dsl
from app.services.animation_dsl_media_cache import AnimationDSLMediaCache
from app.services.animation_dsl_publication import dsl_media_values, private_cache_lock
from app.services.animation_dsl_renderer import renderer_identity
from app.services.animation_dsl_runtime import FONT_DIGEST, IMAGE
from app.services.animation_intent import intent_from_payload
from app.services.animation_jobs import append_animation_event
from app.services.animation_preparation import _ACTIVE, _now, owned_preparation
from app.services.animation_publication import bind_media, reviewed_media_row
from app.services.animation_templates import cache_identity, load_template, normalize_parameters
from app.services.durable_job_dispatch import dispatch_backend, enqueue_animation_job
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.video_dsl_generation import VideoPlan, _template
from app.workers.dsl_render import dsl_cache_key, qualification_in_transaction


@asynccontextmanager
async def _no_cache_lock() -> AsyncIterator[None]:
    yield


async def handoff_video_plan(
    db: AsyncSession,
    graph: KnowledgeGraphRepository,
    *,
    owner: UUID,
    session_hash: str,
    operation_id: UUID,
    execution_token: UUID,
    plan: VideoPlan,
    template_cache: AnimationCache | None = None,
    dsl_cache: AnimationDSLMediaCache | None = None,
    source_validator: Callable[[AsyncSession], Awaitable[None]] | None = None,
) -> AnimationJob | None:
    """Does not send to a Provider. Cancellation and handoff contend on the preparation row."""
    try:
        if plan.source in {"generated_dsl", "reviewed_dsl_cache"} and source_validator is not None:
            await source_validator(db)
        operation = await owned_preparation(
            db,
            owner=owner,
            session_hash=session_hash,
            operation_id=operation_id,
            lock=True,
        )
        if operation.execution_token != execution_token:
            raise DSLCandidateUnavailable()
        if operation.stage not in _ACTIVE:
            await db.commit()
            return None
        reference = await build_dsl_reference(
            db,
            graph,
            owner=owner,
            unit_id=operation.learning_unit_id,
            scene_id=operation.scene_id,
            version=operation.scene_version,
            lock=True,
        )
        intent = intent_from_payload(operation.intent)
        if reference.sha256 != operation.reference_sha256 or plan.intent_sha256 != digest(
            {"intent": intent.payload(), "reference": reference.sha256}
        ):
            raise DSLCandidateUnavailable()
        if plan.source == "unavailable":
            operation.stage, operation.error_code = "failed", "ANIMATION_UNAVAILABLE"
            operation.source_kind = "unavailable"
            await db.commit()
            return None
        if plan.source == "template_fallback" and not operation.allow_template_fallback:
            operation.stage, operation.error_code = "failed", "ANIMATION_UNAVAILABLE"
            operation.source_kind = "unavailable"
            await db.commit()
            return None
        if plan.source in {"generated_dsl", "reviewed_dsl_cache"}:
            job = await _dsl_job(db, graph, operation, plan)
        else:
            job = _template_job(operation, plan)
        db.add(job)
        await db.flush()
        # Formal cache hits require current qualification and actual file integrity.
        qualification = None
        if job.render_kind == "dsl":
            if job.candidate_id is None:
                raise DSLCandidateUnavailable()
            qualification = await qualification_in_transaction(
                db,
                graph,
                job,
                job.candidate_id,
                lock=True,
            )
        private = dsl_cache or AnimationDSLMediaCache()
        context = (
            private_cache_lock(private, owner, job.cache_key) if qualification else _no_cache_lock()
        )
        async with context:
            media = None
            if qualification is not None:
                cached = await asyncio.to_thread(
                    private.lookup, owner, job.cache_key, qualification.compiled
                )
                if cached is not None:
                    candidate = await db.get(DSLCandidate, job.candidate_id)
                    review = (
                        await db.get(DSLReviewRecord, candidate.review_id) if candidate else None
                    )
                    row = await db.scalar(
                        select(AnimationMedia).where(
                            AnimationMedia.cache_key == job.cache_key,
                        )
                    )
                    if review is not None and row is not None:
                        values = dsl_media_values(job, qualification, review, cached)
                        if all(getattr(row, key) == value for key, value in values.items()):
                            media = row
            elif template_cache is not None and job.template_id is not None:
                cached_template = await asyncio.to_thread(
                    template_cache.lookup, job.template_id, job.parameters
                )
                if cached_template is not None:
                    media = await reviewed_media_row(db, job, cached_template)
                    if media is None:
                        raise DSLCandidateUnavailable()
            if media is not None:
                job.status, job.progress, job.media_id = "succeeded", 1.0, media.id
                await db.flush()
                bind_media(db, job, media)
                event, payload = (
                    "succeeded",
                    {
                        "stage": "completed",
                        "progress": 1.0,
                        "media_id": str(media.id),
                    },
                )
            else:
                event, payload = "queued", {"stage": "queued", "progress": 0.0}
            await append_animation_event(
                db, owner_id=owner, job_id=job.id, event_type=event, payload=payload
            )
            # Recheck absolute deadline at commit, including local cache/compile latency.
            if await _now(db) >= operation.deadline:
                raise DSLCandidateUnavailable()
            operation.stage, operation.job_id = "handed_off", job.id
            operation.source_kind = plan.source
            operation.error_code = plan.error_code if plan.source == "template_fallback" else None
            enqueue_animation_job(db, job)
            await db.commit()
        return job
    except Exception:
        await db.rollback()
        raise


async def _dsl_job(
    db: AsyncSession,
    graph: KnowledgeGraphRepository,
    operation: AnimationPreparation,
    plan: VideoPlan,
) -> AnimationJob:
    outcome = plan.outcome
    if (
        outcome is None
        or not outcome.approved
        or outcome.reference.sha256 != operation.reference_sha256
        or outcome.animation_intent_json != canonical(operation.intent)
    ):
        raise DSLCandidateUnavailable()
    fresh = await asyncio.to_thread(
        compile_animation_dsl,
        outcome.compiled.validated.canonical_json,
        knowledge_point_id=outcome.reference.knowledge_point_id,
    )
    if (
        fresh != outcome.compiled
        or outcome.issues
        or outcome.review_source is None
        or binding(
            fresh, outcome.reference, outcome.generation_source, outcome.animation_intent_json
        )
        != outcome.binding_sha256
        or outcome.review_sha256
        != digest(
            {
                "binding": outcome.binding_sha256,
                "verdict": "pass",
                "issues": [],
                "source": asdict(outcome.review_source),
            }
        )
    ):
        raise DSLCandidateUnavailable()
    candidates = (
        await db.scalars(
            select(DSLCandidate)
            .where(
                DSLCandidate.user_id == operation.user_id,
                DSLCandidate.learning_unit_id == operation.learning_unit_id,
                DSLCandidate.scene_id == operation.scene_id,
                DSLCandidate.scene_version == operation.scene_version,
                DSLCandidate.binding_sha256 == outcome.binding_sha256,
                DSLCandidate.policy_id == digest(policy_manifest()),
                DSLCandidate.id.not_in(select(DSLCandidateRevocation.candidate_id)),
            )
            .order_by(DSLCandidate.created_at, DSLCandidate.id)
            .limit(4)
        )
    ).all()
    candidate = None
    for value in candidates:
        checked = await qualified_candidate(
            db, graph, owner=operation.user_id, candidate_id=value.id, lock=True
        )
        if checked.canonical_dsl == outcome.compiled.validated.canonical_json:
            candidate = checked
            break
    if candidate is None:
        _, candidate = await save_dsl_review(
            db,
            graph,
            owner=operation.user_id,
            unit_id=operation.learning_unit_id,
            scene_id=operation.scene_id,
            version=operation.scene_version,
            outcome=outcome,
        )
    if candidate is None:
        raise DSLCandidateUnavailable()
    compiled = outcome.compiled
    parameters = {"candidate_id": str(candidate.id)}
    return AnimationJob(
        **_base(operation),
        parameters=parameters,
        parameters_digest=digest(parameters),
        render_kind="dsl",
        template_id=None,
        template_version=None,
        candidate_id=candidate.id,
        review_rule_version=REVIEW_VERSION,
        source_sha256=compiled.source_sha256,
        image_digest=IMAGE.split("@", 1)[1],
        font_digest=FONT_DIGEST,
        renderer_config_sha256=renderer_identity(),
        subtitle_version="animation-dsl-subtitles-v1",
        cache_key=dsl_cache_key(compiled, outcome.binding_sha256, operation.user_id),
    )


def _template_job(operation: AnimationPreparation, plan: VideoPlan) -> AnimationJob:
    intent = intent_from_payload(operation.intent)
    template = _template(intent)
    if (
        template is None
        or template != (plan.template_id, plan.template_version, plan.parameters_json)
        or plan.source not in {"reviewed_cache", "parameterized_template", "template_fallback"}
    ):
        raise DSLCandidateUnavailable()
    tid, version, params = template
    spec = load_template(tid, require_executable=True)
    parameters = normalize_parameters(spec, json.loads(params))
    runtime = runtime_identity(tid)
    return AnimationJob(
        **_base(operation),
        parameters=parameters,
        parameters_digest=digest(parameters),
        render_kind="template",
        template_id=tid,
        template_version=version,
        review_rule_version=spec.review["rule_version"],
        source_sha256=runtime.source_sha256,
        image_digest=runtime.image_digest,
        font_digest=runtime.font_digest,
        renderer_config_sha256=runtime.renderer_config_sha256,
        subtitle_version=runtime.subtitle_version,
        cache_key=cache_identity(spec, parameters, runtime),
        fallback_reason_code=plan.error_code if plan.source == "template_fallback" else None,
    )


def _base(operation: AnimationPreparation) -> dict[str, object]:
    return {
        "id": uuid4(),
        "user_id": operation.user_id,
        "learning_unit_id": operation.learning_unit_id,
        "scene_id": operation.scene_id,
        "scene_version": operation.scene_version,
        "action_kind": "request",
        "idempotency_key": "dsl-preparation-" + str(operation.id),
        "request_digest": operation.request_digest,
        "generation_id": operation.id,
        "dispatch_backend": dispatch_backend(),
        "dispatch_epoch": 1,
        "status": "queued",
        "attempt": 0,
        "progress": 0.0,
        "last_event_id": 0,
        "cancel_requested": False,
    }
