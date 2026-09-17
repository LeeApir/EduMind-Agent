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
    *, operation_id: UUID, prompt: TextRequest, gateway: ProviderGateway
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
    yield _event("done", {"operation_id": operation, "status": "temporary_complete"})


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
        _first_screen_events(operation_id=uuid4(), prompt=prepared.prompt, gateway=gateway),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
