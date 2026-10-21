"""Shared-plan operation pipeline; all network stages run outside DB transactions."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.hybrid_resource_review import review_resource
from app.agents.learning_unit_generator import StructuredResourceGateway
from app.agents.plan_check import inspect_plan
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan
from app.agents.unit_consistency_review import review_unit
from app.models.learning import LearningOperation, LearningUnit, utc_now
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_review_case import LearningReviewCase
from app.services.hybrid_learning_publication import publish_complete_unit, stage_candidates
from app.services.learning_budget import initialize_budget, reserve_attempt, reserve_correction
from app.services.learning_contract import ROLES, LearningContractError, canonical
from app.services.learning_owner_lock import lock_learning_owner
from app.services.learning_plans import save_plan
from app.services.learning_policy import POLICY, POLICY_VERSION
from app.services.learning_review_cases import create_review_case, invalidate_case
from app.services.learning_review_records import plan_binding, save_review
from app.services.learning_stage_gateway import LearningStageGateway
from app.services.plan_check import owned_review_binding, save_plan_check
from app.services.plan_rebuild import rebuild_plan
from app.services.teaching_actions import assemble_actions
from app.services.unit_material import unit_material


async def run_planned_operation(
    db: AsyncSession,
    *,
    owner_id: UUID,
    operation_id: UUID,
    inputs: PlanInputs,
    gateway: StructuredResourceGateway,
    reuse_plan: LearningPlanVersion | None = None,
    reuse_content: dict[str, Any] | None = None,
    adjustment: object = None,
    on_phase: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    inputs = deepcopy(inputs)
    # P0 may explicitly map both roles to one selected gateway. A diagnostic pair remains explicit.
    gateway = LearningStageGateway(gateway, gateway)
    await lock_learning_owner(db, owner_id)
    op = await db.scalar(
        select(LearningOperation)
        .where(LearningOperation.id == operation_id, LearningOperation.user_id == owner_id)
        .execution_options(populate_existing=True)
    )
    if op is None or op.status != "accepted":
        raise LearningContractError("OPERATION_NOT_FRESH")
    if inputs.teaching_context is not None:
        from app.services.teaching_binding import check_teaching_plan

        teaching = check_teaching_plan(inputs.teaching_context, inputs.metadata)
        if op.goal != teaching["original_request"] or (
            op.teaching_context is not None
            and canonical(op.teaching_context) != canonical(teaching)
        ):
            raise LearningContractError("TEACHING_BINDING_MISMATCH")
        op.teaching_context = teaching
    elif op.teaching_context is not None:
        raise LearningContractError("TEACHING_BINDING_MISMATCH")
    unit = await db.get(LearningUnit, op.learning_unit_id) if op.learning_unit_id else None
    if unit is None:
        unit = LearningUnit(
            user_id=owner_id,
            title=str(inputs.metadata["goal"])[:200],
            knowledge_point_id=inputs.metadata["node_id"],
            learning_objectives={"goal": inputs.metadata["goal"]},
            outline={
                "pipeline": "shared-plan-v1",
                "path_snapshot": inputs.path_snapshot,
                **(
                    {"teaching_context": inputs.teaching_context} if inputs.teaching_context else {}
                ),
            },
        )
        db.add(unit)
        await db.flush()
        op.learning_unit_id = unit.id
    if (
        inputs.teaching_context is not None
        and unit.knowledge_point_id != inputs.metadata["node_id"]
    ):
        raise LearningContractError("TEACHING_BINDING_MISMATCH")
    if unit.user_id != owner_id or unit.status == "withdrawn":
        raise LearningContractError("UNIT_NOT_AVAILABLE")
    for prior_case in (
        await db.scalars(
            select(LearningReviewCase).where(
                LearningReviewCase.user_id == owner_id,
                LearningReviewCase.learning_unit_id == unit.id,
                LearningReviewCase.state.in_(("pending", "approved")),
            )
        )
    ).all():
        await invalidate_case(db, prior_case)
    initialize_budget(op)
    if op.generation_tail_remaining != 0:
        raise LearningContractError("GENERATION_BUDGET_ALREADY_STARTED")
    op.generation_tail_remaining = (9 if reuse_plan is None else 8) - sum(
        1 for role in ROLES if reuse_content and role in reuse_content
    )
    op.status = "running"
    unit_id = unit.id
    deadline = op.generation_deadline
    assert deadline is not None  # Established by initialized/locked budget.
    await db.commit()

    async def reserve(request: Any, permit_id: UUID | None) -> None:
        await reserve_attempt(
            db,
            owner_id=owner_id,
            operation_id=operation_id,
            stage=request.stage,
            permit_id=permit_id,
        )

    async def pair(role: str) -> UUID | None:
        return await reserve_correction(db, owner_id=owner_id, operation_id=operation_id, role=role)

    window = CallWindow(
        deadline=time.monotonic() + max(0, (deadline - utc_now()).total_seconds()),
        reserve_request=reserve,
        reserve_pair=pair,
    )

    async def phase(value: str) -> None:
        await db.execute(
            update(LearningOperation)
            .where(LearningOperation.id == operation_id, LearningOperation.status == "running")
            .values(phase=value)
        )
        await db.commit()
        if on_phase is not None:
            await on_phase(value)

    plan_check_id = None
    try:
        await phase("planning")
        if reuse_plan is None:
            plan_inputs = inputs
            if adjustment is not None:
                plan_inputs = PlanInputs(
                    inputs.metadata,
                    inputs.references,
                    inputs.node_ids,
                    {**inputs.learner_evidence, "explicit_adjustment": adjustment},
                    inputs.reference_context,
                    teaching_context=inputs.teaching_context,
                )
            plan_value = await generate_shared_plan(gateway, plan_inputs, window)
            if (
                isinstance(adjustment, dict)
                and adjustment.get("require_new_example")
                and canonical(plan_value["shared_example"])
                == canonical(adjustment.get("prior_shared_example"))
            ):
                raise LearningContractError("EXAMPLE_NOT_CHANGED")
            plan = await save_plan(
                db,
                owner_id=owner_id,
                unit_id=unit_id,
                operation_id=operation_id,
                plan=plan_value,
                input_snapshot={**inputs.snapshot(), "reference_context": inputs.reference_context},
                references=inputs.references,
                node_ids=set(inputs.node_ids),
                policy_version=POLICY_VERSION,
                policy=POLICY,
            )
            await db.commit()
        else:
            plan = reuse_plan
            if plan.user_id != owner_id or plan.learning_unit_id != unit_id:
                raise LearningContractError
        await phase("plan_check")
        review_binding = await owned_review_binding(
            db, plan, owner_id=owner_id, operation_id=operation_id
        )
        check_record = await inspect_plan(
            gateway, window, plan, operation_id, expected_binding=review_binding
        )
        check_row = await save_plan_check(db, check_record)
        plan_check_id = check_row.id
        await db.commit()
        plan_route = check_record["server_assessment"]["route"]
        if plan_route == "rebuild_once":
            plan = await rebuild_plan(
                db,
                owner_id=owner_id,
                check_id=check_row.id,
                gateway=gateway,
                window=window,
                inputs=inputs,
            )
            reuse_content = None
            await phase("plan_recheck")
            review_binding = await owned_review_binding(
                db, plan, owner_id=owner_id, operation_id=operation_id
            )
            check_record = await inspect_plan(
                gateway,
                window,
                plan,
                operation_id,
                stage="plan_recheck",
                expected_binding=review_binding,
            )
            check_row = await save_plan_check(db, check_record)
            plan_check_id = check_row.id
            await db.commit()
            plan_route = check_record["server_assessment"]["route"]
        if plan_route != "accept_plan":
            if plan_route == "reject":
                raise LearningContractError("PLAN_REJECTED")
            raise LearningContractError(
                "GOAL_CLARIFICATION_REQUIRED"
                if plan_route == "clarify_user"
                else "PLAN_REVIEW_REQUIRED"
            )
        workspace = PlannedScenes(
            plan.plan_json,
            plan_binding(plan, operation_id),
            reference_context=inputs.reference_context,
            input_snapshot=plan.input_snapshot,
        )
        records = []

        async def persist_candidates(current: PlannedScenes) -> None:
            await stage_candidates(db, current)
            await db.commit()

        async def persist_review(record: dict[str, Any]) -> None:
            await save_review(db, record)
            await db.commit()

        for role in ROLES:
            await phase("generating")
            if reuse_content and role in reuse_content:
                workspace.stage(role, reuse_content[role])
            else:
                await workspace.generate(gateway, window, role, adjustment)
            await phase("reviewing")
            history = await review_resource(
                gateway,
                window,
                workspace,
                role,
                on_candidate=persist_candidates,
                on_review=persist_review,
            )
            scenes = await stage_candidates(db, workspace)
            records.append(history[-1])
            await db.commit()
            if history[-1]["local_routing"]["verdict"] == "reject":
                raise LearningContractError("CURRENT_CANDIDATE_REJECTED")
        actions = assemble_actions(workspace.candidates())
        material = unit_material(workspace, scenes, actions)
        await phase("consistency_check")
        result = await review_unit(
            gateway, window, material, records, input_snapshot=plan.input_snapshot
        )
        if result["review"] is None:
            raise LearningContractError("CURRENT_CANDIDATE_REJECTED")
        consistency = await save_review(db, result["review"])
        await db.commit()
        final_ids = [UUID(r["review_id"]) for r in records] + [consistency.id]
        if result["state"] == "rejected":
            raise LearningContractError("CURRENT_CANDIDATE_REJECTED")
        if result["state"] == "needs_human":
            case = await create_review_case(db, material, final_ids)
            await db.commit()
            return {
                "status": "awaiting_human",
                "operation_id": str(operation_id),
                "case_id": str(case.id),
                "learning_unit_id": str(unit_id),
            }
        await phase("publishing")
        publication = await publish_complete_unit(db, material, final_ids)
        await db.commit()
        return {
            "status": "completed",
            "operation_id": str(operation_id),
            "learning_unit_id": str(unit_id),
            "publication_version": publication.version,
            "material": material,
        }
    except BaseException as error:
        await db.rollback()
        await lock_learning_owner(db, owner_id)
        current = await db.get(LearningOperation, operation_id, populate_existing=True)
        if current and current.status not in ("canceled", "completed"):
            if isinstance(error, asyncio.CancelledError):
                current.status = "canceled"
                current.canceled_at = utc_now()
                await db.commit()
                raise
            current.status = (
                "rejected"
                if isinstance(error, LearningContractError)
                and error.code in ("CURRENT_CANDIDATE_REJECTED", "PLAN_REJECTED")
                else "failed"
            )
            current.error = {
                "code": error.code
                if isinstance(error, LearningContractError)
                else "GENERATION_FAILED",
                "retryable": False,
                "message": "Planned operation did not publish.",
            }
            if isinstance(error, LearningContractError) and error.code in (
                "PLAN_REVIEW_REQUIRED",
                "PLAN_REJECTED",
                "GOAL_CLARIFICATION_REQUIRED",
            ):
                current.error = {
                    **current.error,
                    "stage": check_record["request_stage"],
                    "check_id": str(plan_check_id),
                }
            await db.commit()
        raise
