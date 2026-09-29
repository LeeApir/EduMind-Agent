"""Reviewed array-versus-linked-list demonstration and classroom return API."""

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.debate_candidate_generator import (
    DebateCandidateGenerator,
    DebateCandidateRequest,
    DebateGenerationFailure,
    DebateGenerationInputError,
)
from app.agents.debate_candidate_schema import DebateCandidateSchemaError
from app.agents.debate_review import DebateReviewAgent
from app.api.classroom import provider_gateway
from app.api.knowledge_graph import knowledge_graph_repository
from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.models.learning import utc_now
from app.services.classroom import ClassroomNotFound, ClassroomVersionConflict
from app.services.debate_publication import (
    DebateAlreadyActive,
    DebateReservation,
    debate_materials,
    debate_result_payload,
    exit_debate,
    fail_debate,
    owned_debate_result,
    publish_debate,
    reserve_debate,
)
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_operations import IdempotencyConflict
from app.services.provider_gateway import ProviderErrorCode, ProviderGateway

router = APIRouter(tags=["Classroom"])


class DebateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: str = Field(pattern="^array-vs-linked-list$")
    question: str = Field(min_length=1, max_length=1000)


def _event(name: str, data: dict[str, object]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _not_found() -> AuthFailure:
    return AuthFailure(404, "NOT_FOUND", "Debate result or classroom not found.")


def _conflict(code: str, message: str) -> AuthFailure:
    return AuthFailure(409, code, message)


def _stream_response(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events, media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def _run_debate_events(
    *, reservation: DebateReservation, profile: dict[str, object] | None,
    profile_version: int | None, graph: KnowledgeGraphRepository,
    gateway: ProviderGateway, owner_id: UUID,
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[str]:
    operation = reservation.operation
    snapshot = operation.result_snapshot or {}
    question = snapshot.get("question")
    assert isinstance(question, str)
    yield _event("agent_start", {
        "operation_id": str(operation.id), "revision": operation.base_revision,
        "scene_version": reservation.session.scene_version,
        "generation_id": str(operation.generation_id) if operation.generation_id else None,
    })
    async with sessions() as db:
        persisted = await db.get(type(operation), operation.id)
        if persisted is not None and persisted.status == "accepted":
            persisted.status = "running"
            persisted.updated_at = utc_now()
            await db.commit()
    try:
        candidate = await DebateCandidateGenerator(gateway).generate(DebateCandidateRequest(
            preset="array-vs-linked-list", question=question, graph=graph,
            profile=profile, profile_version=profile_version,
        ))
    except DebateGenerationInputError:
        async with sessions() as db:
            await fail_debate(db, owner_id=owner_id, operation_id=operation.id,
                              code="DEBATE_CONTEXT_UNAVAILABLE")
        yield _event("error", {"code": "DEBATE_CONTEXT_UNAVAILABLE", "retryable": False})
        yield _event("done", {"status": "failed"})
        return
    if isinstance(candidate, DebateGenerationFailure):
        invalid = candidate.code is ProviderErrorCode.INVALID_OUTPUT
        retryable = candidate.code in {
            ProviderErrorCode.RATE_LIMITED,
            ProviderErrorCode.TEMPORARILY_UNAVAILABLE,
            ProviderErrorCode.TIMEOUT,
        }
        code = "DEBATE_INVALID_OUTPUT" if invalid else "PROVIDER_UNAVAILABLE"
        async with sessions() as db:
            await fail_debate(db, owner_id=owner_id, operation_id=operation.id,
                              code=code, retryable=retryable)
        yield _event("error", {"code": code, "retryable": retryable})
        yield _event("done", {"status": "failed"})
        return
    yield _event("stage_changed", {"operation_id": str(operation.id), "stage": "reviewing"})
    review = await DebateReviewAgent(gateway).review(candidate)
    if not review.approved:
        code = "REVIEW_UNAVAILABLE" if review.unavailable else "REVIEW_REJECTED"
        async with sessions() as db:
            await fail_debate(db, owner_id=owner_id, operation_id=operation.id,
                              code=code, retryable=review.unavailable)
        yield _event("error", {"code": code, "retryable": review.unavailable})
        yield _event("done", {"status": "failed"})
        return
    try:
        async with sessions() as db:
            result = await publish_debate(
                db, owner_id=owner_id, operation_id=operation.id, review=review,
            )
    except (DebateCandidateSchemaError, ValueError):
        async with sessions() as db:
            await fail_debate(db, owner_id=owner_id, operation_id=operation.id,
                              code="DEBATE_PUBLICATION_FAILED")
        yield _event("error", {"code": "DEBATE_PUBLICATION_FAILED", "retryable": False})
        yield _event("done", {"status": "failed"})
        return
    if result is None:
        yield _event("error", {"code": "CLASSROOM_VERSION_CONFLICT", "retryable": False})
        yield _event("done", {"status": "cancelled"})
        return
    yield _event("review_pass", {"operation_id": str(operation.id), "kind": "debate"})
    yield _event("debate_ready", {
        "operation_id": str(operation.id), "result_id": str(result.id),
        "revision": operation.base_revision + 1,
    })
    yield _event("done", {"status": "published"})


async def _debate_events(
    *, reservation: DebateReservation, profile: dict[str, object] | None,
    profile_version: int | None, graph: KnowledgeGraphRepository,
    gateway: ProviderGateway, owner_id: UUID,
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[str]:
    try:
        async for event in _run_debate_events(
            reservation=reservation, profile=profile,
            profile_version=profile_version, graph=graph,
            gateway=gateway, owner_id=owner_id, sessions=sessions,
        ):
            yield event
    finally:
        # A disconnected client or unexpected exception must not leave a running
        # operation blocking every later demonstration for this classroom.
        async with sessions() as db:
            await fail_debate(
                db, owner_id=owner_id, operation_id=reservation.operation.id,
                code="DEBATE_INTERRUPTED", retryable=True,
            )


@router.post("/api/learning-units/{unit_id}/classroom/debate", response_model=None)
async def start_debate(
    unit_id: UUID, payload: DebateRequest,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    if_match_revision: int = Header(ge=1, alias="If-Match-Classroom-Revision"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    gateway: ProviderGateway = Depends(provider_gateway),
    graph: KnowledgeGraphRepository = Depends(knowledge_graph_repository),
) -> StreamingResponse:
    async with sessions() as db:
        try:
            reservation = await reserve_debate(
                db, owner_id=current.user.id, unit_id=unit_id, preset=payload.preset,
                question=payload.question, idempotency_key=idempotency_key,
                expected_revision=if_match_revision,
            )
        except IdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
        except ClassroomVersionConflict as error:
            raise _conflict("CLASSROOM_VERSION_CONFLICT",
                            f"Classroom revision is now {error.current_revision}.") from None
        except DebateAlreadyActive:
            raise _conflict("DEBATE_ALREADY_ACTIVE", "A debate is already active.") from None
        except ClassroomNotFound:
            raise _not_found() from None
        except ValueError:
            raise AuthFailure(422, "VALIDATION_ERROR", "Unsupported debate request.") from None
        if not reservation.created:
            async def replay() -> AsyncIterator[str]:
                operation = reservation.operation
                yield _event("agent_start", {
                    "operation_id": str(operation.id), "revision": operation.base_revision,
                    "scene_version": reservation.session.scene_version,
                    "generation_id": str(operation.generation_id)
                    if operation.generation_id else None,
                })
                if operation.status not in {"accepted", "running"}:
                    yield _event("done", {
                        "status": "cancelled" if operation.status == "superseded"
                        else operation.status,
                    })
            return _stream_response(replay())
        materials = await debate_materials(db, owner_id=current.user.id)
    return _stream_response(_debate_events(
        reservation=reservation, profile=materials.profile,
        profile_version=materials.profile_version,
        graph=graph, gateway=gateway, owner_id=current.user.id, sessions=sessions,
    ))


@router.get("/api/learning-units/{unit_id}/classroom/debate/{result_id}")
async def get_debate_result(
    unit_id: UUID, result_id: UUID, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        result = await owned_debate_result(
            db, owner_id=current.user.id, unit_id=unit_id, result_id=result_id,
        )
    if result is None:
        raise _not_found()
    response.headers["Cache-Control"] = "no-store"
    return debate_result_payload(result)


@router.post("/api/learning-units/{unit_id}/classroom/debate/{result_id}/exit")
async def exit_debate_endpoint(
    unit_id: UUID, result_id: UUID, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    if_match_revision: int = Header(ge=1, alias="If-Match-Classroom-Revision"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        try:
            receipt, _ = await exit_debate(
                db, owner_id=current.user.id, unit_id=unit_id, result_id=result_id,
                idempotency_key=idempotency_key, expected_revision=if_match_revision,
            )
        except IdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
        except ClassroomVersionConflict as error:
            raise _conflict("CLASSROOM_VERSION_CONFLICT",
                            f"Classroom revision is now {error.current_revision}.") from None
        except DebateAlreadyActive:
            raise _conflict("DEBATE_NOT_ACTIVE", "This result is not the active debate.") from None
        except ClassroomNotFound:
            raise _not_found() from None
    response.headers["Cache-Control"] = "no-store"
    return receipt
