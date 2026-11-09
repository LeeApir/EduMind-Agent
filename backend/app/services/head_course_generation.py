"""Finite head-goal bridge. Existing repository/fences/admission; no network or scheduler."""

import os
from copy import deepcopy
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.core.database import get_database_url
from app.models.free_course_planning import FreeCoursePlanningResult
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, digest


def require_development_database(url: str | None = None) -> None:
    value = make_url(url or get_database_url())
    if (
        value.drivername != "postgresql+asyncpg"
        or value.host != "127.0.0.1"
        or value.port != 15437
        or not (value.database or "").startswith("edumind_catalog_p15_t108_")
    ):
        raise SnapshotError("HEAD_DEVELOPMENT_DATABASE_REQUIRED")


def development_enabled() -> bool:
    if os.environ.get("EDUMIND_HEAD_GOAL_DEVELOPMENT") != "1":
        return False
    require_development_database()
    return True


async def enqueue(sessions, owner: UUID, body: dict[str, Any], key: str) -> dict[str, Any]:
    require_development_database()
    support = m.support_for_goal(body["goal"])
    if body.get("code_language", "c") != "c":
        raise SnapshotError("HEAD_GOAL_UNSUPPORTED")
    config = {"prompt_version": support["version"]}
    window_seconds = None
    if os.environ.get("EDUMIND_HEAD_DEEPSEEK_DEVELOPMENT") == "1":
        from scripts import head_course_deepseek_wire as direct

        if make_url(get_database_url()).database != direct.DATABASE or body["goal"] != m.FIXED_GOAL:
            raise SnapshotError("HEAD_DIRECT_OPERATION_REQUIRED")
        config["policy_version"] = direct.BATCH
        window_seconds = direct.WINDOW_SECONDS
    async with sessions() as db, db.begin():
        repo = SnapshotRepository(db, owner)
        result = await repo.create_course(
            body["goal"], key=key, config=config, operation_window_seconds=window_seconds
        )
        return result


async def generation_context(db: AsyncSession, owner: UUID, cid: UUID, oid: UUID) -> dict[str, Any]:
    from app.agents import head_course_planning_wire
    from app.agents.free_course_planning import request_digest
    from app.services.free_course_planning import load_inputs

    repo = SnapshotRepository(db, owner)
    request = await load_inputs(db, owner, cid, oid)
    if request.get("head_support") != m.support_for_goal(request["original_goal"]):
        raise SnapshotError("HEAD_REQUEST_MISMATCH")
    course = await repo.get_course(cid)
    if course["head_version"] != 1:
        raise SnapshotError("HEAD_OUTLINE_REQUIRED")
    version = await repo.get_version(cid, 1)
    row = await db.scalar(
        select(FreeCoursePlanningResult).where(
            FreeCoursePlanningResult.user_id == owner,
            FreeCoursePlanningResult.course_id == cid,
            FreeCoursePlanningResult.operation_id == oid,
            FreeCoursePlanningResult.plan_id == UUID(version["plan_id"]),
        )
    )
    if (
        row is None
        or row.state != "ready"
        or row.input_snapshot != request
        or row.prompt_version != head_course_planning_wire.PROMPT_VERSION
        or row.request_digest != request_digest(head_course_planning_wire.build_request(request))
    ):
        raise SnapshotError("HEAD_PLANNING_BINDING")
    if row.response_json is None or not isinstance(row.response_json.get("plan"), dict):
        raise SnapshotError("HEAD_PLANNING_BINDING")
    return dict(
        payload=m.content_payload(request, cast(dict[str, Any], row.response_json["plan"])),
        planning_result_id=str(row.id),
        plan_id=version["plan_id"],
        scene_id=version["scenes"][0]["scene_id"],
    )


