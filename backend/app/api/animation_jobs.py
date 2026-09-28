"""Authenticated on-demand animation creation and durable Job lifecycle API."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.models.animation import AnimationJob
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_cache import AnimationCache
from app.services.animation_jobs import (
    AnimationIdempotencyConflict,
    AnimationTargetUnavailable,
    animation_request_digest,
    reserve_animation_job,
)
from app.services.animation_lifecycle import (
    AnimationJobStateConflict,
    cancel_animation_job,
    owned_animation_job,
    retry_animation_job,
)

router = APIRouter(tags=["Animation"])


class AnimationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: Literal["linked-list-insertion", "linked-list-deletion"]
    template_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", max_length=40)
    scene_version: int = Field(ge=1)
    parameters: dict[str, object]


def animation_job_payload(job: AnimationJob) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(job.id), "status": job.status,
        "learning_unit_id": str(job.learning_unit_id),
        "template_id": job.template_id, "attempt": job.attempt,
        "progress": job.progress, "last_event_id": job.last_event_id,
    }
    if job.media_id is not None:
        payload["media_id"] = str(job.media_id)
    if job.retry_of is not None:
        payload["retry_of"] = str(job.retry_of)
    if job.error_code is not None:
        payload["error"] = {
            "code": job.error_code, "message": "Animation is unavailable.",
            "retryable": job.status == "failed",
        }
    return payload


def _not_found() -> AuthFailure:
    return AuthFailure(404, "NOT_FOUND", "Animation job or target not found.")


def _conflict(code: str) -> AuthFailure:
    return AuthFailure(409, code, "Animation request conflicts with its current state.")


@router.post("/api/learning-units/{unit_id}/animations")
async def request_animation(
    unit_id: UUID, payload: AnimationRequest, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        existing = await db.scalar(select(AnimationJob).where(
            AnimationJob.user_id == current.user.id,
            AnimationJob.action_kind == "request",
            AnimationJob.idempotency_key == idempotency_key,
        ))
        if existing is not None:
            digest = animation_request_digest(
                learning_unit_id=unit_id, scene_id=existing.scene_id,
                scene_version=payload.scene_version,
                template_id=payload.template_id,
                template_version=payload.template_version,
                parameters=payload.parameters,
            )
            if existing.request_digest != digest:
                raise _conflict("IDEMPOTENCY_CONFLICT")
            response.headers["Cache-Control"] = "no-store"
            return animation_job_payload(existing)
        target = await db.scalar(select(LearningScene).join(
            LearningUnit, LearningUnit.id == LearningScene.learning_unit_id,
        ).where(
            LearningUnit.id == unit_id,
            LearningUnit.user_id == current.user.id,
            LearningUnit.knowledge_point_id == payload.template_id,
            LearningUnit.status == "ready",
            LearningScene.scene_key == "intro",
            LearningScene.version == payload.scene_version,
            LearningScene.generation_status == "complete",
            LearningScene.review_status == "passed",
        ))
        if target is None:
            raise _not_found()
        try:
            reservation = await reserve_animation_job(
                db, owner_id=current.user.id, learning_unit_id=unit_id,
                scene_id=target.id, scene_version=payload.scene_version,
                template_id=payload.template_id, template_version=payload.template_version,
                parameters=payload.parameters, idempotency_key=idempotency_key,
                cache=AnimationCache(),
            )
        except AnimationIdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT") from None
        except AnimationTargetUnavailable:
            raise _not_found() from None
        except ValueError:
            raise AuthFailure(422, "VALIDATION_ERROR", "Invalid animation parameters.") from None
    response.headers["Cache-Control"] = "no-store"
    response.status_code = (
        200 if not reservation.created or reservation.job.status == "succeeded" else 202
    )
    return animation_job_payload(reservation.job)


@router.get("/api/animation-jobs/{job_id}")
async def get_animation_job(
    job_id: UUID, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        try:
            job = await owned_animation_job(db, owner_id=current.user.id, job_id=job_id)
        except AnimationTargetUnavailable:
            raise _not_found() from None
        result = animation_job_payload(job)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/api/animation-jobs/{job_id}/cancel")
async def cancel_animation(
    job_id: UUID, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        try:
            job = await cancel_animation_job(
                db, owner_id=current.user.id, job_id=job_id,
                idempotency_key=idempotency_key,
            )
        except AnimationTargetUnavailable:
            raise _not_found() from None
        except AnimationIdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT") from None
        except AnimationJobStateConflict:
            raise _conflict("JOB_STATE_CONFLICT") from None
    response.headers["Cache-Control"] = "no-store"
    return animation_job_payload(job)


@router.post("/api/animation-jobs/{job_id}/retry")
async def retry_animation(
    job_id: UUID, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        try:
            job, created = await retry_animation_job(
                db, owner_id=current.user.id, job_id=job_id,
                idempotency_key=idempotency_key,
            )
        except AnimationTargetUnavailable:
            raise _not_found() from None
        except AnimationIdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT") from None
        except AnimationJobStateConflict:
            raise _conflict("JOB_STATE_CONFLICT") from None
    response.headers["Cache-Control"] = "no-store"
    response.status_code = 202 if created else 200
    return animation_job_payload(job)
