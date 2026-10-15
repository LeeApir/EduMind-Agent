"""Atomic publication of complete planned units; no model calls inside transactions."""

from copy import deepcopy
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.hybrid_resource_review import hard_checks, route_review
from app.agents.unit_consistency_review import resource_review_priority
from app.models.classroom import ClassroomSession
from app.models.learning import (
    GeneratedResource,
    LearningOperation,
    LearningScene,
    LearningUnit,
    utc_now,
)
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_publication import LearningPublication, LearningPublicationWithdrawal
from app.models.learning_review import LearningReviewRecord
from app.models.learning_review_case import LearningReviewCase, LearningReviewDecision
from app.services.learning_contract import LearningContractError, canonical
from app.services.learning_owner_lock import lock_learning_owner
from app.services.learning_policy import POLICY_VERSION, active_policy_digest
from app.services.learning_review_cases import (
    case_current,
    invalidate_case,
    locked_case,
    operation_context_current,
)
from app.services.teaching_actions import anchor_catalog
from app.services.unit_material import restore_material


async def current_publication(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID, version: int | None = None
) -> LearningPublication | None:
    unit = await db.get(LearningUnit, unit_id)
    if unit is None or unit.user_id != owner_id:
        return None
    query = select(LearningPublication).where(
        LearningPublication.user_id == owner_id, LearningPublication.learning_unit_id == unit_id
    )
    query = (
        query.where(LearningPublication.version == version)
        if version is not None
        else query.where(LearningPublication.id == unit.current_publication_id)
    )
    row = await db.scalar(query)
    if row is None or (await db.get(LearningPublicationWithdrawal, row.id)) is not None:
        return None
    return row


async def publication_for_resource(db: AsyncSession, resource: GeneratedResource) -> bool:
    if resource.plan_id is None:
        return False
    rows = (
        await db.scalars(
            select(LearningPublication).where(
                LearningPublication.user_id == resource.user_id,
                LearningPublication.learning_unit_id == resource.learning_unit_id,
                LearningPublication.plan_id == resource.plan_id,
            )
        )
    ).all()
    for row in rows:
        if await db.get(LearningPublicationWithdrawal, row.id):
            continue
        material = cast(dict[str, Any], row.material)
        if any(
            s["resource_id"] == str(resource.id) and s["resource_digest"] == resource.content_digest
            for s in material["scenes"]
        ):
            return True
    return False


async def stage_candidates(db: AsyncSession, workspace: Any) -> list[dict[str, Any]]:
    """Persist pending candidates, including corrected history, without any published_at."""
    b = workspace.binding
    owner_id = UUID(b["owner_id"])
    unit_id = UUID(b["unit_id"])
    await lock_learning_owner(db, owner_id)
    final_ids = {c.id for c in workspace.candidates()}
    scenes = []
    for c in workspace.history():
        existing = await db.get(GeneratedResource, UUID(c.id))
        if existing:
            scene = await db.get(LearningScene, existing.scene_id)
            assert scene
        else:
            latest = await db.scalar(
                select(func.max(LearningScene.version)).where(
                    LearningScene.learning_unit_id == unit_id, LearningScene.scene_key == c.role
                )
            )
            scene = LearningScene(
                learning_unit_id=unit_id,
                plan_id=UUID(b["plan_id"]),
                scene_key=c.role,
                scene_order=("explanation", "code", "exercise").index(c.role) + 1,
                scene_type=c.role,
                version=(latest or 0) + 1,
                dependency_digest=c.dependency_digest,
                input_snapshot={"upstream": list(c.upstream)},
                generation_status="complete",
            )
            db.add(scene)
            await db.flush()
            db.add(
                GeneratedResource(
                    id=UUID(c.id),
                    user_id=owner_id,
                    learning_unit_id=unit_id,
                    scene_id=scene.id,
                    plan_id=UUID(b["plan_id"]),
                    resource_type=c.role,
                    knowledge_point_id=str(workspace.plan["node_id"]),
                    content=deepcopy(c.envelope["content"]),
                    content_digest=c.content_digest,
                    dependency_digest=c.dependency_digest,
                    review_status="pending",
                    generation_metadata={
                        "prompt_version": c.envelope["prompt_version"],
                        "instruction_version": "planned-scene-content-v1",
                    },
                )
            )
            await db.flush()
        if c.id in final_ids:
            scenes.append(
                {
                    "role": c.role,
                    "scene_key": c.role,
                    "scene_id": str(scene.id),
                    "scene_version": scene.version,
                    "resource_id": c.id,
                    "resource_digest": c.content_digest,
                    "dependency_digest": c.dependency_digest,
                }
            )
    scenes.sort(key=lambda s: ("explanation", "code", "exercise").index(s["role"]))
    return scenes


