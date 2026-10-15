"""Planned reexplanation SSE, retaining the old formal snapshot during human review."""

from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.learning_unit_generator import StructuredResourceGateway
from app.services.learning_contract import LearningContractError
from app.services.planned_reexplanation import run_planned_reexplanation


async def planned_reexplanation_events(
    *,
    owner_id: UUID,
    operation_id: UUID,
    gateway: StructuredResourceGateway,
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[str]:
    from app.api.classroom import _event

    yield _event("agent_start", {"operation_id": str(operation_id), "stage": "planning"})
    try:
        async with sessions() as db:
            result = await run_planned_reexplanation(
                db, owner_id=owner_id, classroom_operation_id=operation_id, gateway=gateway
            )
        if result["status"] == "awaiting_human":
            yield _event(
                "review_required",
                {
                    "operation_id": str(operation_id),
                    "learning_operation_id": result["operation_id"],
                    "reason_code": "SEMANTIC_REVIEW_REQUIRED",
                },
            )
            yield _event("done", {"operation_id": str(operation_id), "status": "awaiting_human"})
            return
        if result["status"] == "completed" and "material" in result:
            s = result["material"]["scenes"][0]
            yield _event(
                "scene_ready",
                {
                    "operation_id": str(operation_id),
                    "scene_key": "explanation",
                    "scene_version": s["scene_version"],
                    "publication_version": result["publication_version"],
                    "resource_ids": [v["resource_id"] for v in result["material"]["scenes"]],
                },
            )
            yield _event("done", {"operation_id": str(operation_id), "status": "published"})
            return
        yield _event("done", {"operation_id": str(operation_id), "status": result["status"]})
    except Exception as error:
        yield _event(
            "error",
            {
                "operation_id": str(operation_id),
                "code": error.code
                if isinstance(error, LearningContractError)
                else "GENERATION_FAILED",
                "retryable": False,
            },
        )
        yield _event("done", {"operation_id": str(operation_id), "status": "failed"})
