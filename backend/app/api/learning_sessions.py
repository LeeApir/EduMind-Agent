"""POST SSE first-screen endpoint; temporary tokens are never formal resources."""

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, require_authenticated_session
from app.core.database import database_session_factory
from app.core.provider_factory import build_default_provider_gateway
from app.services.first_learning import prepare_first_learning
from app.services.learning_finalization import finalize_learning_unit
from app.services.learning_operations import (
    IdempotencyConflict,
    fail_interrupted_operation,
    operation_payload,
    owned_operation,
    reserve_operation,
    update_operation,
)
from app.services.provider_gateway import ProviderError, ProviderGateway, TextRequest

router = APIRouter(tags=["Learning"])


class StartLearningRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    preferred_language: str = "c"


def provider_gateway() -> ProviderGateway:
    """Resolve the one server-configured P0 provider at request time."""
    return build_default_provider_gateway()


def _event(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _safe_provider_error(error: ProviderError) -> dict[str, object]:
    return {
        "code": "PROVIDER_UNAVAILABLE",
        "message": str(error),
        "retryable": error.retryable,
    }


async def _first_screen_events(
    *,
    operation_id: UUID,
    prompt: TextRequest,
    gateway: ProviderGateway,
    session_factory: async_sessionmaker[AsyncSession],
    owner_id: UUID,
    goal: str,
    code_language: str,
) -> AsyncIterator[str]:
    operation = str(operation_id)
    yield _event("agent_start", {"operation_id": operation, "stage": "preparing"})
    async with session_factory() as db:
        persisted = await owned_operation(db, owner_id=owner_id, operation_id=operation_id)
        assert persisted is not None
        await update_operation(db, persisted, status="streaming_temporary")
    try:
        async for delta in gateway.stream_text(prompt):
            if delta.text.strip():
                yield _event(
                    "token",
                    {"operation_id": operation, "temporary": True, "delta": delta.text},
                )
    except ProviderError as error:
        async with session_factory() as db:
            persisted = await owned_operation(db, owner_id=owner_id, operation_id=operation_id)
            assert persisted is not None
            await update_operation(
                db, persisted, status="failed", error=_safe_provider_error(error)
            )
        yield _event("error", {**_safe_provider_error(error), "operation_id": operation})
        yield _event("done", {"operation_id": operation, "status": "failed"})
        return
    yield _event("stage_changed", {"operation_id": operation, "stage": "reviewing"})
    async with session_factory() as db:
        persisted = await owned_operation(db, owner_id=owner_id, operation_id=operation_id)
        assert persisted is not None
        await update_operation(db, persisted, status="reviewing")
    try:
        async with session_factory() as db:
            finalized = await finalize_learning_unit(
                db,
                owner_id=owner_id,
                goal=goal,
                code_language=code_language,
                gateway=gateway,
            )
    except (ProviderError, ValueError):
        async with session_factory() as db:
            persisted = await owned_operation(db, owner_id=owner_id, operation_id=operation_id)
            assert persisted is not None
            await update_operation(
                db,
                persisted,
                status="failed",
                error={"code": "FINALIZATION_UNAVAILABLE", "retryable": True},
            )
        yield _event(
            "error",
            {
                "code": "FINALIZATION_UNAVAILABLE",
                "message": "Reviewed learning resources are temporarily unavailable.",
                "retryable": True,
                "operation_id": operation,
            },
        )
        yield _event("done", {"operation_id": operation, "status": "failed"})
        return
    if not finalized.published:
        async with session_factory() as db:
            persisted = await owned_operation(db, owner_id=owner_id, operation_id=operation_id)
            assert persisted is not None
            await update_operation(db, persisted, status="failed")
        yield _event("review_reject", {"operation_id": operation, "attempt": 1, "retry": False})
        yield _event("done", {"operation_id": operation, "status": "failed"})
        return
    assert finalized.learning_unit_id is not None
    assert finalized.scene_id is not None
    assert finalized.scene_version is not None
    async with session_factory() as db:
        persisted = await owned_operation(db, owner_id=owner_id, operation_id=operation_id)
        assert persisted is not None
        await update_operation(
            db,
            persisted,
            status="published",
            learning_unit_id=finalized.learning_unit_id,
            scene_id=finalized.scene_id,
            scene_version=finalized.scene_version,
        )
    yield _event("review_pass", {"operation_id": operation, "attempt": 1})
    yield _event(
        "scene_ready",
        {
            "operation_id": operation,
            "learning_unit_id": str(finalized.learning_unit_id),
            "scene_id": str(finalized.scene_id),
            "version": finalized.scene_version,
            "resource_ids": [str(resource_id) for resource_id in finalized.resource_ids],
        },
    )
    yield _event("done", {"operation_id": operation, "status": "published"})


@router.post("/api/learning-sessions")
async def start_learning_session(
    payload: StartLearningRequest,
    _request: Request,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    gateway: ProviderGateway = Depends(provider_gateway),
) -> StreamingResponse:
    """Persist only the profile, then stream explicitly temporary first learning content."""
    async with session_factory() as db:
        try:
            reservation = await reserve_operation(
                db,
                owner_id=current.user.id,
                idempotency_key=idempotency_key,
                goal=payload.goal,
                preferred_language=payload.preferred_language,
            )
        except IdempotencyConflict:
            from app.core.auth import AuthFailure

            raise AuthFailure(409, "IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
        if not reservation.created:
            return StreamingResponse(
                _replay_operation_events(reservation.operation),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
            )
        prepared = await prepare_first_learning(
            db, owner_id=current.user.id, goal=payload.goal, gateway=gateway
        )
    return StreamingResponse(
        _first_screen_events(
            operation_id=reservation.operation.id,
            prompt=prepared.prompt,
            gateway=gateway,
            session_factory=session_factory,
            owner_id=current.user.id,
            goal=payload.goal,
            code_language=payload.preferred_language,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def _replay_operation_events(operation: object) -> AsyncIterator[str]:
    """Return only durable state on an idempotent retry; temporary text is never replayed."""
    from app.models.learning import LearningOperation

    assert isinstance(operation, LearningOperation)
    operation_id = str(operation.id)
    yield _event("agent_start", {"operation_id": operation_id, "stage": operation.status})
    yield _event("done", {"operation_id": operation_id, "status": operation.status})


@router.get("/api/learning-operations/{operation_id}")
async def get_learning_operation(
    operation_id: UUID,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with session_factory() as db:
        operation = await owned_operation(db, owner_id=current.user.id, operation_id=operation_id)
        if operation is None:
            from app.core.auth import AuthFailure

            raise AuthFailure(404, "NOT_FOUND", "Resource not found.")
        await fail_interrupted_operation(db, operation)
        return operation_payload(operation)