async def publication_checks(
    db: AsyncSession, material: dict[str, Any], review_ids: list[UUID]
) -> str:
    workspace, value = restore_material(material)
    b = value["binding"]
    plan = await db.get(LearningPlanVersion, UUID(b["plan_id"]))
    if (
        not plan
        or str(plan.user_id) != b["owner_id"]
        or str(plan.learning_unit_id) != b["unit_id"]
        or canonical(plan.plan_json) != canonical(workspace.plan)
        or plan.plan_digest != b["plan_digest"]
        or plan.input_digest != b["input_digest"]
        or plan.references_digest != b["references_digest"]
        or plan.policy_digest != b["policy_digest"]
        or plan.policy_version != POLICY_VERSION
        or plan.policy_digest != active_policy_digest()
    ):
        raise LearningContractError("PUBLICATION_PLAN_STALE")
    latest = await db.scalar(
        select(func.max(LearningPlanVersion.version)).where(
            LearningPlanVersion.learning_unit_id == plan.learning_unit_id
        )
    )
    if latest != plan.version:
        raise LearningContractError("PUBLICATION_PLAN_STALE")
    snapshot_context = plan.input_snapshot.get("reference_context")
    if snapshot_context is not None and canonical(snapshot_context) != canonical(
        workspace.reference_context
    ):
        raise LearningContractError("REFERENCE_CONTEXT_STALE")
    for c, s in zip(workspace.candidates(), value["scenes"], strict=True):
        hard_checks(c)
        resource = await db.get(GeneratedResource, UUID(c.id))
        scene = await db.get(LearningScene, UUID(s["scene_id"]))
        if (
            not resource
            or not scene
            or resource.user_id != plan.user_id
            or resource.learning_unit_id != plan.learning_unit_id
            or resource.plan_id != plan.id
            or resource.scene_id != scene.id
            or scene.plan_id != plan.id
            or scene.version != s["scene_version"]
            or scene.scene_key != c.role
            or resource.content_digest != c.content_digest
            or resource.dependency_digest != c.dependency_digest
            or canonical(resource.content) != canonical(c.envelope["content"])
        ):
            raise LearningContractError("PUBLICATION_RESOURCE_STALE")
    rows = [await db.get(LearningReviewRecord, id) for id in review_ids]
    if len(rows) != 4 or any(
        not r
        or r.user_id != plan.user_id
        or r.plan_id != plan.id
        or str(r.operation_id) != b["operation_id"]
        for r in rows
    ):
        raise LearningContractError("PUBLICATION_REVIEWS_INCOMPLETE")
    records = [cast(dict[str, Any], r.record) for r in rows if r]
    prior = resource_review_priority(value, records[:3])
    unit_review = records[3]
    if (
        unit_review["target_digest"] != value["unit_digest"]
        or canonical(unit_review["binding"]) != canonical(b)
        or unit_review["result"]["scope"] != "unit"
    ):
        raise LearningContractError("PUBLICATION_CONSISTENCY_STALE")
    # Independently recheck stored routing and anchor catalogs against actual candidates.
    for i, r in enumerate(records):
        candidates = (workspace.candidates()[i],) if i < 3 else workspace.candidates()
        catalog = anchor_catalog(candidates)
        if canonical(catalog) != canonical(r["anchor_catalog"]):
            raise LearningContractError("REVIEW_ANCHOR_STALE")
        calculated = route_review(
            r["result"], scope="resource" if i < 3 else "unit", catalog=catalog
        )["verdict"]
        stored = r["local_routing"]["verdict"]
        if calculated == "reject" and stored != "reject":
            raise LearningContractError("REVIEW_ROUTING_INVALID")
        if stored == "pass" and calculated != "pass":
            raise LearningContractError("REVIEW_ROUTING_INVALID")
    verdict = unit_review["local_routing"]["verdict"]
    if prior == "rejected" or verdict == "reject":
        return "rejected"
    if verdict not in ("pass", "needs_human"):
        raise LearningContractError("CONSISTENCY_NOT_FINAL")
    return (
        "needs_human"
        if prior == "needs_human" or verdict == "needs_human" or not workspace.reference_context
        else "auto_ready"
    )


