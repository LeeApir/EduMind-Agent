"""Private read-only projection of one case's operation audits and candidate revisions."""

from copy import deepcopy
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import GeneratedResource, LearningScene
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_review import LearningReviewRecord
from app.models.learning_review_case import LearningReviewCase
from app.models.plan_check import PlanCheck, PlanCheckResolution, PlanRebuildEvent
from app.services.learning_contract import LearningContractError, digest, validate_contract
from app.services.plan_check import record_digest


async def case_review_history(db: AsyncSession, case: LearningReviewCase) -> dict[str, Any]:
    """Inspect stale cases too; never change state, decide, publish, lock or call models."""
    payload = cast(dict[str, Any], deepcopy(case.payload))
    if digest("review-case", "learning-review-case-v1", payload=payload) != case.case_digest:
        raise LearningContractError("REVIEW_HISTORY_CASE_INVALID")
    material = payload["material"]
    binding = material["binding"]
    expected = {
        "owner_id": str(case.user_id),
        "unit_id": str(case.learning_unit_id),
        "operation_id": str(case.operation_id),
        "plan_id": str(case.plan_id),
    }
    if any(binding[k] != value for k, value in expected.items()):
        raise LearningContractError("REVIEW_HISTORY_CASE_INVALID")
    final_ids = list(payload["review_ids"])
    final_candidates = {c["resource_id"]: c for c in material["candidates"]}
    issues: list[dict[str, Any]] = []
    if len(final_ids) != 4 or len(set(final_ids)) != 4:
        issues.append({"code": "FINAL_REVIEW_SET_INVALID"})
    # no_autoflush prevents this read projection from flushing caller-owned pending changes.
    with db.no_autoflush:
        rows = (
            await db.scalars(
                select(LearningReviewRecord).where(
                    LearningReviewRecord.user_id == case.user_id,
                    LearningReviewRecord.learning_unit_id == case.learning_unit_id,
                    LearningReviewRecord.operation_id == case.operation_id,
                )
            )
        ).all()
        plan_checks = (
            await db.scalars(
                select(PlanCheck)
                .where(
                    PlanCheck.user_id == case.user_id,
                    PlanCheck.learning_unit_id == case.learning_unit_id,
                    PlanCheck.operation_id == case.operation_id,
                )
                .order_by(PlanCheck.created_at, PlanCheck.id)
            )
        ).all()
        plan_notes = (
            await db.scalars(
                select(PlanCheckResolution)
                .where(
                    PlanCheckResolution.user_id == case.user_id,
                    PlanCheckResolution.learning_unit_id == case.learning_unit_id,
                    PlanCheckResolution.operation_id == case.operation_id,
                )
                .order_by(PlanCheckResolution.created_at, PlanCheckResolution.id)
            )
        ).all()
        rebuild_events = (
            await db.scalars(
                select(PlanRebuildEvent)
                .where(
                    PlanRebuildEvent.user_id == case.user_id,
                    PlanRebuildEvent.learning_unit_id == case.learning_unit_id,
                    PlanRebuildEvent.operation_id == case.operation_id,
                )
                .order_by(PlanRebuildEvent.created_at, PlanRebuildEvent.id)
            )
        ).all()
        if any(
            row.record_digest != record_digest(row.record, "rebuild_event")
            for row in rebuild_events
        ):
            raise LearningContractError("PLAN_REBUILD_EVIDENCE_CHANGED")
        if any(row.record_digest != record_digest(row.record) for row in plan_checks) or any(
            row.record_digest != record_digest(row.record, "resolution") for row in plan_notes
        ):
            raise LearningContractError("PLAN_CHECK_CHANGED")
        records = []
        for row in rows:
            value = validate_contract(row.record, "review_record")
            b = value["binding"]
            if (
                value["review_id"] != str(row.id)
                or value["target_digest"] != row.target_digest
                or any(b[k] != expected[k] for k in ("owner_id", "unit_id", "operation_id"))
                or b["plan_id"] != str(row.plan_id)
            ):
                raise LearningContractError("REVIEW_HISTORY_BINDING_INVALID")
            records.append(value)
        # Server-authored UTC record timestamps; ties use review ID, not invented send order.
        records.sort(key=lambda r: (r["created_at"], r["review_id"]))
        found_ids = {r["review_id"] for r in records}
        missing_reviews = sorted(set(final_ids) - found_ids)
        if missing_reviews:
            issues.append({"code": "FINAL_REVIEWS_MISSING", "ids": missing_reviews})
        plan_ids = (
            {UUID(r["binding"]["plan_id"]) for r in records}
            | {case.plan_id}
            | {row.plan_id for row in plan_checks}
        )
        plans = (
            await db.scalars(
                select(LearningPlanVersion).where(
                    LearningPlanVersion.user_id == case.user_id,
                    LearningPlanVersion.learning_unit_id == case.learning_unit_id,
                    LearningPlanVersion.id.in_(plan_ids),
                )
            )
        ).all()
        plan_map = {str(p.id): p for p in plans}
        missing_plans = sorted(str(p) for p in plan_ids if str(p) not in plan_map)
        if missing_plans:
            issues.append({"code": "PLANS_MISSING", "ids": missing_plans})
        references: dict[str, set[tuple[str, str]]] = {}
        for record in records:
            for a in record["anchor_catalog"]:
                references.setdefault(a["resource_id"], set()).add(
                    (record["binding"]["plan_id"], a["resource_digest"])
                )
        for rid, c in final_candidates.items():
            references.setdefault(rid, set()).add((str(case.plan_id), c["content_digest"]))
        resource_rows = (
            await db.execute(
                select(GeneratedResource, LearningScene)
                .join(
                    LearningScene,
                    GeneratedResource.scene_id == LearningScene.id,
                )
                .where(
                    GeneratedResource.user_id == case.user_id,
                    GeneratedResource.learning_unit_id == case.learning_unit_id,
                    GeneratedResource.id.in_([UUID(rid) for rid in references]),
                    LearningScene.learning_unit_id == case.learning_unit_id,
                )
            )
        ).all()
        resources = []
        for resource, scene in resource_rows:
            rid = str(resource.id)
            if (
                references[rid] != {(str(resource.plan_id), resource.content_digest)}
                or scene.plan_id != resource.plan_id
            ):
                raise LearningContractError("REVIEW_HISTORY_BINDING_INVALID")
            resources.append(
                {
                    "resource_id": rid,
                    "role": resource.resource_type,
                    "plan_id": str(resource.plan_id),
                    "scene_id": str(scene.id),
                    "scene_version": scene.version,
                    "resource_version": resource.version,
                    "content_digest": resource.content_digest,
                    "dependency_digest": resource.dependency_digest,
                    "content": deepcopy(resource.content),
                    "generation_metadata": deepcopy(resource.generation_metadata),
                    "stored_review_status": resource.review_status,
                    "is_final_for_case": rid in final_candidates,
                    "resource_review_ids": [
                        r["review_id"]
                        for r in records
                        if r["result"]["scope"] == "resource"
                        and any(a["resource_id"] == rid for a in r["anchor_catalog"])
                    ],
                }
            )
        role_order = {"explanation": 0, "code": 1, "exercise": 2}
        resources.sort(
            key=lambda c: (role_order.get(c["role"], 3), c["scene_version"], c["resource_id"])
        )
        missing_resources = sorted(set(references) - {r["resource_id"] for r in resources})
        if missing_resources:
            issues.append({"code": "CANDIDATES_MISSING", "ids": missing_resources})
    revisions = []
    for role in ("explanation", "code", "exercise"):
        prior = None
        for current in (r for r in resources if r["role"] == role):
            if prior is not None:
                revisions.append(
                    {
                        "role": role,
                        "before_resource_id": prior["resource_id"],
                        "after_resource_id": current["resource_id"],
                        "before_digest": prior["content_digest"],
                        "after_digest": current["content_digest"],
                        "content_changed": prior["content_digest"] != current["content_digest"],
                        "before_review_ids": prior["resource_review_ids"],
                        "after_review_ids": current["resource_review_ids"],
                    }
                )
            prior = current
    return {
        "plan_checks": [deepcopy(row.record) for row in plan_checks],
        "plan_rebuild_events": [deepcopy(row.record) for row in rebuild_events],
        "plan_check_notes": [deepcopy(row.record) for row in plan_notes],
        "automatic_reviews": records,  # Backward-compatible field now includes all history.
        "review_history": {
            "version": "learning-review-history-v1",
            "scope": expected,
            "ordering": "server record.created_at then review_id; ties do not prove send order",
            "final_review_ids": final_ids,
            "complete": not issues,
            "issues": issues,
            "entries": [
                {
                    "sequence": i + 1,
                    "review_id": r["review_id"],
                    "is_final_for_case": r["review_id"] in final_ids,
                    "scope": r["result"]["scope"],
                    "plan_id": r["binding"]["plan_id"],
                    "target_digest": r["target_digest"],
                    "candidate_ids": sorted({a["resource_id"] for a in r["anchor_catalog"]}),
                }
                for i, r in enumerate(records)
            ],
        },
        "candidate_history": resources,
        "candidate_revisions": revisions,
        "revision_note": (
            "Consecutive persisted scene versions, not a stored causal generation wire. "
            "No missing review or model feedback is inferred."
        ),
        "plan_history": [
            {
                "plan_id": str(p.id),
                "version": p.version,
                "is_case_plan": p.id == case.plan_id,
                "plan_digest": p.plan_digest,
                "input_digest": p.input_digest,
                "policy_digest": p.policy_digest,
                "plan": deepcopy(p.plan_json),
                "input_snapshot": deepcopy(p.input_snapshot),
                "references_snapshot": deepcopy(p.references_snapshot),
            }
            for p in sorted(plans, key=lambda p: (p.version, str(p.id)))
        ],
    }
