"""Fixed-outline trial admission through the existing private course repository."""

from dataclasses import dataclass
from types import ModuleType
from typing import Any
from uuid import UUID

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.core.database import get_database_url
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services import (
    binary_search_course_materials,
    queue_course_materials,
    queue_course_revision,
    stack_course_materials,
)
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, digest

WINDOW_SECONDS = 1800


@dataclass(frozen=True)
class FixedCourse:
    topic: str
    materials: ModuleType
    database: str
    package: str
    approval_key: str
    checks: frozenset[str]

    def error(self, suffix: str) -> SnapshotError:
        return SnapshotError(f"{self.topic.upper()}_{suffix}")


REVIEW_CHECKS = frozenset(
    {
        "goal_and_beginner_level",
        "full_lesson_and_fact_citations",
        "all_five_frames_and_highlights",
        "implementation_and_display_boundary",
        "four_transfer_questions_unique_no_hints",
        "answers_and_explanations",
    }
)
STACK = FixedCourse(
    "stack",
    stack_course_materials,
    "edumind_catalog_p15_t108_t119",
    "phase-1.5-stack-lifo-t119",
    "accept_T119_scope_and_batch_C2",
    REVIEW_CHECKS | {"lifo_and_distinct_top_vs_pop"},
)
QUEUE = FixedCourse(
    "queue",
    queue_course_materials,
    "edumind_catalog_p15_t121_queue",
    "phase-1.5-queue-fifo-t121",
    "accept_T121_scope_and_batch_C2",
    REVIEW_CHECKS
    | {"fifo_and_distinct_front_rear_vs_dequeue", "shift_cost_and_effective_elements"},
)
QUEUE_REVISION = FixedCourse(
    QUEUE.topic,
    queue_course_revision,
    QUEUE.database,
    "phase-1.5-queue-fifo-t121/q01-revision",
    "accept_T121_Q01_scope_and_batch_C2",
    QUEUE.checks,
)
BINARY_SEARCH = FixedCourse(
    "binary-search",
    binary_search_course_materials,
    "edumind_catalog_p15_t122_binary_search",
    "phase-1.5-binary-search-t122",
    "accept_T122_scope_and_batch_C2",
    (REVIEW_CHECKS - {"all_five_frames_and_highlights"})
    | {"all_six_frames_and_highlights", "closed_interval_and_comparisons",
       "termination_and_duplicates"},
)
PROFILES = {
    profile.materials.VERSION: profile for profile in (STACK, QUEUE, QUEUE_REVISION, BINARY_SEARCH)
}


def require_database(
    url: str | None = None, *, fixture: bool = False, profile: FixedCourse = STACK
) -> None:
    value = make_url(url or get_database_url())
    if (
        value.drivername != "postgresql+asyncpg"
        or value.host != "127.0.0.1"
        or value.port != 15437
        or value.database != (profile.database + "_test" if fixture else profile.database)
    ):
        raise profile.error("DEVELOPMENT_DATABASE_REQUIRED")


def check_bind(db: AsyncSession, *, fixture: bool, profile: FixedCourse) -> None:
    bind = db.bind
    if isinstance(bind, AsyncConnection):
        bind = bind.engine
    if not isinstance(bind, AsyncEngine):
        raise profile.error("DEVELOPMENT_DATABASE_REQUIRED")
    require_database(
        bind.url.render_as_string(hide_password=False), fixture=fixture, profile=profile
    )


async def prepare(
    db: AsyncSession, owner: UUID, *, fixture: bool = False, profile: FixedCourse = STACK
) -> dict[str, Any]:
    from app.services.free_scene_availability import commit_outline

    check_bind(db, fixture=fixture, profile=profile)
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(
        profile.materials.GOAL,
        key=profile.materials.BATCH,
        config={
            "prompt_version": profile.materials.VERSION,
            "policy_version": profile.materials.BATCH,
        },
        operation_window_seconds=WINDOW_SECONDS,
    )
    cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
    if (await repo.get_course(cid))["head_version"] is None:
        fence = await repo.acquire_write_fence(cid, oid)
        plan = await repo.store_plan(
            cid,
            fence,
            expected_head=None,
            key=f"{profile.topic}-plan",
            candidate=profile.materials.outline(),
        )
        await commit_outline(
            db, owner, cid, fence, plan_id=UUID(plan["plan_id"]), key=f"{profile.topic}-outline"
        )
        op = await repo._operation(cid, oid)
        op.lease_token, op.lease_expires_at = None, None
    return await context(db, owner, cid, oid, fixture=fixture, profile=profile)


async def context(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    oid: UUID,
    *,
    fixture: bool = False,
    profile: FixedCourse = STACK,
) -> dict[str, Any]:
    from app.services.free_scene_generation import load_inputs

    check_bind(db, fixture=fixture, profile=profile)
    repo = SnapshotRepository(db, owner)
    op = await repo._operation(cid, oid)
    course = await repo.get_course(cid)
    if (
        course["original_goal"] != profile.materials.GOAL
        or course["head_version"] != 1
        or op.config_snapshot.get("prompt_version") != profile.materials.VERSION
        or op.config_snapshot.get("policy_version") != profile.materials.BATCH
        or op.kind != "create"
        or op.state not in {"queued", "running"}
        or op.cancel_requested_at is not None
        or op.deadline_at <= await repo._now()
        or (op.deadline_at - op.created_at).total_seconds() != WINDOW_SECONDS
    ):
        raise profile.error("OPERATION_STOPPED_OR_MISMATCH")
    version = await repo.get_version(cid, 1)
    pid, sid = version["plan_id"], version["scenes"][0]["scene_id"]
    inputs = await load_inputs(
        db, owner, cid, oid, plan_id=UUID(pid), scene_id=UUID(sid), expected_head=1
    )
    if inputs["plan"]["candidate"] != profile.materials.outline():
        raise profile.error("PLAN_BINDING")
    if profile is QUEUE_REVISION and not fixture:
        parent, _, _ = queue_course_revision.sealed_parent()
        original = parent["context"]
        if (
            str(owner) != original["owner"]
            or str(cid) == original["course_id"]
            or str(oid) == original["operation_id"]
        ):
            raise profile.error("REVISION_OPERATION_BINDING")
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
        binding=digest(f"{profile.topic}-course-context", inputs=inputs),
        evidence_kind="offline_fixture" if fixture else "actual_provider_response",
    )