def candidate(
    payload: dict[str, Any], raw: dict[str, Any], *, parent: str | None = None
) -> dict[str, Any]:
    m.validate_content(payload, raw)
    return dict(
        payload=payload,
        raw_output=deepcopy(raw),
        parent_digest=parent,
        candidate_digest=digest(
            "head-generated-candidate", payload=payload, raw=raw, parent=parent
        ),
    )


def source(record: dict[str, Any]) -> dict[str, Any]:
    c = record["candidate"]
    return dict(
        origin=m.ORIGIN,
        batch="PHASE-1.5-T108",
        candidate_digest=c["candidate_digest"],
        parent_digest=c["parent_digest"],
        model=record["model"],
        prompt_version=m.VERSION,
        plan_digest=digest("head-plan", plan=c["payload"]["plan"]),
        materials_digest=c["payload"]["materials"]["materials_digest"],
        evidence_kind=record["evidence_kind"],
    )


def fingerprint(row: FreeSceneGenerationResult) -> str:
    return digest(
        "head-generation-outcome",
        input_digest=row.input_digest,
        request_digest=row.request_digest,
        response=row.response_json,
        usage=row.usage_json,
        sent_attempts=row.sent_attempts,
        origin=row.origin_type,
    )


def validate_generation(
    row: FreeSceneGenerationResult, actual: dict[str, Any], operation=None
) -> dict[str, Any]:
    snapshot = row.input_snapshot
    if row.schema_version == "head-evidence-local-revision-v1":
        from app.services.head_course_evidence_publication import validate_publication

        return validate_publication(row, actual)
    if row.schema_version in (m.REUSE_VERSION, m.FIXED_VERSION, "head-aiapi-content-responses-v1"):
        from app.services.head_course_reuse import validate_publication

        return validate_publication(row, actual, operation)
    if row.schema_version == "head-f01-f02-four-text-v1":
        from app.services.head_course_fact_publication import validate_publication

        return validate_publication(row, actual)
    if row.schema_version == "head-questions-identical-duplicate-v1":
        from app.services.head_course_derivation import validate_derivation

        return validate_derivation(row, actual)
    record = cast(dict[str, Any], snapshot["generation"])
    c = record["candidate"]
    expected_payload = m.content_payload(actual["request"], actual["plan"]["candidate"])
    expected_candidate = candidate(expected_payload, c["raw_output"], parent=c["parent_digest"])
    if (
        row.origin_type != m.ORIGIN
        or row.sent_attempts != 1
        or row.state != "candidate"
        or row.reason_code is not None
        or snapshot["inputs"] != actual
        or c != expected_candidate
        or row.input_digest != digest("head-generation-input", snapshot=snapshot)
        or row.request_id != UUID(actual["request"]["request_id"])
        or row.request_digest != digest("head-http-request", body=record["request"])
        or row.response_digest != fingerprint(row)
        or row.response_json != m.assemble(expected_payload, c["raw_output"], source(record))
        or row.prompt_version != m.VERSION
        or row.schema_version != m.VERSION
        or row.usage_json != record["usage"]
        or record["model"] != "deepseek-flash"
        or record["evidence_kind"] not in ("actual_provider_response", "offline_fixture")
    ):
        raise SnapshotError("HEAD_GENERATION_BINDING")
    # Request/parent/receipt checks happen before this record is persisted and again on admission.
    parent = record["parent_candidate"]
    if (parent is None) != (c["parent_digest"] is None) or (
        parent is not None
        and (
            candidate(expected_payload, parent["raw_output"], parent=None) != parent
            or parent["candidate_digest"] != c["parent_digest"]
        )
    ):
        raise SnapshotError("HEAD_PARENT_BINDING")
    if record["request"] != m.body(expected_payload, parent, record["issues"]):
        raise SnapshotError("HEAD_REQUEST_BINDING")
    # All teaching fields render as Vue text interpolation, never HTML/Markdown execution.
    # Preserve original model text in both the private audit and the public text projection.
    cleaned = deepcopy(row.response_json)
    return dict(
        state="accepted",
        reason_code=None,
        findings=[],
        cleaned=dict(
            content=dict(blocks=cleaned["blocks"], generation_source=cleaned["generation_source"]),
            actions=cleaned["actions"],
            dependencies=[],
        ),
    )


