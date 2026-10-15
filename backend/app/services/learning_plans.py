"""Persist validated plans with server-issued identities and owner locks."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningOperation, LearningUnit
from app.models.learning_plan import LearningPlanVersion
from app.services.learning_contract import LearningContractError, digest, validate_plan
from app.services.learning_owner_lock import lock_learning_owner


async def save_plan(
    db: AsyncSession,
    *,
    owner_id: UUID,
    unit_id: UUID,
    operation_id: UUID,
    plan: object,
    input_snapshot: dict[str, Any],
    references: dict[str, object],
    node_ids: set[str],
    policy_version: str,
    policy: dict[str, object],
) -> LearningPlanVersion:
    value = validate_plan(plan, node_ids=node_ids, references=references)
    await lock_learning_owner(db, owner_id)
    unit = await db.get(LearningUnit, unit_id)
    operation = await db.get(LearningOperation, operation_id)
    if (
        unit is None
        or unit.user_id != owner_id
        or operation is None
        or operation.user_id != owner_id
        or operation.learning_unit_id != unit_id
    ):
        raise LearningContractError
    version = await db.scalar(
        select(func.max(LearningPlanVersion.version)).where(
            LearningPlanVersion.learning_unit_id == unit_id
        )
    )
    row = LearningPlanVersion(
        user_id=owner_id,
        learning_unit_id=unit_id,
        origin_operation_id=operation_id,
        version=(version or 0) + 1,
        schema_version="learning-plan-v1",
        plan_json=value,
        input_snapshot=input_snapshot,
        references_snapshot=references,
        policy_snapshot=policy,
        plan_digest=digest("plan", "learning-plan-v1", plan=value),
        input_digest=digest("input", "learning-input-v1", snapshot=input_snapshot),
        references_digest=digest("references", "learning-references-v1", references=references),
        policy_version=policy_version,
        policy_digest=digest("policy", policy_version, policy=policy),
    )
    db.add(row)
    await db.flush()
    return row
