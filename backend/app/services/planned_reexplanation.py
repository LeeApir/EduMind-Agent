"""Reexplain a planned unit through whole-unit qualification; keep the old snapshot usable."""

from copy import deepcopy
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.learning_unit_generator import StructuredResourceGateway
from app.agents.shared_learning_plan import PlanInputs
from app.models.classroom import ClassroomOperation, ClassroomSession
from app.models.learning import GeneratedResource, LearningOperation, utc_now
from app.models.learning_plan import LearningPlanVersion
from app.services.hybrid_learning_publication import current_publication
from app.services.learning_contract import LearningContractError
from app.services.learning_owner_lock import lock_learning_owner
from app.services.planned_learning_flow import run_planned_operation


async def planned_materials(
    db: AsyncSession,
    *,
    owner_id: UUID,
    unit_id: UUID,
    scene_key: str,
    base_version: int,
    action: str,
) -> dict[str, Any]:
    if scene_key not in ("intro", "explanation"):
        raise LearningContractError("REEXPLANATION_SCENE_UNSUPPORTED")
    if action not in ("simpler", "deeper", "another_example"):
        raise LearningContractError
    publication = await current_publication(db, owner_id=owner_id, unit_id=unit_id)
    if publication is None:
        raise LearningContractError("SCENE_VERSION_CONFLICT")
    material = cast(dict[str, Any], publication.material)
    if material["scenes"][0]["scene_version"] != base_version:
        raise LearningContractError("SCENE_VERSION_CONFLICT")
    plan = await db.get(LearningPlanVersion, publication.plan_id)
    if plan is None:
        raise LearningContractError("PLAN_UNAVAILABLE")
    resources = []
    for s in material["scenes"]:
        r = await db.get(GeneratedResource, UUID(s["resource_id"]))
        if (
            not r
            or r.user_id != owner_id
            or r.content_digest != s["resource_digest"]
            or r.plan_id != plan.id
        ):
            raise LearningContractError("ASSOCIATED_RESOURCE_UNAVAILABLE")
        resources.append(r)
    if resources[1].content.get("language") != plan.plan_json["code_language"]:
        raise LearningContractError("CODE_LANGUAGE_MISMATCH")
    return {
        "publication_version": publication.version,
        "plan_id": str(plan.id),
        "input_snapshot": deepcopy(plan.input_snapshot),
        "code_language": plan.plan_json["code_language"],
        "prior_explanation": deepcopy(resources[0].content),
        "reuse_content": {c["role"]: deepcopy(c["envelope"]) for c in material["candidates"][1:]},
    }


async def run_planned_reexplanation(
    db: AsyncSession,
    *,
    owner_id: UUID,
    classroom_operation_id: UUID,
    gateway: StructuredResourceGateway,
) -> dict[str, Any]:
    await lock_learning_owner(db, owner_id)
    classroom_op = await db.scalar(
        select(ClassroomOperation)
        .where(
            ClassroomOperation.id == classroom_operation_id, ClassroomOperation.user_id == owner_id
        )
        .execution_options(populate_existing=True)
    )
    if not classroom_op or classroom_op.kind != "reexplanation":
        raise LearningContractError
    snapshot = cast(dict[str, Any], classroom_op.result_snapshot or {})
    # Replaying never creates a second model operation.
    if snapshot.get("learning_operation_id"):
        op = await db.get(LearningOperation, UUID(snapshot["learning_operation_id"]))
        return {
            "status": op.status if op else "failed",
            "operation_id": snapshot["learning_operation_id"],
        }
    session = await db.scalar(
        select(ClassroomSession).where(
            ClassroomSession.user_id == owner_id,
            ClassroomSession.learning_unit_id == classroom_op.learning_unit_id,
        )
    )
    if (
        not session
        or session.revision != classroom_op.base_revision
        or session.generation_id != classroom_op.generation_id
        or classroom_op.status not in ("accepted", "running")
    ):
        raise LearningContractError("CLASSROOM_VERSION_CONFLICT")
    values = await planned_materials(
        db,
        owner_id=owner_id,
        unit_id=classroom_op.learning_unit_id,
        scene_key=snapshot["scene_key"],
        base_version=snapshot["base_scene_version"],
        action=snapshot["action"],
    )
    plan = await db.get(LearningPlanVersion, UUID(values["plan_id"]))
    assert plan
    raw = values["input_snapshot"]
    inputs = PlanInputs(
        raw["metadata"],
        raw["references"],
        frozenset(raw["node_ids"]),
        raw["learner_evidence"],
        raw["reference_context"],
    )
    op = LearningOperation(
        user_id=owner_id,
        learning_unit_id=classroom_op.learning_unit_id,
        idempotency_key="planned-reexplanation:" + str(classroom_op.id),
        request_digest=classroom_op.request_digest,
        goal=str(plan.plan_json["goal"]),
        preferred_language=values["code_language"],
    )
    op.publication_expectation = {
        "classroom_operation_id": str(classroom_op.id),
        "revision": session.revision,
        "generation_id": str(session.generation_id),
        "publication_version": session.publication_version,
    }
    db.add(op)
    await db.flush()
    classroom_op.result_snapshot = {
        **snapshot,
        "learning_operation_id": str(op.id),
        "base_publication_version": values["publication_version"],
    }
    classroom_op.status = "running"
    await db.commit()
    another = snapshot["action"] == "another_example"
    try:
        result = await run_planned_operation(
            db,
            owner_id=owner_id,
            operation_id=op.id,
            inputs=inputs,
            gateway=gateway,
            reuse_plan=None if another else plan,
            reuse_content=None if another else values["reuse_content"],
            adjustment={
                "action": snapshot["action"],
                "prior_explanation": values["prior_explanation"],
                "require_new_example": another,
                "prior_shared_example": plan.plan_json["shared_example"],
            },
        )
    except BaseException:
        await db.rollback()
        await lock_learning_owner(db, owner_id)
        current = await db.get(ClassroomOperation, classroom_operation_id, populate_existing=True)
        if current and current.status in ("accepted", "running"):
            current.status = "failed"
            current.updated_at = utc_now()
            await db.commit()
        raise
    current = await db.get(ClassroomOperation, classroom_operation_id, populate_existing=True)
    assert current
    current.status = "published" if result["status"] == "completed" else result["status"]
    current.result_snapshot = {
        **cast(dict[str, Any], current.result_snapshot),
        "planned_result": {k: v for k, v in result.items() if k != "material"},
    }
    await db.commit()
    return result
