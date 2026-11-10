"""Fixed stack admission using the private course repository and existing write fence."""

from typing import Any
from uuid import UUID

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.core.database import get_database_url
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services import stack_course_materials as m
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, digest

DATABASE = "edumind_catalog_p15_t108_t119"
TEST_DATABASE = DATABASE + "_test"
WINDOW_SECONDS = 1800
CHECKS = frozenset(
    {
        "goal_and_beginner_level",
        "full_lesson_and_fact_citations",
        "all_five_frames_and_highlights",
        "lifo_and_distinct_top_vs_pop",
        "implementation_and_display_boundary",
        "four_transfer_questions_unique_no_hints",
        "answers_and_explanations",
    }
)


def require_database(url: str | None = None, *, fixture: bool = False) -> None:
    value = make_url(url or get_database_url())
    if (
        value.drivername != "postgresql+asyncpg"
        or value.host != "127.0.0.1"
        or value.port != 15437
        or value.database != (TEST_DATABASE if fixture else DATABASE)
    ):
        raise SnapshotError("STACK_DEVELOPMENT_DATABASE_REQUIRED")


def check_bind(db: AsyncSession, *, fixture: bool) -> None:
    bind = db.bind
    if isinstance(bind, AsyncConnection):
        bind = bind.engine
    if not isinstance(bind, AsyncEngine):
        raise SnapshotError("STACK_DEVELOPMENT_DATABASE_REQUIRED")
    require_database(bind.url.render_as_string(hide_password=False), fixture=fixture)


async def prepare(db: AsyncSession, owner: UUID, *, fixture: bool = False) -> dict[str, Any]:
    from app.services.free_scene_availability import commit_outline

    check_bind(db, fixture=fixture)
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(
        m.GOAL,
        key=m.BATCH,
        config={"prompt_version": m.VERSION, "policy_version": m.BATCH},
        operation_window_seconds=WINDOW_SECONDS,
    )
    cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
    if (await repo.get_course(cid))["head_version"] is None:
        fence = await repo.acquire_write_fence(cid, oid)
        plan = await repo.store_plan(
            cid,
            fence,
            expected_head=None,
            key="stack-plan",
            candidate=m.outline(),
        )
        await commit_outline(
            db, owner, cid, fence, plan_id=UUID(plan["plan_id"]), key="stack-outline"
        )
        op = await repo._operation(cid, oid)
        op.lease_token, op.lease_expires_at = None, None
    return await context(db, owner, cid, oid, fixture=fixture)


async def context(
    db: AsyncSession, owner: UUID, cid: UUID, oid: UUID, *, fixture: bool = False
) -> dict[str, Any]:
    from app.services.free_scene_generation import load_inputs

    check_bind(db, fixture=fixture)
    repo = SnapshotRepository(db, owner)
    op = await repo._operation(cid, oid)
    course = await repo.get_course(cid)
    if (
        course["original_goal"] != m.GOAL
        or course["head_version"] != 1
        or op.config_snapshot.get("prompt_version") != m.VERSION
        or op.config_snapshot.get("policy_version") != m.BATCH
        or op.kind != "create"
        or op.state not in {"queued", "running"}
        or op.cancel_requested_at is not None
        or op.deadline_at <= await repo._now()
        or (op.deadline_at - op.created_at).total_seconds() != WINDOW_SECONDS
    ):
        raise SnapshotError("STACK_OPERATION_STOPPED_OR_MISMATCH")
    version = await repo.get_version(cid, 1)
    pid, sid = version["plan_id"], version["scenes"][0]["scene_id"]
    inputs = await load_inputs(
        db, owner, cid, oid, plan_id=UUID(pid), scene_id=UUID(sid), expected_head=1
    )
    if inputs["plan"]["candidate"] != m.outline():
        raise SnapshotError("STACK_PLAN_BINDING")
    # The foreground request binds to the outline across leases. Scene admission still
    # checks the current epoch against its own write fence and snapshot.
    del inputs["lease_epoch"]
    return dict(
        owner=str(owner),
        course_id=str(cid),
        operation_id=str(oid),
        plan_id=pid,
        scene_id=sid,
        request_id=str(op.request_id),
        starts_at=op.created_at.isoformat(),
        expires_at=op.deadline_at.isoformat(),
        binding=digest("stack-course-context", inputs=inputs),
        evidence_kind="offline_fixture" if fixture else "actual_provider_response",
    )


def candidate(
    ctx: dict[str, Any], output: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, Any]:
    mat = m.materials()
    m.validate_content(output, mat)
    data = dict(
        context=ctx,
        raw_output=output,
        receipt=receipt,
        plan_digest=digest("stack-plan", plan=m.outline()),
        materials_digest=mat["materials_digest"],
    )
    return {**data, "candidate_digest": digest("stack-course-candidate", data=data)}


