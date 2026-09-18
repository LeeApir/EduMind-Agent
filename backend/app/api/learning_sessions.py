"""POST SSE first-screen endpoint; temporary tokens are never formal resources."""

import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, require_authenticated_session
from app.core.database import database_session_factory
from app.core.provider_factory import build_default_provider_gateway
from app.services.first_learning import prepare_first_learning
from app.services.learning_finalization import finalize_learning_unit
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
    try:
        async for delta in gateway.stream_text(prompt):
            if delta.text.strip():
                yield _event(
                    "token",
                    {"operation_id": operation, "temporary": True, "delta": delta.text},
                )
    except ProviderError as error:
        yield _event("error", {**_safe_provider_error(error), "operation_id": operation})
        yield _event("done", {"operation_id": operation, "status": "failed"})
        return
    yield _event("stage_changed", {"operation_id": operation, "stage": "reviewing"})
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
        yield _event("review_reject", {"operation_id": operation, "attempt": 1, "retry": False})
        yield _event("done", {"operation_id": operation, "status": "failed"})
        return
    assert finalized.learning_unit_id is not None
    assert finalized.scene_id is not None
    assert finalized.scene_version is not None
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
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    gateway: ProviderGateway = Depends(provider_gateway),
) -> StreamingResponse:
    """Persist only the profile, then stream explicitly temporary first learning content."""
    async with session_factory() as db:
        prepared = await prepare_first_learning(
            db, owner_id=current.user.id, goal=payload.goal, gateway=gateway
        )
    return StreamingResponse(
        _first_screen_events(
            operation_id=uuid4(),
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
