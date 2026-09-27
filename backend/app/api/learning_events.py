"""Authenticated learning actions bound to an approved owner scene."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.profile_agent import StructuredProfileGateway
from app.api.knowledge_graph import knowledge_graph_repository
from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_events import (
    LearningEventInvalid,
    LearningEventNotFound,
    learning_event_receipt,
    record_learning_action,
)
from app.services.learning_operations import IdempotencyConflict
from app.services.profile_behavior_updates import (
    learning_evidence_summary,
    profile_behavior_gateway_factory,
    update_profile_from_summary,
)

router = APIRouter(tags=["Assessment"])


class LearningActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    knowledge_node_id: str
    learning_unit_id: UUID
    scene_id: UUID
    action: str


@router.post("/api/learning-events", status_code=200)
async def post_learning_action(
    payload: LearningActionRequest,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
    repository: KnowledgeGraphRepository = Depends(knowledge_graph_repository),
    gateway_factory: Callable[[], StructuredProfileGateway] = Depends(
        profile_behavior_gateway_factory
    ),
    idempotency_key: str = Header(min_length=16, max_length=128, alias="Idempotency-Key"),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with session_factory() as db:
        try:
            record, _ = await record_learning_action(
                db,
                owner_id=current.user.id,
                idempotency_key=idempotency_key,
                event_type=payload.event_type,
                node_id=payload.knowledge_node_id,
                unit_id=payload.learning_unit_id,
                scene_id=payload.scene_id,
                action=payload.action,
                repository=repository,
            )
        except LearningEventNotFound:
            raise AuthFailure(404, "NOT_FOUND", "Resource not found.") from None
        except LearningEventInvalid:
            raise AuthFailure(422, "VALIDATION_ERROR", "Learning action is invalid.") from None
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
    return {**learning_event_receipt(record), "profile_update_status": profile_status}
