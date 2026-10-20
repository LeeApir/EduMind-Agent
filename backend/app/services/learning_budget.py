"""Operation-row serialized reservations; failures consume slots, deadlines never reset."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningOperation, utc_now
from app.models.learning_budget import LearningCorrectionPermit, LearningGenerationAttempt
from app.services.learning_contract import LearningContractError
from app.services.learning_stage_gateway import GENERATION_STAGES, REVIEW_STAGES

BUDGET_VERSION = "learning-budget-v1"


def correction_cap(mapping: int, rebuild: int) -> int:
    if (
        type(mapping) is not int
        or type(rebuild) is not int
        or mapping not in (0, 1)
        or rebuild not in (0, 1)
    ):
        raise LearningContractError("GENERATION_BUDGET_INVALID")
    return min(6, (20 - 9 - mapping - 2 * rebuild) // 2)


def initialize_budget(op: LearningOperation) -> None:
    if op.generation_budget_version not in (None, BUDGET_VERSION):
        raise LearningContractError("GENERATION_BUDGET_VERSION_MISMATCH")
    if op.generation_budget_version is None:
        if op.generation_call_count != 0:
            raise LearningContractError("LEGACY_BUDGET_CANNOT_RESUME")
        op.generation_budget_version = BUDGET_VERSION
    op.generation_deadline = op.generation_deadline or utc_now() + timedelta(seconds=180)


async def locked_operation(
    db: AsyncSession, owner_id: UUID, operation_id: UUID
) -> LearningOperation:
    op = await db.scalar(
        select(LearningOperation)
        .where(LearningOperation.id == operation_id, LearningOperation.user_id == owner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        op is None
        or op.generation_budget_version != BUDGET_VERSION
        or op.status not in ("accepted", "running")
        or op.generation_deadline is None
        or op.generation_deadline <= utc_now()
    ):
        raise LearningContractError("GENERATION_LIMIT_EXCEEDED")
    return op


async def permits_for(db: AsyncSession, operation_id: UUID) -> list[LearningCorrectionPermit]:
    return list(
        (
            await db.scalars(
                select(LearningCorrectionPermit)
                .where(LearningCorrectionPermit.operation_id == operation_id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )


async def reserve_correction(
    db: AsyncSession, *, owner_id: UUID, operation_id: UUID, role: str
) -> UUID | None:
    op = await locked_operation(db, owner_id, operation_id)
    if op.status != "running" or role not in ("explanation", "code", "exercise"):
        raise LearningContractError("GENERATION_BUDGET_INVALID")
    permits = await permits_for(db, operation_id)
    same = [p for p in permits if p.role == role]
    unused = sum(2 - p.used for p in permits)
    # Do not take another pair while any earlier pair is unconsumed, even across workers.
    if (
        unused
        or len(same) >= 2
        or len(permits) >= correction_cap(op.generation_mapping_count, op.generation_rebuild_count)
        or op.generation_call_count + unused + 2 + op.generation_tail_remaining > 20
    ):
        await db.commit()
        return None
    row = LearningCorrectionPermit(operation_id=operation_id, role=role, ordinal=len(same) + 1)
    db.add(row)
    await db.flush()
    pid = row.id
    await db.commit()
    return pid


async def reserve_attempt(
    db: AsyncSession,
    *,
    owner_id: UUID,
    operation_id: UUID,
    stage: str | None,
    permit_id: UUID | None = None,
) -> float:
    if stage not in GENERATION_STAGES | REVIEW_STAGES:
        raise LearningContractError("LEARNING_STAGE_REQUIRED")
    op = await locked_operation(db, owner_id, operation_id)
    permits = await permits_for(db, operation_id)
    unspent = sum(2 - p.used for p in permits)
    if op.generation_call_count >= 20:
        raise LearningContractError("GENERATION_LIMIT_EXCEEDED")
    if stage == "goal_mapping":
        if op.status != "accepted" or op.generation_mapping_count or permit_id is not None:
            raise LearningContractError("GOAL_MAPPING_LIMIT_EXCEEDED")
        op.generation_mapping_count = 1
    elif permit_id is not None:
        p = next((p for p in permits if p.id == permit_id), None)
        if (
            op.status != "running"
            or p is None
            or p.used >= 2
            or stage != ("resource_correction" if p.used == 0 else "resource_review")
        ):
            raise LearningContractError("CORRECTION_PERMIT_INVALID")
        p.used += 1
        unspent -= 1
    else:
        if (
            op.status != "running"
            or stage == "resource_correction"
            or op.generation_tail_remaining <= 0
            or unspent
        ):
            raise LearningContractError("BASELINE_ATTEMPT_INVALID")
        if stage in ("plan_rebuild", "plan_recheck") and op.generation_rebuild_count != 1:
            raise LearningContractError("PLAN_REBUILD_NOT_AUTHORIZED")
        op.generation_tail_remaining -= 1
    if op.generation_call_count + 1 + unspent + op.generation_tail_remaining > 20:
        raise LearningContractError("GENERATION_LIMIT_EXCEEDED")
    op.generation_call_count += 1
    db.add(
        LearningGenerationAttempt(
            operation_id=operation_id,
            ordinal=op.generation_call_count,
            stage=stage,
            permit_id=permit_id,
        )
    )
    deadline = op.generation_deadline
    assert deadline is not None  # Established by initialized/locked budget.
    await db.commit()
    remaining = min(60.0, (deadline - utc_now()).total_seconds())
    if remaining <= 0:
        raise LearningContractError("GENERATION_LIMIT_EXCEEDED")
    return remaining