async def publish_complete_unit(
    db: AsyncSession,
    material: dict[str, Any],
    review_ids: list[UUID],
    *,
    case: LearningReviewCase | None = None,
) -> LearningPublication:
    _, material = restore_material(material)
    b = material["binding"]
    uid = UUID(b["owner_id"])
    unit_id = UUID(b["unit_id"])
    await lock_learning_owner(db, uid)
    unit = await db.scalar(
        select(LearningUnit)
        .where(LearningUnit.id == unit_id, LearningUnit.user_id == uid)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not unit or unit.status == "withdrawn":
        raise LearningContractError("UNIT_NOT_AVAILABLE")
    existing = await db.scalar(
        select(LearningPublication).where(
            LearningPublication.operation_id == UUID(b["operation_id"])
        )
    )
    if existing:
        if (
            existing.unit_digest != material["unit_digest"]
            or canonical(existing.material) != canonical(material)
            or existing.review_ids != [str(v) for v in review_ids]
        ):
            raise LearningContractError("PUBLICATION_REPLAY_CONFLICT")
        return existing
    op = await db.scalar(
        select(LearningOperation)
        .where(LearningOperation.id == UUID(b["operation_id"]), LearningOperation.user_id == uid)
        .execution_options(populate_existing=True)
    )
    if not op or op.status not in ("accepted", "running", "awaiting_human"):
        raise LearningContractError("OPERATION_NOT_ACTIVE")
    if not await operation_context_current(db, op):
        raise LearningContractError("CLASSROOM_VERSION_CONFLICT")
    state = await publication_checks(db, material, review_ids)
    decision = None
    if state == "rejected":
        raise LearningContractError("CURRENT_CANDIDATE_REJECTED")
    if state == "needs_human":
        if case is None:
            raise LearningContractError("HUMAN_REVIEW_REQUIRED")
        case = await locked_case(db, owner_id=uid, case_id=case.id)
        if (
            case.state != "approved"
            or case.operation_id != op.id
            or not await case_current(db, case)
            or cast(dict[str, Any], case.payload)["material"]["unit_digest"]
            != material["unit_digest"]
        ):
            raise LearningContractError("REVIEW_CASE_INVALIDATED")
        decision = await db.scalar(
            select(LearningReviewDecision).where(
                LearningReviewDecision.case_id == case.id,
                LearningReviewDecision.case_digest == case.case_digest,
                LearningReviewDecision.verdict == "approve",
            )
        )
        if not decision:
            raise LearningContractError("HUMAN_DECISION_REQUIRED")
    version = await db.scalar(
        select(func.max(LearningPublication.version)).where(
            LearningPublication.learning_unit_id == unit_id
        )
    )
    publication = LearningPublication(
        user_id=uid,
        learning_unit_id=unit_id,
        plan_id=UUID(b["plan_id"]),
        operation_id=op.id,
        version=(version or 0) + 1,
        unit_digest=material["unit_digest"],
        material=deepcopy(material),
        review_ids=[str(v) for v in review_ids],
        approval_source="human_assisted" if decision else "auto",
        decision_id=decision.id if decision else None,
    )
    db.add(publication)
    await db.flush()
    for s in material["scenes"]:
        resource = await db.get(GeneratedResource, UUID(s["resource_id"]))
        scene = await db.get(LearningScene, UUID(s["scene_id"]))
        assert resource and scene
        if resource.published_at is not None:
            raise LearningContractError("CANDIDATE_ALREADY_PUBLISHED")
        resource.review_status = "passed"
        resource.published_at = utc_now()
        resource.review_comments = {
            "approval_source": publication.approval_source,
            "publication_id": str(publication.id),
        }
        scene.review_status = "passed"
    unit.status = "ready"
    unit.current_publication_id = publication.id
    unit.review_summary = {
        "approval_source": publication.approval_source,
        "publication_version": publication.version,
    }
    op.status = "completed"
    op.scene_id = UUID(material["scenes"][0]["scene_id"])
    op.published_scene_version = material["scenes"][0]["scene_version"]
    op.updated_at = utc_now()
    session = await db.scalar(
        select(ClassroomSession).where(
            ClassroomSession.user_id == uid, ClassroomSession.learning_unit_id == unit_id
        )
    )
    if session:
        session.scene_key = "explanation"
        session.scene_version = int(material["scenes"][0]["scene_version"])
        session.publication_version = publication.version
        session.revision += 1
        session.generation_id = None
        session.scene_progress = 0
        session.updated_at = utc_now()
    if op.publication_expectation:
        from app.models.classroom import ClassroomOperation

        classroom_op = await db.get(
            ClassroomOperation, UUID(str(op.publication_expectation["classroom_operation_id"]))
        )
        if classroom_op:
            classroom_op.status = "published"
            classroom_op.result_id = UUID(material["scenes"][0]["scene_id"])
            classroom_op.result_snapshot = {
                **(classroom_op.result_snapshot or {}),
                "scene_version": material["scenes"][0]["scene_version"],
                "publication_version": publication.version,
                "resource_ids": [s["resource_id"] for s in material["scenes"]],
            }
    if case:
        case.state = "published"
        case.updated_at = utc_now()
    await db.flush()
    return publication


async def publish_approved_case(
    db: AsyncSession, *, owner_id: UUID, case_id: UUID
) -> LearningPublication:
    case = await locked_case(db, owner_id=owner_id, case_id=case_id)
    payload = cast(dict[str, Any], case.payload)
    return await publish_complete_unit(
        db, payload["material"], [UUID(v) for v in payload["review_ids"]], case=case
    )


async def withdraw_publication(
    db: AsyncSession, *, owner_id: UUID, publication_id: UUID, reason_code: str
) -> None:
    await lock_learning_owner(db, owner_id)
    row = await db.get(LearningPublication, publication_id)
    if not row or row.user_id != owner_id:
        raise LearningContractError("PUBLICATION_NOT_FOUND")
    if not await db.get(LearningPublicationWithdrawal, row.id):
        db.add(
            LearningPublicationWithdrawal(
                publication_id=row.id,
                user_id=owner_id,
                learning_unit_id=row.learning_unit_id,
                reason_code=reason_code,
            )
        )
    for case in (
        await db.scalars(
            select(LearningReviewCase).where(
                LearningReviewCase.user_id == owner_id,
                LearningReviewCase.learning_unit_id == row.learning_unit_id,
                LearningReviewCase.state.in_(("pending", "approved")),
            )
        )
    ).all():
        await invalidate_case(db, case)
    unit = await db.get(LearningUnit, row.learning_unit_id)
    if unit and unit.current_publication_id == row.id:
        unit.status = "withdrawn"
    await db.flush()