def candidate(
    ctx: dict[str, Any],
    output: dict[str, Any],
    receipt: dict[str, Any],
    *,
    profile: FixedCourse = STACK,
) -> dict[str, Any]:
    mat = profile.materials.materials()
    profile.materials.validate_content(output, mat)
    data = dict(
        context=ctx,
        raw_output=output,
        receipt=receipt,
        plan_digest=digest(f"{profile.topic}-plan", plan=profile.materials.outline()),
        materials_digest=mat["materials_digest"],
    )
    if profile is QUEUE_REVISION:
        queue_course_revision.validate_immutable(output)
        data["parent_digest"] = queue_course_revision.PARENT
    return {**data, "candidate_digest": digest(f"{profile.topic}-course-candidate", data=data)}


def assembly(
    c: dict[str, Any], review: dict[str, Any], *, profile: FixedCourse = STACK
) -> dict[str, Any]:
    evaluator = review.get("independent_evaluator")
    if (
        review.get("candidate_digest") != c["candidate_digest"]
        or review.get("verdict") != "pass"
        or not isinstance(evaluator, str)
        or not evaluator.strip()
        or review.get("blocking_findings") != []
        or review.get("checks") != dict.fromkeys(profile.checks, True)
        or any(type(v) is not bool for v in review["checks"].values())
    ):
        raise profile.error("REVIEW_REQUIRED")
    evidence_kind = c["context"]["evidence_kind"]
    if profile is QUEUE_REVISION and evidence_kind == "actual_provider_response":
        evidence_kind = "evidence_bound_local_revision"
    source = dict(
        origin=profile.materials.ORIGIN,
        batch=profile.materials.BATCH,
        model=profile.materials.request()["model"],
        prompt_version=profile.materials.VERSION,
        parent_digest=c.get("parent_digest"),
        evidence_kind=evidence_kind,
        candidate_digest=c["candidate_digest"],
        materials_digest=c["materials_digest"],
        plan_digest=c["plan_digest"],
        teaching_review=dict(verdict="pass", independent_evaluator=evaluator),
    )
    return profile.materials.assemble(c["raw_output"], source)


def fingerprint(row: FreeSceneGenerationResult, *, profile: FixedCourse = STACK) -> str:
    return digest(
        f"{profile.topic}-generation-outcome",
        input_digest=row.input_digest,
        request_digest=row.request_digest,
        response=row.response_json,
        state=row.state,
        usage=row.usage_json,
        sent_attempts=row.sent_attempts,
    )


async def validate_publication(db, row, actual, operation) -> dict[str, Any]:
    profile = PROFILES[row.schema_version]
    snapshot = row.input_snapshot
    c = snapshot["candidate"]
    ctx = c["context"]
    expected = await context(
        db,
        row.user_id,
        row.course_id,
        row.operation_id,
        fixture=ctx["evidence_kind"] == "offline_fixture",
        profile=profile,
    )
    raw = assembly(c, snapshot["review"], profile=profile)
    if (
        operation.id != row.operation_id
        or row.origin_type != "model_generation"
        or row.state != "candidate"
        or row.reason_code is not None
        or row.sent_attempts != 1
        or row.expected_head != 1
        or row.prompt_version != profile.materials.VERSION
        or ctx != expected
        or row.input_snapshot["inputs"] != actual
        or c != candidate(expected, c["raw_output"], c["receipt"], profile=profile)
        or str(row.request_id) != ctx["request_id"]
        or str(row.scene_id) != ctx["scene_id"]
        or str(row.plan_id) != ctx["plan_id"]
        or row.input_digest != digest(f"{profile.topic}-generation-input", snapshot=snapshot)
        or row.request_digest
        != digest(f"{profile.topic}-http-request", body=profile.materials.request())
        or row.usage_json != c["receipt"]["usage"]
        or row.response_digest != fingerprint(row, profile=profile)
        or row.response_json != raw
    ):
        raise profile.error("PUBLICATION_BINDING")
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


async def publish(db, c, review, *, profile: FixedCourse = STACK) -> dict[str, Any]:
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
    expected = await context(
        db, owner, cid, oid, fixture=ctx["evidence_kind"] == "offline_fixture", profile=profile
    )
    if c != candidate(expected, c["raw_output"], c["receipt"], profile=profile):
        raise profile.error("PUBLICATION_BINDING")
    raw = assembly(c, review, profile=profile)
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
        call_key=profile.materials.BATCH,
        plan_id=pid,
        scene_id=sid,
        input_digest=digest(f"{profile.topic}-generation-input", snapshot=snapshot),
        request_digest=digest(f"{profile.topic}-http-request", body=profile.materials.request()),
        input_snapshot=snapshot,
        response_json=raw,
        usage_json=c["receipt"]["usage"],
        origin_type="model_generation",
        prompt_version=profile.materials.VERSION,
        schema_version=profile.materials.VERSION,
        sent_attempts=1,
        state="candidate",
        reason_code=None,
    )
    row.response_digest = fingerprint(row, profile=profile)
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
        key=f"{profile.topic}-ready:" + c["candidate_digest"],
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
