"""Locked human-case lifecycle; no model calls and no publication side effects."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.unit_consistency_review import resource_review_priority
from app.models.learning import LearningOperation, LearningUnit, utc_now
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_review import LearningReviewRecord
from app.models.learning_review_case import LearningReviewCase, LearningReviewDecision
from app.services.learning_contract import LearningContractError, canonical, digest
from app.services.learning_owner_lock import lock_learning_owner
from app.services.learning_policy import POLICY_VERSION, active_policy_digest
from app.services.unit_material import restore_material


async def locked_case(db: AsyncSession, *, owner_id: UUID, case_id: UUID) -> LearningReviewCase:
    try:
        await lock_learning_owner(db, owner_id)
    except ValueError:
        raise LearningContractError("REVIEW_CASE_NOT_FOUND") from None
    case = await db.scalar(
        select(LearningReviewCase).where(
            LearningReviewCase.id == case_id, LearningReviewCase.user_id == owner_id
        )
    )
    if case is None:
        raise LearningContractError("REVIEW_CASE_NOT_FOUND")
    await db.refresh(case)
    await db.scalar(
        select(LearningUnit)
        .where(LearningUnit.id == case.learning_unit_id, LearningUnit.user_id == owner_id)
        .with_for_update()
    )
    return case


async def invalidate_case(db: AsyncSession, case: LearningReviewCase) -> None:
    if case.state not in ("pending", "approved"):
        return
    case.state = "invalidated"
    case.updated_at = utc_now()
    op = await db.get(LearningOperation, case.operation_id)
    if op and op.status not in ("canceled", "completed"):
        op.status = "failed"
        op.review_summary = {
            "state": "invalidated",
            "approval_source": None,
            "reason_code": "REVIEW_CASE_INVALIDATED",
            "updated_at": utc_now().isoformat(),
        }
        op.error = {
            "code": "REVIEW_CASE_INVALIDATED",
            "message": "Review case expired.",
            "retryable": False,
        }
    if op and op.publication_expectation:
        from app.models.classroom import ClassroomOperation

        parent = await db.get(
            ClassroomOperation, UUID(str(op.publication_expectation["classroom_operation_id"]))
        )
        if parent and parent.status in ("accepted", "running", "awaiting_human"):
            parent.status = "cancelled" if op.status == "canceled" else "failed"


async def case_current(db: AsyncSession, case: LearningReviewCase) -> bool:
    payload = cast(dict[str, Any], case.payload)
    if digest("review-case", "learning-review-case-v1", payload=payload) != case.case_digest:
        return False
    op = await db.get(LearningOperation, case.operation_id)
    plan = await db.get(LearningPlanVersion, case.plan_id)
    unit = await db.get(LearningUnit, case.learning_unit_id)
    latest = await db.scalar(
        select(func.max(LearningPlanVersion.version)).where(
            LearningPlanVersion.learning_unit_id == case.learning_unit_id
        )
    )
    if (
        not op
        or op.status != "awaiting_human"
        or not plan
        or not unit
        or unit.status == "withdrawn"
        or plan.policy_version != POLICY_VERSION
        or plan.policy_digest != active_policy_digest()
        or latest != plan.version
        or payload["material"]["binding"]["policy_digest"] != plan.policy_digest
    ):
        return False
    if not await operation_context_current(db, op):
        return False
    restore_material(payload["material"])
    return True


async def create_review_case(
    db: AsyncSession, material: dict[str, Any], review_ids: list[UUID]
) -> LearningReviewCase:
    workspace, value = restore_material(material)
    b = value["binding"]
    owner_id = UUID(b["owner_id"])
    await lock_learning_owner(db, owner_id)
    await db.scalar(
        select(LearningUnit)
        .where(LearningUnit.id == UUID(b["unit_id"]), LearningUnit.user_id == owner_id)
        .with_for_update()
    )
    rows = [await db.get(LearningReviewRecord, id) for id in review_ids]
    if len(rows) != 4 or any(
        r is None or r.user_id != owner_id or str(r.operation_id) != b["operation_id"] for r in rows
    ):
        raise LearningContractError
    records = [cast(dict[str, Any], r.record) for r in rows if r]
    prior = resource_review_priority(value, records[:3])
    unit_review = records[3]
    if (
        unit_review["target_digest"] != value["unit_digest"]
        or canonical(unit_review["binding"]) != canonical(b)
        or unit_review["result"]["scope"] != "unit"
    ):
        raise LearningContractError("REVIEW_CASE_BINDING_INVALID")
    verdict = unit_review["local_routing"]["verdict"]
    if prior == "rejected" or verdict == "reject":
        raise LearningContractError("REJECT_NOT_HUMAN_ELIGIBLE")
    if prior != "needs_human" and verdict != "needs_human":
        raise LearningContractError("NO_HUMAN_REVIEW_REQUIRED")
    for existing in (
        await db.scalars(
            select(LearningReviewCase).where(
                LearningReviewCase.user_id == owner_id,
                LearningReviewCase.learning_unit_id == UUID(b["unit_id"]),
                LearningReviewCase.state.in_(("pending", "approved")),
            )
        )
    ).all():
        if existing.operation_id == UUID(b["operation_id"]):
            if (
                cast(dict[str, Any], existing.payload)["material"]["unit_digest"]
                == value["unit_digest"]
            ):
                return existing
            raise LearningContractError("REVIEW_CASE_CONFLICT")
        await invalidate_case(db, existing)
    await db.flush()
    payload = {"material": value, "review_ids": [str(id) for id in review_ids]}
    case = LearningReviewCase(
        user_id=owner_id,
        learning_unit_id=UUID(b["unit_id"]),
        plan_id=UUID(b["plan_id"]),
        operation_id=UUID(b["operation_id"]),
        payload=payload,
        case_digest=digest("review-case", "learning-review-case-v1", payload=payload),
    )
    op = await db.get(LearningOperation, case.operation_id)
    if op is None or op.status not in ("accepted", "running"):
        raise LearningContractError("OPERATION_NOT_ACTIVE")
    op.status = "awaiting_human"
    op.phase = "awaiting_human"
    op.review_summary = {
        "state": "pending",
        "approval_source": None,
        "reason_code": "SEMANTIC_REVIEW_REQUIRED",
        "updated_at": utc_now().isoformat(),
    }
    db.add(case)
    await db.flush()
    return case


async def decide_case(
    db: AsyncSession,
    *,
    owner_id: UUID,
    case_id: UUID,
    expected_digest: str,
    reviewer_id: str,
    identity_source: str,
    verdict: str,
    reason: str,
    idempotency_key: str,
) -> LearningReviewDecision:
    # Caller must authenticate a local maintainer; this service is never exposed by HTTP.
    if (
        verdict not in ("approve", "reject")
        or not reason.strip()
        or len(reason) > 2000
        or not 1 <= len(reviewer_id) <= 128
        or not 1 <= len(identity_source) <= 128
        or not 1 <= len(idempotency_key) <= 128
    ):
        raise LearningContractError("INVALID_REVIEW_DECISION")
    case = await locked_case(db, owner_id=owner_id, case_id=case_id)
    prior = await db.scalar(
        select(LearningReviewDecision).where(
            LearningReviewDecision.user_id == owner_id,
            LearningReviewDecision.idempotency_key == idempotency_key,
        )
    )
    if prior:
        if (
            prior.case_id != case_id
            or prior.case_digest != expected_digest
            or prior.verdict != verdict
            or prior.reason != reason
            or prior.reviewer_id != reviewer_id
            or prior.identity_source != identity_source
        ):
            raise LearningContractError("REVIEW_IDEMPOTENCY_CONFLICT")
        return prior
    if case.case_digest != expected_digest or case.state != "pending":
        raise LearningContractError("REVIEW_CASE_STALE")
    if not await case_current(db, case):
        await invalidate_case(db, case)
        await db.commit()
        raise LearningContractError("REVIEW_CASE_INVALIDATED")
    row = LearningReviewDecision(
        user_id=owner_id,
        learning_unit_id=case.learning_unit_id,
        case_id=case.id,
        case_digest=case.case_digest,
        reviewer_id=reviewer_id,
        identity_source=identity_source,
        verdict=verdict,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    case.state = "approved" if verdict == "approve" else "rejected"
    case.updated_at = utc_now()
    if verdict == "reject":
        op = await db.get(LearningOperation, case.operation_id)
        assert op
        op.status = "rejected"
        op.review_summary = {
            "state": "rejected",
            "approval_source": None,
            "reason_code": "HUMAN_REJECTED",
            "updated_at": utc_now().isoformat(),
        }
    db.add(row)
    await db.flush()
    return row


async def cancel_review_operation(db: AsyncSession, *, owner_id: UUID, operation_id: UUID) -> bool:
    await lock_learning_owner(db, owner_id)
    op = await db.scalar(
        select(LearningOperation)
        .where(LearningOperation.id == operation_id, LearningOperation.user_id == owner_id)
        .execution_options(populate_existing=True)
    )
    if op is None:
        raise LearningContractError("OPERATION_NOT_FOUND")
    if op.status in ("completed", "failed", "rejected"):
        return False
    if op.status == "canceled":
        return True
    op.status = "canceled"
    op.canceled_at = utc_now()
    for case in (
        await db.scalars(
            select(LearningReviewCase).where(
                LearningReviewCase.operation_id == operation_id,
                LearningReviewCase.user_id == owner_id,
                LearningReviewCase.state.in_(("pending", "approved")),
            )
        )
    ).all():
        await invalidate_case(db, case)
    await db.flush()
    return True


async def operation_context_current(db: AsyncSession, op: LearningOperation) -> bool:
    if op.publication_expectation is None:
        return True
    from app.models.classroom import ClassroomOperation, ClassroomSession

    expected = op.publication_expectation
    session = await db.scalar(
        select(ClassroomSession)
        .where(
            ClassroomSession.user_id == op.user_id,
            ClassroomSession.learning_unit_id == op.learning_unit_id,
        )
        .execution_options(populate_existing=True)
    )
    classroom_op = await db.get(
        ClassroomOperation, UUID(str(expected["classroom_operation_id"])), populate_existing=True
    )
    if (
        not session
        or not classroom_op
        or classroom_op.status not in ("accepted", "running", "awaiting_human")
    ):
        return False
    return (
        session.revision == expected["revision"]
        and str(session.generation_id) == expected["generation_id"]
        and session.publication_version == expected["publication_version"]
    )
