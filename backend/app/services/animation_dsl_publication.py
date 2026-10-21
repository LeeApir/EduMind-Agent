"""Lease/qualification/cache ordered publication of private reviewed DSL media."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.animation import AnimationJob, AnimationMedia
from app.models.animation_dsl import DSLCandidate, DSLReviewRecord
from app.services.animation_dsl_candidates import DSLCandidateUnavailable
from app.services.animation_dsl_media_cache import AnimationDSLMediaCache, PrivateDSLMedia
from app.services.animation_jobs import append_animation_event
from app.services.animation_publication import RUNTIME_FIELDS, bind_media
from app.services.animation_worker import JobLease, _locked_current_job
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.workers.dsl_render import (
    DSLRenderQualification,
    DSLRenderResult,
    qualification_in_transaction,
)


@asynccontextmanager
async def private_cache_lock(
    cache: AnimationDSLMediaCache,
    owner: UUID,
    key: str,
) -> AsyncIterator[None]:
    context = cache.lock(owner, key)
    acquisition = asyncio.create_task(asyncio.to_thread(context.__enter__))
    try:
        await asyncio.shield(acquisition)
    except asyncio.CancelledError:
        # A blocked thread can acquire after cancellation. Always release its eventual lock.
        await acquisition
        await asyncio.to_thread(context.__exit__, None, None, None)
        raise
    try:
        yield
    finally:
        await asyncio.to_thread(context.__exit__, None, None, None)


async def publish_dsl_job(
    sessions: async_sessionmaker[AsyncSession],
    graph: KnowledgeGraphRepository,
    lease: JobLease,
    result: DSLRenderResult,
    *,
    cache: AnimationDSLMediaCache | None = None,
) -> bool:
    if result.media is None or result.qualification is None:
        return False
    trusted_cache = cache or AnimationDSLMediaCache()
    async with sessions() as db:
        try:
            job = await _locked_current_job(db, lease)
            if job is None or job.candidate_id is None:
                return False
            qualification = await qualification_in_transaction(
                db,
                graph,
                job,
                job.candidate_id,
                lock=True,
            )
            if qualification != result.qualification:
                raise DSLCandidateUnavailable()
            candidate = await db.get(DSLCandidate, job.candidate_id)
            record = await db.get(DSLReviewRecord, candidate.review_id) if candidate else None
            if record is None:
                raise DSLCandidateUnavailable()
            async with private_cache_lock(trusted_cache, lease.owner_id, job.cache_key):
                media = await asyncio.to_thread(
                    trusted_cache.publish_locked,
                    lease.owner_id,
                    job.cache_key,
                    qualification.compiled,
                    result.media,
                )
                values = dsl_media_values(job, qualification, record, media)
                await db.execute(
                    pg_insert(AnimationMedia)
                    .values(**values)
                    .on_conflict_do_nothing(index_elements=[AnimationMedia.cache_key])
                )
                saved = await db.scalar(
                    select(AnimationMedia).where(
                        AnimationMedia.cache_key == job.cache_key,
                    )
                )
                if saved is None or any(
                    getattr(saved, key) != value for key, value in values.items()
                ):
                    raise DSLCandidateUnavailable()
                if await _locked_current_job(db, lease) is None:
                    raise DSLCandidateUnavailable()
                job.media_id, job.status, job.progress = saved.id, "succeeded", 1.0
                job.lease_token = job.lease_expires_at = None
                await db.flush()
                bind_media(db, job, saved)
                await append_animation_event(
                    db,
                    owner_id=lease.owner_id,
                    job_id=job.id,
                    event_type="succeeded",
                    payload={"stage": "completed", "progress": 1.0, "media_id": str(saved.id)},
                )
                await db.commit()
            result.media.cleanup()
            return True
        except Exception:
            await db.rollback()
            raise


def dsl_media_values(
    job: AnimationJob,
    qualification: DSLRenderQualification,
    record: DSLReviewRecord,
    media: PrivateDSLMedia,
) -> dict[str, object]:
    return {
        "cache_key": job.cache_key,
        "render_kind": "dsl",
        "user_id": job.user_id,
        "candidate_id": job.candidate_id,
        "template_id": None,
        "template_version": None,
        "review_rule_version": job.review_rule_version,
        **{field: getattr(job, field) for field in RUNTIME_FIELDS},
        "mp4_sha256": media.mp4_sha256,
        "srt_sha256": media.srt_sha256,
        "mp4_size": media.mp4_path.stat().st_size,
        "srt_size": media.srt_path.stat().st_size,
        "duration_seconds": media.duration_seconds,
        "review_status": "passed",
        "source_versions": {
            "compiler_version": qualification.compiled.compiler_version,
            "binding": record.binding_sha256,
            **{
                key: record.evidence[key]
                for key in (
                    "schema",
                    "validator",
                    "compiler",
                    "compiler_policy",
                    "graph",
                    "reference",
                    "generation",
                    "review_source",
                )
                if key in record.evidence
            },
        },
    }
