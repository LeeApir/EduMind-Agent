"""Authenticated, idempotent submission of published exercise answers."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.services.learning_operations import IdempotencyConflict
from app.services.quiz_scoring import QuizScoringError
from app.services.quiz_submissions import QuizResourceNotFound, quiz_receipt, submit_quiz_attempt

router = APIRouter(tags=["Assessment"])


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
    return quiz_receipt(record)
