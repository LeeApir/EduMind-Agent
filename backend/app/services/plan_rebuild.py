"""One pre-content rebuilt plan; no verifier or budget bypass and no provider in a transaction."""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.learning_unit_generator import StructuredResourceGateway
from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan
from app.models.learning import GeneratedResource
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_review import LearningReviewRecord
from app.models.plan_check import PlanCheck
from app.services.learning_budget import locked_operation, permits_for
from app.services.learning_contract import LearningContractError, canonical
from app.services.learning_owner_lock import lock_learning_owner
from app.services.learning_plans import save_plan
from app.services.plan_check import (
    owned_plan_check,
    save_rebuild_event,
    validate_evidence,
    verify_snapshots,
)
from app.services.plan_verifiers import verify_proof_sources


def event(
    record: dict[str, Any], kind: str, new: LearningPlanVersion | None = None
) -> dict[str, Any]:
    b = record["binding"]
    return dict(
        schema_version="plan-rebuild-event-v1",
        event_id=str(uuid4()),
        operation_id=b["operation_id"],
        event_type=kind,
        attempt=1,
        prior_plan_id=b["plan_id"],
        prior_plan_digest=b["plan_digest"],
        trigger_check_id=record["check_id"],
        proof_ids=record["server_assessment"]["proof_ids"],
        new_plan_id=str(new.id) if new else None,
        new_plan_digest=new.plan_digest if new else None,
        input_digest=b["input_digest"],
        reference_digest=b["reference_digest"],
        policy_digest=b["policy_digest"],
        created_at=datetime.now(timezone.utc).isoformat(),
    )


async def reserve_rebuild(db: AsyncSession, *, owner_id: UUID, check_id: UUID) -> PlanCheck:
    await lock_learning_owner(db, owner_id)
    row = await owned_plan_check(db, owner_id=owner_id, check_id=check_id)
    record = validate_evidence(row.record)
    op = await locked_operation(db, owner_id, row.operation_id)
    plan = await db.get(LearningPlanVersion, row.plan_id)
    latest = await db.scalar(
        select(func.max(LearningPlanVersion.version)).where(
            LearningPlanVersion.learning_unit_id == row.learning_unit_id
        )
    )
    content = await db.scalar(
        select(GeneratedResource.id).where(GeneratedResource.plan_id == row.plan_id).limit(1)
    )
    review = await db.scalar(
        select(LearningReviewRecord.id).where(LearningReviewRecord.plan_id == row.plan_id).limit(1)
    )
    if (
        record["server_assessment"]["route"] != "rebuild_once"
        or row.stage != "plan_check"
        or op.status != "running"
        or op.phase != "plan_check"
        or op.generation_rebuild_count
        or plan is None
        or plan.origin_operation_id != op.id
        or latest != plan.version
        or content is not None
        or review is not None
        or await permits_for(db, op.id)
    ):
        raise LearningContractError("PLAN_REBUILD_NOT_AUTHORIZED")
    verify_snapshots(plan)
    verify_proof_sources(plan, record)
    # Seven content/audit baseline calls plus one new plan and its recheck. No old reuse.
    if op.generation_call_count + 9 > 20:
        raise LearningContractError("GENERATION_LIMIT_EXCEEDED")
    op.generation_rebuild_count = 1
    op.generation_tail_remaining = 9
    await save_rebuild_event(db, owner_id=owner_id, record=event(record, "reserved"))
    await db.commit()
    return row


async def rebuild_plan(
    db: AsyncSession,
    *,
    owner_id: UUID,
    check_id: UUID,
    gateway: StructuredResourceGateway,
    window: CallWindow,
    inputs: PlanInputs,
) -> LearningPlanVersion:
    row = await reserve_rebuild(db, owner_id=owner_id, check_id=check_id)
    record = validate_evidence(row.record)
    old = await db.get(LearningPlanVersion, row.plan_id)
    assert old is not None
    # Release the read transaction before any provider activity.
    old_input = deepcopy(old.input_snapshot)
    old_refs = deepcopy(old.references_snapshot)
    old_policy = deepcopy(old.policy_snapshot)
    old_policy_version = old.policy_version
    prior_version = old.version
    await db.commit()
    try:
        value = await generate_shared_plan(
            gateway,
            inputs,
            window,
            repair=dict(
                prior_plan=old.plan_json,
                findings=record["model_result"]["findings"],
                proofs=record["proofs"],
            ),
        )
        await lock_learning_owner(db, owner_id)
        current = await locked_operation(db, owner_id, row.operation_id)
        latest = await db.scalar(
            select(func.max(LearningPlanVersion.version)).where(
                LearningPlanVersion.learning_unit_id == row.learning_unit_id
            )
        )
        if current.status != "running" or latest != prior_version:
            raise LearningContractError("PLAN_REBUILD_CONTEXT_CHANGED")
        # Input, reference and policy remain original; generation guidance is not user intent.
        if canonical(inputs.references) != canonical(old_refs) or canonical(
            inputs.metadata
        ) != canonical(old_input["metadata"]):
            raise LearningContractError("PLAN_REBUILD_INPUT_CHANGED")
        new = await save_plan(
            db,
            owner_id=owner_id,
            unit_id=row.learning_unit_id,
            operation_id=row.operation_id,
            plan=value,
            input_snapshot=old_input,
            references=old_refs,
            node_ids=set(inputs.node_ids),
            policy_version=old_policy_version,
            policy=old_policy,
        )
        await save_rebuild_event(db, owner_id=owner_id, record=event(record, "completed", new))
        await db.commit()
        return new
    except BaseException:
        await db.rollback()
        await save_rebuild_event(db, owner_id=owner_id, record=event(record, "failed"))
        await db.commit()
        raise
