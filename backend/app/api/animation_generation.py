"""Owner/CSRF-bound API preparation SSE and immutable-session snapshots/cancellation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.provider_connections import (
    ProviderRoute,
    StrictInput,
    identity,
    provider_store,
    request_registry,
)
from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.credential_crypto import CredentialFailure
from app.core.database import database_session_factory
from app.core.product_mode import require_dynamic_mode
from app.models.animation_generation import AnimationPreparation
from app.models.learning import LearningScene
from app.services.animation_cache import AnimationCache
from app.services.animation_dsl_candidate_cache import ReviewedDSLCandidateCache
from app.services.animation_dsl_candidates import DSLCandidateUnavailable, build_dsl_reference
from app.services.animation_dsl_flow import DSLCallBudget, SelectedDSLFlow, UnavailableDSLCallBudget
from app.services.animation_dsl_handoff import handoff_video_plan
from app.services.animation_intent import VideoIntent
from app.services.animation_job_qualification import current_animation_graph
from app.services.animation_jobs import AnimationIdempotencyConflict, AnimationTargetUnavailable
from app.services.animation_preparation import (
    AnimationPreparationLimit,
    advance_preparation,
    cancel_preparation,
    fail_preparation,
    owned_preparation,
    preparation_payload,
    reserve_preparation,
)
from app.services.owned_learning import visible_unit
from app.services.provider_connections import ProviderConnectionStore
from app.services.provider_gateway import ProviderError
from app.services.video_dsl_generation import VideoDSLPlanner

router = APIRouter(
    tags=["Animation"], route_class=ProviderRoute, dependencies=[Depends(require_dynamic_mode)]
)


class AnimationGenerateRequest(StrictInput):
    scene_id: UUID = Field(strict=False)
    scene_version: int = Field(ge=1)
    goal_kind: Literal[
        "compare", "swap", "traverse", "insert", "delete", "trace_insert", "trace_delete"
    ]
    parameters: dict[str, object]

    @field_validator("parameters", mode="before")
    @classmethod
    def bounded_parameters(cls, value: object) -> object:
        if type(value) is not dict or set(value) - {"values", "index", "value"}:
            raise ValueError("Invalid animation parameters")
        values = value.get("values")
        if type(values) is not list or len(values) > 8:
            raise ValueError("Invalid animation parameters")
        if any(type(item) is not int or not -999 <= item <= 999 for item in values):
            raise ValueError("Invalid animation parameters")
        if any(
            type(item) is not int or not -999 <= item <= 999
            for key, item in value.items()
            if key != "values"
        ):
            raise ValueError("Invalid animation parameters")
        return value


_ALLOWED = {
    "array": {"compare", "swap", "traverse"},
    "single-linked-list": {"compare", "traverse"},
    "linked-list-concept": {"compare", "traverse"},
    "linked-list-traversal": {"traverse"},
    "linked-list-insertion": {"insert", "trace_insert"},
    "linked-list-deletion": {"delete", "trace_delete"},
}


def dsl_call_budget() -> DSLCallBudget:
    return UnavailableDSLCallBudget()


def dsl_transport() -> httpx.AsyncBaseTransport | None:
    return None


def _event(event: str, value: dict[str, object]) -> str:
    return "event: " + event + "\ndata: " + json.dumps(value, ensure_ascii=True) + "\n\n"


def _unavailable() -> AuthFailure:
    return AuthFailure(404, "NOT_FOUND", "Animation preparation or target not found.")


@router.post("/api/learning-units/{unit_id}/animations/generate", operation_id="generateAnimation")
async def generate_animation(
    unit_id: UUID,
    payload: AnimationGenerateRequest,
    request: Request,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    store: ProviderConnectionStore = Depends(provider_store),
    budget: DSLCallBudget = Depends(dsl_call_budget),
    transport: httpx.AsyncBaseTransport | None = Depends(dsl_transport),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    operation_id: UUID = Header(alias="X-Animation-Operation-ID"),
    quality_handle: str | None = Header(
        default=None, min_length=32, max_length=200, alias="X-Animation-Quality-Handle"
    ),
    review_handle: str | None = Header(
        default=None, min_length=32, max_length=200, alias="X-Animation-Review-Handle"
    ),
    allow_fallback: bool = Header(default=False, alias="X-Animation-Allow-Template-Fallback"),
) -> StreamingResponse:
    graph = current_animation_graph()
    async with sessions() as db:
        unit = await visible_unit(db, current.user.id, unit_id)
        scene = await db.scalar(
            select(LearningScene).where(
                LearningScene.id == payload.scene_id,
                LearningScene.learning_unit_id == unit_id,
                LearningScene.version == payload.scene_version,
                LearningScene.generation_status == "complete",
                LearningScene.review_status == "passed",
            )
        )
        if unit is None or scene is None or unit.knowledge_point_id is None:
            raise _unavailable()
        if payload.goal_kind not in _ALLOWED.get(unit.knowledge_point_id, set()):
            raise AuthFailure(
                422, "VALIDATION_ERROR", "Animation goal is unavailable for this target."
            )
        try:
            operation = payload.goal_kind.removeprefix("trace_")
            intent = VideoIntent(
                unit.knowledge_point_id,
                operation,  # type: ignore[arg-type]
                json.dumps(payload.parameters, allow_nan=False),
                "detailed_trace" if payload.goal_kind.startswith("trace_") else "standard",
            )
            intent.payload()
            reservation = await reserve_preparation(
                db,
                graph,
                owner=current.user.id,
                session_hash=current.record.token_hash,
                unit_id=unit_id,
                scene_id=payload.scene_id,
                scene_version=payload.scene_version,
                intent=intent,
                idempotency_key=idempotency_key,
                allow_template_fallback=allow_fallback,
                operation_id=operation_id,
            )
        except (ValueError, TypeError) as error:
            if isinstance(error, AnimationPreparationLimit):
                raise AuthFailure(
                    429, "ANIMATION_PREPARATION_LIMIT", "Too many active animations."
                ) from None
            if isinstance(error, AnimationIdempotencyConflict):
                raise AuthFailure(
                    409, "IDEMPOTENCY_CONFLICT", "Animation request conflicts."
                ) from None
            if isinstance(error, (AnimationTargetUnavailable, DSLCandidateUnavailable)):
                raise _unavailable() from None
            raise AuthFailure(422, "VALIDATION_ERROR", "Invalid animation parameters.") from None
    return StreamingResponse(
        _preparation_events(
            reservation.operation,
            created=reservation.created,
            current=current,
            store=store,
            sessions=sessions,
            intent=intent,
            request=request,
            budget=budget,
            transport=transport,
            quality_handle=quality_handle,
            review_handle=review_handle,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"},
    )


async def _preparation_events(
    operation: AnimationPreparation,
    *,
    created: bool,
    current: AuthenticatedSession,
    store: ProviderConnectionStore,
    sessions: async_sessionmaker[AsyncSession],
    intent: VideoIntent,
    request: Request,
    budget: DSLCallBudget,
    transport: httpx.AsyncBaseTransport | None,
    quality_handle: str | None,
    review_handle: str | None,
) -> AsyncIterator[str]:
    actor: asyncio.Task[None] | None = None
    changes: asyncio.Queue[str] = asyncio.Queue(maxsize=8)
    try:
        yield _event("agent_start", preparation_payload(operation))
        if created:
            actor = asyncio.create_task(
                _execute_preparation(
                    operation,
                    current=current,
                    store=store,
                    sessions=sessions,
                    intent=intent,
                    request=request,
                    budget=budget,
                    transport=transport,
                    quality_handle=quality_handle,
                    review_handle=review_handle,
                    changes=changes,
                )
            )
        while True:
            async with sessions() as db:
                row = await owned_preparation(
                    db,
                    owner=current.user.id,
                    session_hash=current.record.token_hash,
                    operation_id=operation.id,
                    lock=True,
                )
                snapshot = preparation_payload(row)
                await db.commit()
            if snapshot["stage"] in {"handed_off", "failed", "cancelled"}:
                if actor is not None:
                    await asyncio.gather(actor, return_exceptions=True)
                yield _event("done", snapshot)
                return
            try:
                phase = await asyncio.wait_for(changes.get(), timeout=0.25)
                yield _event("stage_changed", {"id": str(operation.id), "stage": phase})
            except TimeoutError:
                if actor is not None and actor.done():
                    # A dead holder never restarts model work. Fail a still-active receipt safely.
                    async with sessions() as db:
                        await fail_preparation(
                            db,
                            owner=current.user.id,
                            operation_id=operation.id,
                            execution_token=operation.execution_token,
                            code="ANIMATION_UNAVAILABLE",
                        )
    except (AnimationTargetUnavailable, CredentialFailure):
        yield _event(
            "done",
            {
                "id": str(operation.id),
                "stage": "failed",
                "deadline": operation.deadline.isoformat(),
                "error_code": "ANIMATION_UNAVAILABLE",
            },
        )
    finally:
        if created:
            if actor is not None and not actor.done():
                actor.cancel()
            if quality_handle or review_handle:
                request_registry(request).retire_operation(
                    current.user.id,
                    current.record.token_hash,
                    operation.id,
                )

            async def cleanup() -> None:
                if actor is not None:
                    await asyncio.gather(actor, return_exceptions=True)
                async with sessions() as db:
                    try:
                        await cancel_preparation(
                            db,
                            owner=current.user.id,
                            session_hash=current.record.token_hash,
                            operation_id=operation.id,
                            execution_token=operation.execution_token,
                        )
                    except (AnimationTargetUnavailable, CredentialFailure):
                        await fail_preparation(
                            db,
                            owner=current.user.id,
                            operation_id=operation.id,
                            execution_token=operation.execution_token,
                            code="ANIMATION_PREPARATION_EXPIRED",
                        )

            # ASGI disconnect cancellation is level-triggered. A separate shielded cleanup
            # task finishes the PG CAS even when the original request can no longer await.
            await asyncio.shield(asyncio.create_task(cleanup()))


async def _execute_preparation(
    operation: AnimationPreparation,
    *,
    current: AuthenticatedSession,
    store: ProviderConnectionStore,
    sessions: async_sessionmaker[AsyncSession],
    intent: VideoIntent,
    request: Request,
    budget: DSLCallBudget,
    transport: httpx.AsyncBaseTransport | None,
    quality_handle: str | None,
    review_handle: str | None,
    changes: asyncio.Queue[str],
) -> None:
    graph = current_animation_graph()
    registry = request_registry(request) if quality_handle or review_handle else None

    async def stage(phase: str) -> None:
        changes.put_nowait(phase)

    flow = SelectedDSLFlow(
        store,
        graph,
        operation,
        identity(current),
        budget,
        quality_handle=quality_handle,
        review_handle=review_handle,
        registry=registry,
        transport=transport,
        stage_changed=stage,
    )
    owner_task = asyncio.current_task()
    assert owner_task is not None
    stop = asyncio.Event()

    async def observe() -> None:
        while not stop.is_set():
            await asyncio.sleep(0.5)
            if stop.is_set():
                return
            async with sessions() as db:
                row = await db.get(AnimationPreparation, operation.id)
                if row is not None and row.stage == "handed_off":
                    return
            try:
                async with asyncio.timeout(1):
                    alive = await flow.live()
            except Exception:
                alive = False
            if not alive:
                owner_task.cancel()
                return

    watcher = asyncio.create_task(observe())
    try:
        async with sessions() as db:
            reference = await build_dsl_reference(
                db,
                graph,
                owner=current.user.id,
                unit_id=operation.learning_unit_id,
                scene_id=operation.scene_id,
                version=operation.scene_version,
            )
        reviewed = None
        try:
            sources = await flow.freeze_sources()
            reviewed = ReviewedDSLCandidateCache(
                sessions, graph, owner=current.user.id, expected_sources=sources
            )
        except (CredentialFailure, ProviderError):
            pass  # Applicable templates can be selected without a model route or credential.
        planner = VideoDSLPlanner(flow.generator(), cache=AnimationCache(), reviewed_cache=reviewed)
        plan = await planner.plan(intent, reference=reference, dynamic_allowed=True)
        if plan.source in {"generated_dsl", "reviewed_dsl_cache"}:
            await flow.validate_sources()
            async with sessions() as db:
                if not await advance_preparation(
                    db,
                    graph,
                    owner=current.user.id,
                    session_hash=current.record.token_hash,
                    operation_id=operation.id,
                    execution_token=operation.execution_token,
                    stage="compiled",
                ):
                    return
            await stage("compiled")
        await flow.close()  # No credential survives the no-model handoff transaction.
        async with sessions() as db:
            await handoff_video_plan(
                db,
                graph,
                owner=current.user.id,
                session_hash=current.record.token_hash,
                operation_id=operation.id,
                execution_token=operation.execution_token,
                plan=plan,
                template_cache=AnimationCache(),
                source_validator=flow.validate_handoff_sources,
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        async with sessions() as db:
            await fail_preparation(
                db,
                owner=current.user.id,
                operation_id=operation.id,
                execution_token=operation.execution_token,
                code="ANIMATION_UNAVAILABLE",
            )
    finally:
        stop.set()
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        await flow.close()


@router.get("/api/animation-preparations/{operation_id}", operation_id="getAnimationPreparation")
async def get_preparation(
    operation_id: UUID,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        try:
            row = await owned_preparation(
                db,
                owner=current.user.id,
                session_hash=current.record.token_hash,
                operation_id=operation_id,
                lock=True,
            )
        except AnimationTargetUnavailable:
            raise _unavailable() from None
        payload = preparation_payload(row)
        await db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return payload


@router.post(
    "/api/animation-preparations/{operation_id}/cancel", operation_id="cancelAnimationPreparation"
)
async def cancel_generation(
    operation_id: UUID,
    request: Request,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
) -> dict[str, object]:
    async with sessions() as db:
        try:
            row = await cancel_preparation(
                db,
                owner=current.user.id,
                session_hash=current.record.token_hash,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
            )
        except AnimationIdempotencyConflict:
            raise AuthFailure(
                409, "IDEMPOTENCY_CONFLICT", "Animation cancellation conflicts."
            ) from None
        except AnimationTargetUnavailable:
            raise _unavailable() from None
        payload = preparation_payload(row)
    if row.stage == "cancelled":
        request_registry(request).retire_operation(
            current.user.id, current.record.token_hash, row.id
        )
    response.headers["Cache-Control"] = "private, no-store"
    return payload