def assembly(c: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    evaluator = review.get("independent_evaluator")
    if (
        review.get("candidate_digest") != c["candidate_digest"]
        or review.get("verdict") != "pass"
        or not isinstance(evaluator, str)
        or not evaluator.strip()
        or review.get("blocking_findings") != []
        or review.get("checks") != dict.fromkeys(CHECKS, True)
        or any(type(v) is not bool for v in review["checks"].values())
    ):
        raise SnapshotError("STACK_REVIEW_REQUIRED")
    source = dict(
        origin=m.ORIGIN,
        batch=m.BATCH,
        model=m.request()["model"],
        prompt_version=m.VERSION,
        parent_digest=None,
        evidence_kind=c["context"]["evidence_kind"],
        candidate_digest=c["candidate_digest"],
        materials_digest=c["materials_digest"],
        plan_digest=c["plan_digest"],
        teaching_review=dict(verdict="pass", independent_evaluator=evaluator),
    )
    return m.assemble(c["raw_output"], source)


def fingerprint(row: FreeSceneGenerationResult) -> str:
    return digest(
        "stack-generation-outcome",
        input_digest=row.input_digest,
        request_digest=row.request_digest,
        response=row.response_json,
        state=row.state,
        usage=row.usage_json,
        sent_attempts=row.sent_attempts,
    )


async def validate_publication(db, row, actual, operation) -> dict[str, Any]:
    snapshot = row.input_snapshot
    c = snapshot["candidate"]
    ctx = c["context"]
    expected = await context(
        db,
        row.user_id,
        row.course_id,
        row.operation_id,
        fixture=ctx["evidence_kind"] == "offline_fixture",
    )
    raw = assembly(c, snapshot["review"])
    if (
        operation.id != row.operation_id
        or row.origin_type != "model_generation"
        or row.state != "candidate"
        or row.reason_code is not None
        or row.sent_attempts != 1
        or row.expected_head != 1
        or row.prompt_version != m.VERSION
        or ctx != expected
        or row.input_snapshot["inputs"] != actual
        or c != candidate(expected, c["raw_output"], c["receipt"])
        or str(row.request_id) != ctx["request_id"]
        or str(row.scene_id) != ctx["scene_id"]
        or str(row.plan_id) != ctx["plan_id"]
        or row.input_digest != digest("stack-generation-input", snapshot=snapshot)
        or row.request_digest != digest("stack-http-request", body=m.request())
        or row.usage_json != c["receipt"]["usage"]
        or row.response_digest != fingerprint(row)
        or row.response_json != raw
    ):
        raise SnapshotError("STACK_PUBLICATION_BINDING")
    return dict(
        state="accepted",
        reason_code=None,
        findings=[],
        cleaned=dict(
            content=dict(blocks=raw["blocks"], generation_source=raw["generation_source"]),
            actions=raw["actions"],
            dependencies=[],
        ),
    )


async def publish(db, c, review) -> dict[str, Any]:
    from app.services.free_scene_availability import commit_scene
    from app.services.free_scene_generation import load_inputs
    from app.services.free_scene_validation import validate_candidate

    ctx = c["context"]
    owner, cid, oid, pid, sid = (
        UUID(ctx[k])
        for k in (
            "owner",
            "course_id",
            "operation_id",
            "plan_id",
            "scene_id",
        )
    )
    expected = await context(db, owner, cid, oid, fixture=ctx["evidence_kind"] == "offline_fixture")
    if c != candidate(expected, c["raw_output"], c["receipt"]):
        raise SnapshotError("STACK_PUBLICATION_BINDING")
    raw = assembly(c, review)
    repo = SnapshotRepository(db, owner)
    fence = await repo.acquire_write_fence(cid, oid)
    actual = await load_inputs(db, owner, cid, oid, plan_id=pid, scene_id=sid, expected_head=1)
    snapshot = dict(inputs=actual, candidate=c, review=review)
    row = FreeSceneGenerationResult(
        user_id=owner,
        course_id=cid,
        operation_id=oid,
        request_id=UUID(ctx["request_id"]),
        lease_epoch=fence.epoch,
        expected_head=1,
        call_key=m.BATCH,
        plan_id=pid,
        scene_id=sid,
        input_digest=digest("stack-generation-input", snapshot=snapshot),
        request_digest=digest("stack-http-request", body=m.request()),
        input_snapshot=snapshot,
        response_json=raw,
        usage_json=c["receipt"]["usage"],
        origin_type="model_generation",
        prompt_version=m.VERSION,
        schema_version=m.VERSION,
        sent_attempts=1,
        state="candidate",
        reason_code=None,
    )
    row.response_digest = fingerprint(row)
    db.add(row)
    await db.flush()
    validated = await validate_candidate(db, owner, cid, fence, result_id=row.id)
    ready = await commit_scene(
        db,
        owner,
        cid,
        fence,
        validation_id=UUID(validated["validation_id"]),
        expected_head=1,
        key="stack-ready:" + c["candidate_digest"],
    )
    operation = await repo._operation(cid, oid)
    operation.state, operation.lease_token, operation.lease_expires_at = "succeeded", None, None
    return dict(
        course_id=str(cid),
        operation_id=str(oid),
        version=ready["version"],
        scene_id=str(sid),
        scene_version_id=ready["scene_version_id"],
        candidate_digest=c["candidate_digest"],
    )
