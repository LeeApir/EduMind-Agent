"""Authenticated classroom snapshot, creation, mode-switching, and speech-streaming API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.classroom_context import ClassroomTurnContext, build_classroom_context
from app.agents.classroom_speech_review import SpeechReviewer, SpeechReviewVerdict
from app.agents.classroom_speech_rules import (
    classify_student_speech,
    classify_tutor_turn,
    combined_speech_verdict,
)
from app.agents.learning_resource_schema import LearningResourceType, ResourceSchemaError
from app.agents.learning_unit_generator import (
    LearningResourceRequest,
    LearningUnitGenerator,
    ResourceGenerationFailure,
)
from app.agents.review_agent import ReviewAgent
from app.agents.tutor_agent import TutorAgent
from app.api.knowledge_graph import knowledge_graph_repository
from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.core.provider_factory import build_default_provider_gateway
from app.models.learning import utc_now
from app.services.classroom import (
    ClassroomNotFound,
    ClassroomReplayUnavailable,
    ClassroomVersionConflict,
    InvalidModeCombination,
    classroom_payload,
    create_classroom,
    owned_classroom,
    set_classroom_mode,
)
from app.services.classroom_speech import (
    classroom_message_payload,
    classroom_messages,
    classroom_operation_payload,
    commit_classroom_speech,
    owned_classroom_operation,
    reserve_classroom_speech,
    speech_materials,
)
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_events import LearningEventInvalid, LearningEventNotFound
from app.services.learning_operations import IdempotencyConflict
from app.services.provider_gateway import ProviderGateway
from app.services.scene_reexplanation import (
    ReexplanationMaterials,
    ReexplanationReservation,
    SceneVersionConflict,
    fail_reexplanation,
    publish_reexplanation,
    reexplanation_materials,
    reserve_reexplanation,
)

router = APIRouter(tags=["Classroom"])


class ModeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["focus", "interactive"]
    enabled_roles: list[Literal["beginner", "advanced"]]


class ClassroomSpeech(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    scene_version: int = Field(ge=1)


class ReexplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["simpler", "deeper", "another_example"]
    base_scene_version: int = Field(ge=1)


def _not_found() -> AuthFailure:
    return AuthFailure(404, "NOT_FOUND", "Classroom not found.")


def _conflict(code: str, message: str) -> AuthFailure:
    return AuthFailure(409, code, message)


def _event(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunks(text: str, size: int = 80) -> Iterator[str]:
    for start in range(0, len(text), size):
        yield text[start : start + size]


def provider_gateway() -> ProviderGateway:
    return build_default_provider_gateway()


def _generation(generation_id: UUID | None) -> str | None:
    return str(generation_id) if generation_id is not None else None


@router.get("/api/learning-units/{unit_id}/classroom")
async def get_classroom(
    unit_id: UUID, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        session = await owned_classroom(db, owner_id=current.user.id, unit_id=unit_id)
    if session is None:
        raise _not_found()
    response.headers["Cache-Control"] = "no-store"
    return classroom_payload(session)


@router.post("/api/learning-units/{unit_id}/classroom")
async def create_classroom_endpoint(
    unit_id: UUID, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        try:
            receipt, created = await create_classroom(
                db, owner_id=current.user.id, unit_id=unit_id, idempotency_key=idempotency_key
            )
        except IdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
        except ClassroomNotFound:
            raise _not_found() from None
        except ClassroomReplayUnavailable:
            raise _conflict(
                "IDEMPOTENCY_RESULT_UNAVAILABLE", "Original receipt is unavailable."
            ) from None
    response.headers["Cache-Control"] = "no-store"
    response.status_code = 201 if created else 200
    return receipt


@router.patch("/api/learning-units/{unit_id}/classroom/mode")
async def set_classroom_mode_endpoint(
    unit_id: UUID, payload: ModeChange, response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    if_match_revision: int = Header(ge=1, alias="If-Match-Classroom-Revision"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        try:
            receipt, _ = await set_classroom_mode(
                db,
                owner_id=current.user.id,
                unit_id=unit_id,
                idempotency_key=idempotency_key,
                mode=payload.mode,
                enabled_roles=list(payload.enabled_roles),
                expected_revision=if_match_revision,
            )
        except IdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
        except ClassroomVersionConflict as error:
            raise _conflict(
                "CLASSROOM_VERSION_CONFLICT",
                f"Classroom revision is now {error.current_revision}.",
            ) from None
        except ClassroomNotFound:
            raise _not_found() from None
        except ClassroomReplayUnavailable:
            raise _conflict(
                "IDEMPOTENCY_RESULT_UNAVAILABLE", "Original receipt is unavailable."
            ) from None
        except InvalidModeCombination:
            raise AuthFailure(
                422, "VALIDATION_ERROR", "Focus mode enables no companion roles."
            ) from None
    response.headers["Cache-Control"] = "no-store"
    return receipt


async def _speech_events(
    *,
    operation_id: UUID,
    revision: int,
    scene_version: int,
    generation_id: UUID | None,
    mode: str,
    enabled_roles: list[str],
    student_text: str,
    context: ClassroomTurnContext,
    gateway: ProviderGateway,
    session_factory: async_sessionmaker[AsyncSession],
    owner_id: UUID,
) -> AsyncIterator[str]:
    operation = str(operation_id)
    generation = _generation(generation_id)
    yield _event(
        "agent_start",
        {
            "operation_id": operation,
            "revision": revision,
            "scene_version": scene_version,
            "generation_id": generation,
        },
    )
    async with session_factory() as db:
        persisted = await owned_classroom_operation(
            db, owner_id=owner_id, operation_id=operation_id
        )
        if persisted is not None:
            persisted.status = "running"
            persisted.updated_at = utc_now()
            await db.commit()
    outcome = await TutorAgent(gateway).orchestrate(
        mode=mode, enabled_roles=enabled_roles, context=context
    )
    if not outcome.ok:
        assert outcome.failure is not None
        async with session_factory() as db:
            persisted = await owned_classroom_operation(
                db, owner_id=owner_id, operation_id=operation_id
            )
            if persisted is not None:
                persisted.status = "failed"
                persisted.error = {
                    "code": "PROVIDER_UNAVAILABLE",
                    "message": outcome.failure.message,
                    "retryable": outcome.failure.recoverable,
                }
                persisted.updated_at = utc_now()
                await db.commit()
        yield _event(
            "error", {"code": "PROVIDER_UNAVAILABLE", "retryable": outcome.failure.recoverable}
        )
        yield _event("done", {"status": "failed"})
        return
    assert outcome.turn is not None
    utterances = outcome.turn.utterances
    turn_text = "\n".join(utterance.text for utterance in utterances)
    verdict = combined_speech_verdict(
        classify_student_speech(student_text), classify_tutor_turn(turn_text)
    )
    if verdict.escalated:
        review = await SpeechReviewer(gateway).review(
            turn_text=turn_text, reference=context.serialized
        )
        if not review.approved:
            code = (
                "REVIEW_UNAVAILABLE"
                if review.verdict is SpeechReviewVerdict.UNAVAILABLE
                else "REVIEW_REJECTED"
            )
            async with session_factory() as db:
                persisted = await owned_classroom_operation(
                    db, owner_id=owner_id, operation_id=operation_id
                )
                if persisted is not None:
                    persisted.status = "failed"
                    persisted.error = {
                        "code": code,
                        "message": "Classroom speech was not approved.",
                        "retryable": review.verdict is SpeechReviewVerdict.UNAVAILABLE,
                    }
                    persisted.updated_at = utc_now()
                    await db.commit()
            yield _event(
                "content_retracted",
                {"revision": revision, "generation_id": generation, "code": code},
            )
            yield _event("done", {"status": "failed"})
            return
    for utterance in utterances:
        for chunk in _chunks(utterance.text):
            yield _event(
                "token",
                {
                    "revision": revision,
                    "scene_version": scene_version,
                    "generation_id": generation,
                    "temporary": True,
                    "delta": chunk,
                    "role": utterance.role,
                },
            )
    yield _event("review_pass", {"operation_id": operation, "kind": "speech"})
    async with session_factory() as db:
        persisted = await owned_classroom_operation(
            db, owner_id=owner_id, operation_id=operation_id
        )
        assert persisted is not None
        committed = await commit_classroom_speech(
            db,
            owner_id=owner_id,
            operation=persisted,
            student_text=student_text,
            utterances=tuple((utterance.role, utterance.text) for utterance in utterances),
        )
    if not committed.published:
        yield _event("done", {"status": "cancelled"})
        return
    for cursor, _role, message_id in committed.messages:
        yield _event(
            "message_ready",
            {"revision": revision, "message_cursor": cursor, "message_id": message_id},
        )
    yield _event("done", {"status": "published"})


@router.post("/api/learning-units/{unit_id}/classroom/messages", response_model=None)
async def stream_classroom_speech(
    unit_id: UUID,
    payload: ClassroomSpeech,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    if_match_revision: int = Header(ge=1, alias="If-Match-Classroom-Revision"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    gateway: ProviderGateway = Depends(provider_gateway),
    graph: KnowledgeGraphRepository = Depends(knowledge_graph_repository),
) -> StreamingResponse:
    async with sessions() as db:
        try:
            reservation = await reserve_classroom_speech(
                db,
                owner_id=current.user.id,
                unit_id=unit_id,
                idempotency_key=idempotency_key,
                text=payload.text,
                scene_version=payload.scene_version,
                expected_revision=if_match_revision,
            )
        except IdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
        except ClassroomVersionConflict as error:
            raise _conflict(
                "CLASSROOM_VERSION_CONFLICT",
                f"Classroom revision is now {error.current_revision}.",
            ) from None
        except ClassroomNotFound:
            raise _not_found() from None
        if not reservation.created:
            return _replay_speech(reservation)
        session = reservation.session
        try:
            materials = await speech_materials(
                db, owner_id=current.user.id, unit_id=unit_id, session=session
            )
        except ClassroomNotFound:
            raise _not_found() from None
    if materials.node_id is None or graph.get_node(materials.node_id) is None:
        raise _not_found()
    try:
        context = build_classroom_context(
            graph,
            node_id=materials.node_id,
            goal=materials.goal,
            reviewed_resources=materials.reviewed_resources,
            profile=materials.profile,
            path=materials.path,
        )
    except ValueError:
        raise _not_found() from None
    return StreamingResponse(
        _speech_events(
            operation_id=reservation.operation.id,
            revision=session.revision,
            scene_version=session.scene_version,
            generation_id=session.generation_id,
            mode=session.mode,
            enabled_roles=[str(role) for role in session.enabled_roles],
            student_text=payload.text,
            context=context,
            gateway=gateway,
            session_factory=sessions,
            owner_id=current.user.id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _replay_speech(reservation: object) -> StreamingResponse:
    """Idempotent retry replays only durable state; temporary tokens are never replayed."""
    from app.services.classroom_speech import SpeechReservation

    assert isinstance(reservation, SpeechReservation)
    operation = str(reservation.operation.id)
    session = reservation.session

    async def events() -> AsyncIterator[str]:
        yield _event(
            "agent_start",
            {
                "operation_id": operation,
                "revision": session.revision,
                "scene_version": session.scene_version,
                "generation_id": _generation(session.generation_id),
            },
        )
        yield _event("done", {"status": reservation.operation.status})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def _reexplanation_events(
    *, reservation: ReexplanationReservation, materials: ReexplanationMaterials,
    owner_id: UUID, gateway: ProviderGateway,
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[str]:
    operation = reservation.operation
    snapshot = operation.result_snapshot or {}
    base_version = snapshot.get("base_scene_version")
    assert isinstance(base_version, int)
    generation = _generation(operation.generation_id)
    yield _event("agent_start", {
        "operation_id": str(operation.id), "revision": operation.base_revision,
        "scene_version": base_version, "generation_id": generation,
    })
    async with sessions() as db:
        persisted = await owned_classroom_operation(
            db, owner_id=owner_id, operation_id=operation.id
        )
        if persisted is not None:
            persisted.status = "running"
            persisted.updated_at = utc_now()
            await db.commit()
    outcome = await LearningUnitGenerator(gateway).generate_one(
        LearningResourceRequest(
            knowledge_point=materials.knowledge_point, learner_goal=materials.goal,
            code_language=materials.code_language, adjustment=materials.adjustment,
        ),
        LearningResourceType.EXPLANATION,
    )
    if isinstance(outcome, ResourceGenerationFailure):
        async with sessions() as db:
            await fail_reexplanation(
                db, operation_id=operation.id, owner_id=owner_id,
                code="PROVIDER_UNAVAILABLE",
            )
        yield _event("error", {"code": "PROVIDER_UNAVAILABLE", "retryable": True})
        yield _event("done", {"status": "failed"})
        return
    markdown = outcome.content["markdown"]
    assert isinstance(markdown, str)
    for chunk in _chunks(markdown):
        yield _event("token", {
            "revision": operation.base_revision, "scene_version": base_version,
            "generation_id": generation, "temporary": True,
            "delta": chunk,
        })
    review = await ReviewAgent(gateway).review(outcome, context=materials.review_context)
    if not review.approved:
        code = "REVIEW_UNAVAILABLE" if review.unavailable else "REVIEW_REJECTED"
        async with sessions() as db:
            await fail_reexplanation(
                db, operation_id=operation.id, owner_id=owner_id,
                code=code,
            )
        yield _event("content_retracted", {
            "revision": operation.base_revision, "generation_id": generation,
            "code": code,
        })
        if review.unavailable:
            yield _event("error", {"code": code, "retryable": True})
        yield _event("done", {"status": "failed"})
        return
    try:
        async with sessions() as db:
            published = await publish_reexplanation(
                db, owner_id=owner_id, operation_id=operation.id, review=review,
            )
    except (SceneVersionConflict, ResourceSchemaError, ValueError):
        async with sessions() as db:
            await fail_reexplanation(
                db, operation_id=operation.id, owner_id=owner_id,
                code="SCENE_PUBLICATION_FAILED",
            )
        yield _event("content_retracted", {
            "revision": operation.base_revision, "generation_id": generation,
            "code": "SCENE_PUBLICATION_FAILED",
        })
        yield _event("error", {"code": "SCENE_PUBLICATION_FAILED", "retryable": False})
        yield _event("done", {"status": "failed"})
        return
    if not published.published:
        yield _event("content_retracted", {
            "revision": operation.base_revision, "generation_id": generation,
            "code": "SCENE_VERSION_CONFLICT",
        })
        yield _event("error", {"code": "SCENE_VERSION_CONFLICT", "retryable": False})
        yield _event("done", {"status": "cancelled"})
        return
    yield _event("review_pass", {"operation_id": str(operation.id), "kind": "reexplanation"})
    yield _event("scene_ready", {
        "revision": operation.base_revision + 1,
        "scene_key": snapshot["scene_key"],
        "scene_version": published.scene_version,
        "resource_ids": [str(value) for value in published.resource_ids],
    })
    yield _event("done", {"status": "published"})


@router.post(
    "/api/learning-units/{unit_id}/classroom/scenes/{scene_key}/reexplanations",
    response_model=None,
)
async def stream_reexplanation(
    unit_id: UUID, scene_key: str, payload: ReexplanationRequest,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
    if_match_revision: int = Header(ge=1, alias="If-Match-Classroom-Revision"),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    gateway: ProviderGateway = Depends(provider_gateway),
    graph: KnowledgeGraphRepository = Depends(knowledge_graph_repository),
) -> StreamingResponse:
    async with sessions() as db:
        try:
            reservation = await reserve_reexplanation(
                db, owner_id=current.user.id, unit_id=unit_id,
                scene_key=scene_key, idempotency_key=idempotency_key,
                action=payload.action, base_scene_version=payload.base_scene_version,
                expected_revision=if_match_revision, graph=graph,
            )
        except IdempotencyConflict:
            raise _conflict("IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
        except ClassroomVersionConflict as error:
            raise _conflict(
                "CLASSROOM_VERSION_CONFLICT",
                f"Classroom revision is now {error.current_revision}.",
            ) from None
        except SceneVersionConflict:
            raise _conflict("SCENE_VERSION_CONFLICT", "Scene version changed.") from None
        except ClassroomNotFound:
            raise _not_found() from None
        except (LearningEventNotFound, LearningEventInvalid):
            raise _not_found() from None
        if not reservation.created:
            async def replay() -> AsyncIterator[str]:
                operation = reservation.operation
                prior = operation.result_snapshot or {}
                yield _event("agent_start", {
                    "operation_id": str(operation.id),
                    "revision": operation.base_revision,
                    "scene_version": prior.get("base_scene_version"),
                    "generation_id": _generation(operation.generation_id),
                })
                if operation.status not in {"accepted", "running"}:
                    yield _event("done", {
                        "status": "cancelled" if operation.status == "superseded"
                        else operation.status,
                    })
            return StreamingResponse(
                replay(), media_type="text/event-stream",
                headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
            )
        try:
            materials = await reexplanation_materials(
                db, owner_id=current.user.id, unit_id=unit_id,
                scene_key=scene_key, base_scene_version=payload.base_scene_version,
                action=payload.action, graph=graph,
            )
        except (ClassroomNotFound, ValueError):
            await fail_reexplanation(
                db, operation_id=reservation.operation.id,
                owner_id=current.user.id, code="SCENE_CONTEXT_UNAVAILABLE",
            )
            raise _not_found() from None
    return StreamingResponse(
        _reexplanation_events(
            reservation=reservation, materials=materials,
            owner_id=current.user.id, gateway=gateway, sessions=sessions,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/api/learning-units/{unit_id}/classroom/messages")
async def get_classroom_messages(
    unit_id: UUID,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    after: int = Query(default=0, ge=0),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        session, messages = await classroom_messages(
            db, owner_id=current.user.id, unit_id=unit_id, after=after
        )
        if session is None:
            raise _not_found()
        if after > session.message_cursor:
            raise _conflict(
                "MESSAGE_CURSOR_INVALID",
                "Message cursor exceeds the current classroom.",
            )
        payload = {
            "messages": [classroom_message_payload(message) for message in messages],
            "last_message_cursor": session.message_cursor,
        }
    response.headers["Cache-Control"] = "no-store"
    return payload


@router.get("/api/classroom-operations/{operation_id}")
async def get_classroom_operation(
    operation_id: UUID,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    async with sessions() as db:
        operation = await owned_classroom_operation(
            db, owner_id=current.user.id, operation_id=operation_id
        )
        if operation is None:
            raise AuthFailure(404, "NOT_FOUND", "Resource not found.")
        payload = classroom_operation_payload(operation)
    response.headers["Cache-Control"] = "no-store"
    return payload
