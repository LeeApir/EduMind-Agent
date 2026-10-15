"""Store v4 audits without granting resource publication rights."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning_plan import LearningPlanVersion
from app.models.learning_review import LearningReviewRecord
from app.services.learning_contract import LearningContractError, validate_contract


async def save_review(db: AsyncSession, record: object) -> LearningReviewRecord:
    value = validate_contract(record, "review_record")
    b = value["binding"]
    plan = await db.get(LearningPlanVersion, UUID(b["plan_id"]))
    if (
        plan is None
        or str(plan.user_id) != b["owner_id"]
        or str(plan.learning_unit_id) != b["unit_id"]
        or plan.version != b["plan_version"]
        or plan.plan_digest != b["plan_digest"]
        or plan.input_digest != b["input_digest"]
        or plan.references_digest != b["references_digest"]
        or plan.policy_version != b["policy_version"]
        or plan.policy_digest != b["policy_digest"]
    ):
        raise LearningContractError("REVIEW_BINDING_INVALID")
    row = LearningReviewRecord(
        id=UUID(value["review_id"]),
        user_id=plan.user_id,
        learning_unit_id=plan.learning_unit_id,
        plan_id=plan.id,
        operation_id=UUID(b["operation_id"]),
        target_digest=value["target_digest"],
        record=value,
    )
    db.add(row)
    await db.flush()
    return row


def plan_binding(plan: LearningPlanVersion, operation_id: UUID) -> dict[str, Any]:
    return {
        "owner_id": str(plan.user_id),
        "unit_id": str(plan.learning_unit_id),
        "operation_id": str(operation_id),
        "plan_id": str(plan.id),
        "plan_version": plan.version,
        "plan_digest": plan.plan_digest,
        "input_digest": plan.input_digest,
        "references_digest": plan.references_digest,
        "policy_version": plan.policy_version,
        "policy_digest": plan.policy_digest,
    }
