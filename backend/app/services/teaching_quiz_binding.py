"""Resolve quiz evidence against the exact immutable publication, never current path."""

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import GeneratedResource, LearningUnit
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_publication import LearningPublication, LearningPublicationWithdrawal
from app.services.learning_contract import LearningContractError, canonical
from app.services.teaching_binding import TEACHING_BINDING_VERSION, check_teaching_plan
from app.services.unit_material import restore_material


async def quiz_teaching_binding(db: AsyncSession, resource: GeneratedResource) -> dict[str, Any]:
    rows = (
        await db.scalars(
            select(LearningPublication)
            .where(
                LearningPublication.user_id == resource.user_id,
                LearningPublication.learning_unit_id == resource.learning_unit_id,
                LearningPublication.plan_id == resource.plan_id,
            )
            .order_by(LearningPublication.version.desc())
        )
    ).all()
    for row in rows:
        material = cast(dict[str, Any], row.material)
        if await db.get(LearningPublicationWithdrawal, row.id):
            continue
        if not any(
            s["resource_id"] == str(resource.id) and s["resource_digest"] == resource.content_digest
            for s in material["scenes"]
        ):
            continue
        if "teaching_context" not in material:
            raise LearningContractError("TEACHING_BINDING_UNVERIFIED")
        try:
            _, m = restore_material(material)
            context = check_teaching_plan(m["teaching_context"], m["plan"])
            plan = await db.get(LearningPlanVersion, resource.plan_id)
            unit = await db.get(LearningUnit, resource.learning_unit_id, populate_existing=True)
            candidate = next(c for c in m["candidates"] if c["resource_id"] == str(resource.id))
            if (
                not plan
                or str(plan.id) != m["binding"]["plan_id"]
                or plan.plan_digest != m["binding"]["plan_digest"]
                or plan.input_digest != m["binding"]["input_digest"]
                or row.unit_digest != m["unit_digest"]
                or not unit
                or unit.user_id != resource.user_id
                or plan.user_id != resource.user_id
                or canonical(plan.input_snapshot.get("teaching_context")) != canonical(context)
                or plan.plan_json["node_id"] != context["teaching_node_id"]
                or unit.knowledge_point_id != context["teaching_node_id"]
                or resource.knowledge_point_id != context["teaching_node_id"]
                or canonical(candidate["envelope"]["content"]) != canonical(resource.content)
            ):
                raise ValueError
        except (LearningContractError, ValueError, KeyError, StopIteration):
            raise LearningContractError("TEACHING_BINDING_MISMATCH") from None
        return {
            "version": TEACHING_BINDING_VERSION,
            "publication_id": str(row.id),
            "publication_version": row.version,
            "plan_id": str(plan.id),
            "teaching_node_id": context["teaching_node_id"],
            "target_node_id": context["target_node_id"],
        }
    raise LearningContractError("TEACHING_BINDING_UNVERIFIED")
