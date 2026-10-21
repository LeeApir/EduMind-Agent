"""Lease-bound render step for a persisted approved candidate; T028 owns Job/publication APIs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.animation_dsl_review import REVIEW_VERSION, digest
from app.models.animation import AnimationJob
from app.models.animation_dsl import DSLReviewRecord
from app.services.animation_dsl_candidates import DSLCandidateUnavailable, qualified_candidate
from app.services.animation_dsl_compiler import CompiledDSL, compile_animation_dsl
from app.services.animation_dsl_renderer import render_compiled_dsl, renderer_identity
from app.services.animation_dsl_runtime import FONT_DIGEST, IMAGE
from app.services.animation_host import RenderHost
from app.services.animation_renderer import RenderedCandidate, RenderError
from app.services.animation_worker import (
    JobLease,
    _heartbeat_until_stopped,
    _locked_current_job,
    fail_animation_job,
    report_animation_progress,
)
from app.services.knowledge_graph import KnowledgeGraphRepository


@dataclass(frozen=True)
class DSLRenderQualification:
    candidate_id: UUID
    compiled: CompiledDSL = field(repr=False)
    binding_sha256: str
    cache_key: str


@dataclass(frozen=True)
class DSLRenderResult:
    media: RenderedCandidate | None = field(default=None, repr=False)
    qualification: DSLRenderQualification | None = field(default=None, repr=False)
    error_code: str | None = None


def dsl_cache_key(compiled: CompiledDSL, binding_sha256: str, owner_id: UUID) -> str:
    return digest(
        {
            "owner_namespace": digest({"private_dsl_owner_v1": str(owner_id)}),
            "compiler_identity": compiled.identity_sha256,
            "binding": binding_sha256,
            "renderer": renderer_identity(),
            "review_version": REVIEW_VERSION,
            "image": IMAGE,
            "font_digest": FONT_DIGEST,
        }
    )


async def qualify_dsl_job(
    sessions: async_sessionmaker[AsyncSession],
    graph: KnowledgeGraphRepository,
    lease: JobLease,
    candidate_id: UUID,
) -> DSLRenderQualification:
    # No host lock/container call is made while this transaction holds the Job row.
    async with sessions() as db:
        job = await _locked_current_job(db, lease)
        if job is None:
            raise DSLCandidateUnavailable()
        return await qualification_in_transaction(db, graph, job, candidate_id)


async def qualification_in_transaction(
    db: AsyncSession,
    graph: KnowledgeGraphRepository,
    job: AnimationJob,
    candidate_id: UUID,
    *,
    lock: bool = False,
) -> DSLRenderQualification:
    if (
        job.render_kind != "dsl"
        or job.candidate_id != candidate_id
        or job.template_id is not None
        or job.template_version is not None
        or job.parameters != {"candidate_id": str(candidate_id)}
    ):
        raise DSLCandidateUnavailable()
    candidate = await qualified_candidate(
        db, graph, owner=job.user_id, candidate_id=candidate_id, lock=lock
    )
    if (candidate.learning_unit_id, candidate.scene_id, candidate.scene_version) != (
        job.learning_unit_id,
        job.scene_id,
        job.scene_version,
    ):
        raise DSLCandidateUnavailable()
    record = await db.get(DSLReviewRecord, candidate.review_id)
    if record is None:
        raise DSLCandidateUnavailable()
    compiled = await asyncio.to_thread(
        compile_animation_dsl,
        candidate.canonical_dsl,
        knowledge_point_id=job_knowledge_point(candidate.canonical_dsl),
    )
    key = dsl_cache_key(compiled, record.binding_sha256, job.user_id)
    if (
        record.evidence.get("identity") != compiled.identity_sha256
        or record.evidence.get("compiled_source") != compiled.source_sha256
        or job.cache_key != key
        or job.source_sha256 != compiled.source_sha256
        or job.review_rule_version != REVIEW_VERSION
        or job.image_digest != IMAGE.split("@", 1)[1]
        or job.font_digest != FONT_DIGEST
        or job.renderer_config_sha256 != renderer_identity()
        or job.subtitle_version != "animation-dsl-subtitles-v1"
    ):
        raise DSLCandidateUnavailable()
    return DSLRenderQualification(candidate_id, compiled, record.binding_sha256, key)


def job_knowledge_point(raw: str) -> str:
    import json

    value = json.loads(raw)["knowledge_point_id"]
    if type(value) is not str:
        raise DSLCandidateUnavailable()
    return value


async def render_dsl_job(
    sessions: async_sessionmaker[AsyncSession],
    graph: KnowledgeGraphRepository,
    lease: JobLease,
    candidate_id: UUID,
    *,
    work_root: Path | None = None,
    complete: Callable[[DSLRenderResult], Awaitable[bool]] | None = None,
    failure: Callable[[str], Awaitable[bool]] | None = None,
) -> DSLRenderResult:
    controller = RenderHost(sessions, lease.token, asyncio.get_running_loop())
    stop = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat_until_stopped(sessions, lease, stop))
    media = None
    render_task: asyncio.Task[RenderedCandidate] | None = None
    try:
        qualification = await qualify_dsl_job(sessions, graph, lease, candidate_id)
        render_task = asyncio.create_task(
            asyncio.to_thread(
                render_compiled_dsl,
                qualification.compiled,
                work_root=work_root,
                container_name=lease.container_name,
                controller=controller,
            )
        )
        media = await asyncio.shield(render_task)
        if not await report_animation_progress(sessions, lease, stage="validating", progress=0.8):
            media.cleanup()
            media = None
            return DSLRenderResult(error_code="DSL_RENDER_UNAVAILABLE")
        refreshed = await qualify_dsl_job(sessions, graph, lease, candidate_id)
        if refreshed != qualification:
            raise DSLCandidateUnavailable()
        result = DSLRenderResult(media, qualification)
        # T028 publication callback checks binding/current qualification with heartbeat alive.
        if complete is not None and not await complete(result):
            raise DSLCandidateUnavailable()
        return result  # Rendering success alone does not mark Job succeeded or grant media access.
    except asyncio.CancelledError:
        if failure is None:
            await fail_animation_job(sessions, lease, code="DSL_RENDER_INTERRUPTED")
        else:
            await failure("DSL_RENDER_INTERRUPTED")
        await asyncio.to_thread(controller.stop)
        # Cancelling an asyncio waiter does not stop its thread. Reap any late local output.
        if render_task is not None:
            try:
                late_media = await render_task
                late_media.cleanup()
            except Exception:
                pass
        if media is not None:
            media.cleanup()
        raise
    except Exception as error:
        if media is not None:
            media.cleanup()
        code = str(error) if isinstance(error, RenderError) else "DSL_RENDER_UNAVAILABLE"
        if code not in {
            "DSL_RENDER_UNAVAILABLE",
            "DSL_COMPILE_REJECTED",
            "DSL_RENDER_TIMEOUT",
            "DSL_RENDER_FAILED",
            "DSL_MEDIA_INVALID",
            "DSL_RENDER_RESOURCE_LIMIT",
        }:
            code = "DSL_RENDER_UNAVAILABLE"
        if failure is None:
            await fail_animation_job(sessions, lease, code=code)
        else:
            await failure(code)
        return DSLRenderResult(error_code=code)
    finally:
        stop.set()
        await heartbeat
        await asyncio.to_thread(controller.stop)