async def publish(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    oid: UUID,
    records: list[dict[str, Any]],
    review: dict[str, Any],
) -> dict[str, Any]:
    from app.services.free_scene_availability import commit_scene
    from app.services.free_scene_generation import load_inputs
    from app.services.free_scene_validation import validate_candidate

    bind = db.bind
    if isinstance(bind, AsyncConnection):
        bind = bind.engine
    if not isinstance(bind, AsyncEngine):
        raise SnapshotError("HEAD_DEVELOPMENT_DATABASE_REQUIRED")
    require_development_database(bind.url.render_as_string(hide_password=False))
    if not 1 <= len(records) <= 2:
        raise SnapshotError("HEAD_REPAIR_LIMIT")
    context = await generation_context(db, owner, cid, oid)
    final = records[-1]["candidate"]
    if (
        review.get("candidate_digest") != final["candidate_digest"]
        or review.get("verdict") != "pass"
        or not review.get("independent_evaluator")
        or review.get("planning_basis_binding") != context["payload"]["planning_basis"]["binding"]
    ):
        raise SnapshotError("HEAD_REVIEW_REQUIRED")
    if records[0]["candidate"]["parent_digest"] is not None or (
        len(records) == 2 and final["parent_digest"] != records[0]["candidate"]["candidate_digest"]
    ):
        raise SnapshotError("HEAD_PARENT_BINDING")
    repo = SnapshotRepository(db, owner)
    fence = await repo.acquire_write_fence(cid, oid)
    actual = await load_inputs(
        db,
        owner,
        cid,
        oid,
        plan_id=UUID(context["plan_id"]),
        scene_id=UUID(context["scene_id"]),
        expected_head=1,
    )
    ids = []
    for i, record in enumerate(records):
        if record["candidate"]["payload"] != context["payload"]:
            raise SnapshotError("HEAD_REQUEST_MISMATCH")
        snapshot = dict(inputs=actual, generation=record, final_review=review)
        row = FreeSceneGenerationResult(
            user_id=owner,
            course_id=cid,
            operation_id=oid,
            request_id=UUID(actual["request"]["request_id"]),
            lease_epoch=fence.epoch,
            call_key=f"head-model-{i}",
            expected_head=1,
            input_snapshot=snapshot,
            input_digest=digest("head-generation-input", snapshot=snapshot),
            request_digest=digest("head-http-request", body=record["request"]),
            response_json=m.assemble(
                context["payload"], record["candidate"]["raw_output"], source(record)
            ),
            prompt_version=m.VERSION,
            schema_version=m.VERSION,
            state="candidate",
            reason_code=None,
            plan_id=UUID(context["plan_id"]),
            scene_id=UUID(context["scene_id"]),
            sent_attempts=1,
            usage_json=record["usage"],
            origin_type=m.ORIGIN,
        )
        row.response_digest = fingerprint(row)
        db.add(row)
        await db.flush()
        checked = await validate_candidate(db, owner, cid, fence, result_id=row.id)
        ids.append(str(row.id))
    ready = await commit_scene(
        db,
        owner,
        cid,
        fence,
        validation_id=UUID(checked["validation_id"]),
        expected_head=1,
        key="head-goal-ready:" + final["candidate_digest"],
    )
    op = await repo._operation(cid, oid)
    op.state = "succeeded"
    op.lease_token = None
    op.lease_expires_at = None
    return dict(
        course_id=str(cid),
        operation_id=str(oid),
        version=ready["version"],
        scene_id=context["scene_id"],
        generation_result_ids=ids,
        candidate_digest=final["candidate_digest"],
    )
