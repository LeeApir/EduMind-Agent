"""Shared-plan SSE adapter. No client-accessible reviewer or approval endpoint."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.goal_node_resolver import clarification_payload, resolve_goal_node
from app.models.learning import LearningOperation, utc_now
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_contract import LearningContractError
from app.services.learning_operations import owned_operation
from app.services.planned_learning_flow import run_planned_operation
from app.services.provider_gateway import ProviderGateway, StructuredRequest, StructuredResult
from app.services.shared_plan_inputs import shared_plan_inputs


async def hybrid_events(
    *,
    operation_id: UUID,
    owner_id: UUID,
    goal: str,
    language: str,
    gateway: ProviderGateway,
    graph: KnowledgeGraphRepository,
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[str]:
    from app.api.learning_sessions import _event

    queue: asyncio.Queue[tuple[str, dict[str, object]]] = asyncio.Queue()

    async def phase(value: str) -> None:
        await queue.put(
            ("stage_changed", {"operation_id": str(operation_id), "stage": value, "phase": value})
        )

    async def work() -> None:
        failure_detail: dict[str, object] | None = None
        try:
            async with sessions() as db:
                op = await owned_operation(db, owner_id=owner_id, operation_id=operation_id)
                if op is None or op.status != "accepted":
                    raise LearningContractError("OPERATION_NOT_FRESH")
                op.phase = "planning"
                op.generation_deadline = utc_now() + timedelta(seconds=180)
                await db.commit()

                # An optional goal-mapping request consumes the same durable operation quota.
                class MappingGateway:
                    async def generate_structured(
                        self, request: StructuredRequest, *, retry_safe: bool = False
                    ) -> StructuredResult:
                        count = await db.scalar(
                            update(LearningOperation)
                            .where(
                                LearningOperation.id == operation_id,
                                LearningOperation.status == "accepted",
                                LearningOperation.generation_call_count < 20,
                                LearningOperation.generation_deadline > utc_now(),
                            )
                            .values(
                                generation_call_count=LearningOperation.generation_call_count + 1
                            )
                            .returning(LearningOperation.generation_call_count)
                        )
                        await db.commit()
                        if count is None:
                            raise LearningContractError("GENERATION_LIMIT_EXCEEDED")
                        async with asyncio.timeout(60):
                            return await gateway.generate_structured(request, retry_safe=False)

                resolution = await resolve_goal_node(goal, graph=graph, gateway=MappingGateway())
                if resolution.node is None:
                    failure_detail = clarification_payload(resolution, graph)
                    raise LearningContractError("GOAL_CLARIFICATION_REQUIRED")
                # Preserve the existing path loop without an extra profile model request.
                from dataclasses import replace

                from app.agents.profile_events import PROFILE_MERGE_RULE_VERSION
                from app.models.learning import StudentProfile
                from app.services.learning_owner_lock import lock_learning_owner
                from app.services.owned_learning import latest_profile
                from app.services.path_commands import path_payload
                from app.services.path_versions import plan_or_replan_path

                await lock_learning_owner(db, owner_id)
                profile = await latest_profile(db, owner_id)
                if profile is None:
                    profile = StudentProfile(
                        user_id=owner_id,
                        version=1,
                        merge_rule_version=PROFILE_MERGE_RULE_VERSION,
                        initial_query=goal,
                        learning_goals={"topic": goal},
                        evidence={
                            "learning_goals": [
                                {
                                    "source": "initial_query",
                                    "confidence": 1.0,
                                    "observed_at": utc_now().isoformat(),
                                    "profile_version": 1,
                                }
                            ]
                        },
                    )
                    db.add(profile)
                    await db.flush()
                await db.commit()
                path, _ = await plan_or_replan_path(
                    db,
                    owner_id=owner_id,
                    target_node_id=resolution.node.id,
                    graph=graph,
                    trigger_reason="initial_plan",
                )
                path_snapshot = path_payload(path, is_stale=False)
                await db.commit()
                inputs = await shared_plan_inputs(
                    db,
                    owner_id=owner_id,
                    node_id=path.current_node_id or resolution.node.id,
                    goal=goal,
                    language=language,
                    graph=graph,
                )
                inputs = replace(inputs, path_snapshot=path_snapshot)
                await db.commit()
                result = await run_planned_operation(
                    db,
                    owner_id=owner_id,
                    operation_id=operation_id,
                    inputs=inputs,
                    gateway=gateway,
                    on_phase=phase,
                )
                if result["status"] == "awaiting_human":
                    await queue.put(
                        (
                            "review_required",
                            {
                                "operation_id": str(operation_id),
                                "reason_code": "SEMANTIC_REVIEW_REQUIRED",
                            },
                        )
                    )
                else:
                    material = result["material"]
                    scene = material["scenes"][0]
                    await queue.put(
                        (
                            "scene_ready",
                            {
                                "operation_id": str(operation_id),
                                "learning_unit_id": result["learning_unit_id"],
                                "scene_key": "explanation",
                                "scene_id": scene["scene_id"],
                                "version": scene["scene_version"],
                                "publication_version": result["publication_version"],
                                "resource_ids": [s["resource_id"] for s in material["scenes"]],
                            },
                        )
                    )
                await queue.put(
                    ("done", {"operation_id": str(operation_id), "status": result["status"]})
                )
        except Exception as error:
            detail = failure_detail or {
                "code": error.code
                if isinstance(error, LearningContractError)
                else "GENERATION_FAILED",
                "retryable": False,
            }
            async with sessions() as db:
                op = await owned_operation(db, owner_id=owner_id, operation_id=operation_id)
                if op and op.status not in ("completed", "canceled", "rejected", "failed"):
                    op.status = "failed"
                    op.error = detail
                if op and op.status in ("canceled", "rejected", "failed"):
                    op.phase = None
                    op.generation_deadline = None
                await db.commit()
                status = op.status if op else "failed"
            await queue.put(("error", {"operation_id": str(operation_id), **detail}))
            await queue.put(("done", {"operation_id": str(operation_id), "status": status}))

    task = asyncio.create_task(work())
    try:
        yield _event("agent_start", {"operation_id": str(operation_id), "stage": "planning"})
        while True:
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=10)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield _event(event, data)
            if event == "done":
                break
        await task
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            async with sessions() as db:
                from app.services.learning_review_cases import cancel_review_operation

                await cancel_review_operation(db, owner_id=owner_id, operation_id=operation_id)
                await db.commit()
