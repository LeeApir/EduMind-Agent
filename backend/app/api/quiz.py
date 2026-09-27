"""Authenticated, idempotent submission of published exercise answers."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.profile_agent import StructuredProfileGateway
from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.services.learning_operations import IdempotencyConflict
from app.services.profile_behavior_updates import (
    learning_evidence_summary,
    profile_behavior_gateway_factory,
    update_profile_from_summary,
)
from app.services.quiz_scoring import QuizScoringError
from app.services.quiz_submissions import (
    QuizResourceNotFound,
    latest_quiz_attempt,
    quiz_receipt,
    submit_quiz_attempt,
)

router = APIRouter(tags=["Assessment"])


@router.get("/api/quiz-submissions/latest")
async def get_latest_quiz_result(
    response: Response,
    resource_id: UUID,
    resource_version: int = Query(ge=1),
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        try:
            record = await latest_quiz_attempt(
                db,
                owner_id=current.user.id,
                resource_id=resource_id,
                resource_version=resource_version,
            )
        except QuizResourceNotFound:
            raise AuthFailure(404, "NOT_FOUND", "Quiz result not found.") from None
        if record is None:
            raise AuthFailure(404, "NOT_FOUND", "Quiz result not found.")
        return {**quiz_receipt(record), "profile_update_status": "no_change"}


class QuizAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(max_length=500)


class QuizSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: UUID
    resource_version: int = Field(ge=1)
    answers: list[QuizAnswerRequest] = Field(min_length=1, max_length=10)


@router.post("/api/quiz-submissions")
async def submit_quiz(
    payload: QuizSubmissionRequest,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    gateway_factory: Callable[[], StructuredProfileGateway] = Depends(
        profile_behavior_gateway_factory
    ),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        try:
            record, _ = await submit_quiz_attempt(
                db,
                owner_id=current.user.id,
                idempotency_key=idempotency_key,
                resource_id=payload.resource_id,
                resource_version=payload.resource_version,
                answers=[answer.model_dump() for answer in payload.answers],
            )
        except QuizResourceNotFound:
            raise AuthFailure(404, "NOT_FOUND", "Resource not found.") from None
        except QuizScoringError:
            raise AuthFailure(
                422, "QUIZ_SUBMISSION_INVALID", "Quiz submission is invalid."
            ) from None
        except IdempotencyConflict:
            raise AuthFailure(409, "IDEMPOTENCY_CONFLICT", "Idempotency key conflicts.") from None
    profile_status = await update_profile_from_summary(
        session_factory,
        owner_id=current.user.id,
        evidence_id=record.id,
        observed_at=record.created_at,
        summary=learning_evidence_summary(record),
        gateway_factory=gateway_factory,
    )
    return {**quiz_receipt(record), "profile_update_status": profile_status}
