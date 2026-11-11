"""Bounded trial admission through the existing private course repository."""

from dataclasses import dataclass, replace
from datetime import datetime
from types import ModuleType
from typing import Any
from uuid import UUID

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.core.database import get_database_url
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services import (
    binary_search_course_frames,
    binary_search_course_materials,
    binary_search_course_revision,
    head_course_materials,
    queue_course_materials,
    queue_course_revision,
    stack_course_materials,
    stack_course_profile_pair,
)
from app.services import (
    course_trial_revision as revision,
)
from app.services.course_question_stem import PROMPT_VERSION as STEM_PROMPT_VERSION
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, digest

WINDOW_SECONDS = 1800
LIVE_BATCH = "four-topic-live-reuse-r01"
LIVE_WINDOW_SECONDS = 5400
LIVE_REQUESTS = {"plan": 1, "generate": 4, "revise": 4}


@dataclass(frozen=True)
class FixedCourse:
    topic: str
    materials: ModuleType
    database: str
    package: str
    approval_key: str
    checks: frozenset[str]
    new_batch: bool = False
    offline_only: bool = False
    live_reuse: bool = False
    learner_case: str | None = None
    learner_prompt_version: str = stack_course_profile_pair.VERSION

    @property
    def batch(self) -> str:
        if self.learner_case is not None:
            prefix = "stack-profile" if self.offline_only else "stack-profile-pair-live"
            return f"{prefix}-{self.learner_case}-r01"
        if self.offline_only:
            return f"{self.topic}-revision-fixture-r01"
        if self.live_reuse:
            return f"{LIVE_BATCH}-{self.topic}"
        return f"{self.topic}-stem-v2-r01" if self.new_batch else self.materials.BATCH

    @property
    def model_planned(self) -> bool:
        return self.topic == "head"

    @property
    def goal(self) -> str:
        return head_course_materials.EMPTY_GOAL if self.model_planned else self.materials.GOAL

    @property
    def prompt_version(self) -> str:
        if self.learner_case is not None:
            return self.learner_prompt_version
        return head_course_materials.FIXED_VERSION if self.model_planned else self.materials.VERSION

    @property
    def schema_version(self) -> str:
        return "head-empty-course-trial-v1" if self.model_planned else self.materials.VERSION

    def request(self, ctx=None):
        if self.learner_case is not None:
            evidence = stack_course_profile_pair.evidence(self.learner_case)
            if ctx is not None and (
                ctx.get("learner_case") != self.learner_case
                or ctx.get("learner_evidence") != evidence
                or ctx.get("profile_version") != 1
                or not ctx.get("profile_id")
            ):
                raise self.error("PROFILE_BINDING")
            return stack_course_profile_pair.request(
                self.learner_case, prompt_version=self.learner_prompt_version
            )
        if self.model_planned:
            return self.materials.body(ctx["head_payload"], stem_prompt_version=STEM_PROMPT_VERSION)
        if self.new_batch:
            return self.materials.request(stem_prompt_version=STEM_PROMPT_VERSION)
        return self.materials.request()

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
    | {
        "all_six_frames_and_highlights",
        "closed_interval_and_comparisons",
        "termination_and_duplicates",
    },
)
BINARY_SEARCH_REVISION = FixedCourse(
    BINARY_SEARCH.topic,
    binary_search_course_revision,
    BINARY_SEARCH.database,
    BINARY_SEARCH.package + "/revision",
    "accept_T122_revision_scope_and_batch_C2",
    BINARY_SEARCH.checks,
)
BINARY_SEARCH_FRAMES = FixedCourse(
    BINARY_SEARCH.topic,
    binary_search_course_frames,
    "edumind_catalog_p15_t127_reuse",
    "phase-1.5-binary-search-program-frames-t130",
    "accept_T130_scope_and_batch_C2",
    BINARY_SEARCH.checks | {"lesson_prose_matches_program_iterations"},
)
STACK_PROFILE_CASES = {
    case: replace(
        STACK,
        database="edumind_catalog_p15_t132_stack_profiles",
        package=f"phase-1.5-stack-profile-pair-t132/{case}",
        approval_key="accept_T132_fixture_scope",
        checks=STACK.checks | {"learner_evidence_respected", "teaching_depth_matches_profile"},
        offline_only=True,
        learner_case=case,
    )
    for case in stack_course_profile_pair.CASES
}
STACK_PROFILE_LIVE = {
    f"stack-profile-{case}": replace(
        profile,
        database="edumind_catalog_p15_t127_reuse",
        package="phase-1.5-stack-profile-pair-t132/live",
        approval_key="accept_T133_scope_and_batch_C2",
        offline_only=False,
    )
    for case, profile in STACK_PROFILE_CASES.items()
}
PROFILES = {
    profile.materials.VERSION: profile
    for profile in (
        STACK, QUEUE, QUEUE_REVISION, BINARY_SEARCH, BINARY_SEARCH_REVISION, BINARY_SEARCH_FRAMES
    )
}
NEW_BATCHES = {
    profile.topic: replace(
        profile,
        database="edumind_catalog_p15_t125_trials",
        package="phase-1.5-shared-first-draft-t125",
        approval_key="accept_T125_scope_and_batch_C2",
        new_batch=True,
    )
    for profile in (
        FixedCourse("head", head_course_materials, "", "", "", frozenset()),
        STACK,
        QUEUE,
        BINARY_SEARCH,
    )
}
REVISION_FIXTURES = {
    topic: replace(
        profile,
        package="phase-1.5-shared-revision-t126",
        database="edumind_catalog_p15_t126_trials",
        approval_key="accept_T126_fixture_scope",
        offline_only=True,
    )
    for topic, profile in NEW_BATCHES.items()
}
LIVE_REUSE = {
    topic: replace(
        profile,
        package="phase-1.5-shared-live-reuse-t127",
        database="edumind_catalog_p15_t127_reuse",
        approval_key="accept_T127_scope_and_batch_C2",
        live_reuse=True,
    )
    for topic, profile in NEW_BATCHES.items()
}
FOREGROUND_BATCHES = {
    profile.batch: profile
    for profile in (
        *NEW_BATCHES.values(), *REVISION_FIXTURES.values(), *LIVE_REUSE.values(),
        *STACK_PROFILE_LIVE.values(),
    )
}


def require_database(
    url: str | None = None, *, fixture: bool = False, profile: FixedCourse = STACK
) -> None:
    if profile.offline_only and not fixture:
        raise profile.error("OFFLINE_ONLY")
    if profile.live_reuse and fixture:
        raise profile.error("LIVE_FIXTURE_FORBIDDEN")
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
    db: AsyncSession, owner: UUID, *, fixture: bool = False, profile: FixedCourse = STACK,
    live_run: dict | None = None, profile_id: UUID | None = None,
) -> dict[str, Any]:
    from app.services.free_scene_availability import commit_outline

    check_bind(db, fixture=fixture, profile=profile)
    if profile.live_reuse != (live_run is not None):
        raise profile.error("LIVE_AUTHORIZATION_REQUIRED")
    if (profile.learner_case is None) != (profile_id is None):
        raise profile.error("PROFILE_BINDING")
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(
        profile.goal,
        key=profile.batch,
        profile_id=profile_id,
        config={
            "prompt_version": profile.prompt_version,
            "policy_version": profile.batch,
        },
        policy_snapshot={"course_trial_run": live_run} if live_run is not None else None,
        operation_window_seconds=WINDOW_SECONDS,
    )
    cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
    if profile.model_planned:
        return await context(db, owner, cid, oid, fixture=fixture, profile=profile, planning=True)
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
    planning: bool = False,
) -> dict[str, Any]:
    from app.services.free_scene_generation import load_inputs

    check_bind(db, fixture=fixture, profile=profile)
    repo = SnapshotRepository(db, owner)
    op = await repo._operation(cid, oid)
    course = await repo.get_course(cid)
    if (
        course["original_goal"] != profile.goal
        or course["head_version"] != (None if planning else 1)
        or op.config_snapshot.get("prompt_version") != profile.prompt_version
        or op.config_snapshot.get("policy_version") != profile.batch
        or op.kind != "create"
        or op.state not in {"queued", "running"}
        or op.cancel_requested_at is not None
        or op.deadline_at <= await repo._now()
        or (op.deadline_at - op.created_at).total_seconds() != WINDOW_SECONDS
    ):
        raise profile.error("OPERATION_STOPPED_OR_MISMATCH")
    common = dict(
        owner=str(owner),
        course_id=str(cid),
        operation_id=str(oid),
        request_id=str(op.request_id),
        starts_at=op.created_at.isoformat(),
        expires_at=op.deadline_at.isoformat(),
        evidence_kind="offline_fixture" if fixture else "actual_provider_response",
    )
    if profile.new_batch:
        common.update(
            topic=profile.topic,
            batch=profile.batch,
            stem_prompt_version=STEM_PROMPT_VERSION,
            plan_source="model_planned" if profile.model_planned else "fixed_outline",
        )
    if profile.live_reuse:
        run = op.policy_snapshot.get("course_trial_run")
        if (
            not isinstance(run, dict)
            or set(run) != {"run_sha256", "expires_at"}
            or datetime.fromisoformat(run["expires_at"]) <= await repo._now()
        ):
            raise profile.error("LIVE_WINDOW_OR_BINDING")
        common["live_run"] = run
    if planning:
        from app.services.free_course_planning import load_inputs as load_planning_inputs

        return dict(**common, planning_inputs=await load_planning_inputs(db, owner, cid, oid))
    if profile.model_planned:
        from app.services.head_course_generation import generation_context

        head = await generation_context(db, owner, cid, oid)
        return dict(
            **common, plan_id=head["plan_id"], scene_id=head["scene_id"],
            head_payload=head["payload"], planning_result_id=head["planning_result_id"],
        )
    version = await repo.get_version(cid, 1)
    pid, sid = version["plan_id"], version["scenes"][0]["scene_id"]
    inputs = await load_inputs(
        db, owner, cid, oid, plan_id=UUID(pid), scene_id=UUID(sid), expected_head=1
    )
    if inputs["plan"]["candidate"] != profile.materials.outline():
        raise profile.error("PLAN_BINDING")
    if profile.learner_case is not None:
        request = inputs["request"]
        common.update(
            learner_case=profile.learner_case,
            learner_evidence=request["learner_evidence"],
            profile_id=request["profile_id"],
            profile_version=request["profile_version"],
        )
        profile.request(common)
    if profile in (QUEUE_REVISION, BINARY_SEARCH_REVISION) and not fixture:
        if profile is QUEUE_REVISION:
            parent, _, _ = queue_course_revision.sealed_parent()
            original = parent["context"]
        else:
            _, original, _ = binary_search_course_revision.sealed_source()
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
        **common,
        plan_id=pid,
        scene_id=sid,
        binding=digest(f"{profile.topic}-course-context", inputs=inputs),
    )


def candidate(
    ctx: dict[str, Any],
    output: dict[str, Any],
    receipt: dict[str, Any],
    *,
    profile: FixedCourse = STACK,
) -> dict[str, Any]:
    if profile.model_planned:
        payload = ctx["head_payload"]
        profile.materials.validate_content(payload, output)
        mat, plan = payload["materials"], payload["plan"]
    else:
        mat, plan = profile.materials.materials(), profile.materials.outline()
        profile.materials.validate_content(output, mat)
    data = dict(
        context=ctx,
        raw_output=output,
        receipt=receipt,
        plan_digest=digest(f"{profile.topic}-plan", plan=plan),
        materials_digest=mat["materials_digest"],
    )
    if profile is QUEUE_REVISION:
        queue_course_revision.validate_immutable(output)
        data["parent_digest"] = queue_course_revision.PARENT
    elif profile is BINARY_SEARCH_REVISION:
        binary_search_course_revision.validate_immutable(output)
        data["source_response_sha256"] = binary_search_course_revision.SOURCE_RESPONSE
    elif profile is BINARY_SEARCH_FRAMES or profile.learner_case is not None:
        if receipt.get("request_sha256") != revision.checksum(profile.request(ctx)):
            raise profile.error("REQUEST_BINDING")
    return {**data, "candidate_digest": digest(f"{profile.topic}-course-candidate", data=data)}


def assembly(
    c: dict[str, Any], review: dict[str, Any], *, profile: FixedCourse = STACK
) -> dict[str, Any]:
    evaluator = review.get("independent_evaluator")
    checks = review.get("checks")
    paired = profile.learner_case is not None and not profile.offline_only
    required = dict.fromkeys(profile.checks, True)
    if paired and isinstance(checks, dict):
        # Record fit separately from factual correctness and individual course availability.
        required["teaching_depth_matches_profile"] = checks.get("teaching_depth_matches_profile")
    if (
        review.get("candidate_digest") != c["candidate_digest"]
        or review.get("verdict") != "pass"
        or not isinstance(evaluator, str)
        or not evaluator.strip()
        or review.get("blocking_findings") != []
        or not isinstance(checks, dict)
        or (not profile.model_planned and checks != required)
        or any(type(v) is not bool for v in checks.values())
        or (paired and review.get("evidence_kind") != c["context"]["evidence_kind"])
        or (
            (
                profile.live_reuse or profile is BINARY_SEARCH_FRAMES
                or profile.learner_case is not None or "revision" in c
            )
            and (review.get("parent_digest") != c.get("parent_digest")
                 or review.get("full_lesson_reviewed") is not True)
        )
    ):
        raise profile.error("REVIEW_REQUIRED")
    evidence_kind = c["context"]["evidence_kind"]
    if (
        profile in (QUEUE_REVISION, BINARY_SEARCH_REVISION)
        and evidence_kind == "actual_provider_response"
    ):
        evidence_kind = "evidence_bound_local_revision"
    source = dict(
        origin=profile.materials.ORIGIN,
        batch=profile.batch,
        model=profile.request(c["context"])["model"],
        prompt_version=profile.prompt_version,
        parent_digest=c.get("parent_digest"),
        evidence_kind=evidence_kind,
        candidate_digest=c["candidate_digest"],
        materials_digest=c["materials_digest"],
        plan_digest=c["plan_digest"],
        teaching_review=dict(verdict="pass", independent_evaluator=evaluator),
    )
    if profile is BINARY_SEARCH_REVISION:
        source["source_response_sha256"] = c["source_response_sha256"]
    if profile is BINARY_SEARCH_FRAMES or paired:
        source.update(
            source_request_sha256=c["receipt"]["request_sha256"],
            source_response_sha256=c["receipt"]["raw_sha256"],
            review_sha256=revision.checksum(review),
        )
    if paired:
        source.update(
            learner_case=profile.learner_case,
            learner_evidence_digest=digest(
                stack_course_profile_pair.VERSION, evidence=c["context"]["learner_evidence"]
            ),
            plan_source="fixed_outline",
        )
    if profile.new_batch:
        source.update(
            plan_source=c["context"]["plan_source"], stem_prompt_version=STEM_PROMPT_VERSION
        )
    if "revision" in c:
        source["revision_version"] = revision.VERSION
    if profile.model_planned:
        from app.services import head_course_reuse as reuse

        payload = c["context"]["head_payload"]
        # The outer review is bound to the new receipt-bearing candidate above.
        # Reuse the original head-specific teaching and evidence checks on its inner lesson.
        lesson = reuse.candidate(payload, c["raw_output"], parent=c.get("parent_digest"))
        reuse.require_full_review(dict(review, candidate_digest=lesson["candidate_digest"]), lesson)
        evidence = payload["teaching_evidence"]
        source.update(
            teaching_evidence_version=evidence["version"],
            teaching_evidence_digest=evidence["evidence_digest"],
        )
        return profile.materials.assemble(payload, c["raw_output"], source)
    return profile.materials.assemble(c["raw_output"], source)


def revised_candidate(ctx, replacements, receipt, source, *, profile):
    parent, review, approval = (source[key] for key in ("parent", "review", "approval"))
    if (
        parent != candidate(ctx, parent["raw_output"], parent["receipt"], profile=profile)
        or parent["receipt"]["request_sha256"] != revision.checksum(profile.request(ctx))
    ):
        raise profile.error("REVISION_PARENT_BINDING")
    request = revision.approved_request(profile, parent, review, approval)
    if receipt["request_sha256"] != revision.checksum(request):
        raise profile.error("REVISION_REQUEST_BINDING")
    merged = revision.merge(profile, parent, review, approval, replacements)
    data = candidate(ctx, merged, receipt, profile=profile)
    del data["candidate_digest"]
    data.update(parent_digest=parent["candidate_digest"], revision=dict(
        parent=parent, review=review, approval=approval, replacements=replacements,
    ))
    return {**data, "candidate_digest": digest(f"{profile.topic}-course-candidate", data=data)}


def verify_candidate(ctx, c, profile):
    if "revision" in c:
        if profile is BINARY_SEARCH_FRAMES or profile.learner_case is not None:
            raise profile.error("PUBLICATION_BINDING")
        source = c["revision"]
        expected = revised_candidate(
            ctx, source["replacements"], c["receipt"], source, profile=profile
        )
        request = revision.approved_request(
            profile, source["parent"], source["review"], source["approval"]
        )
    else:
        expected = candidate(ctx, c["raw_output"], c["receipt"], profile=profile)
        request = profile.request(ctx)
    if c != expected:
        raise profile.error("PUBLICATION_BINDING")
    return request


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
    profile = FOREGROUND_BATCHES.get(row.call_key)
    profile = profile or PROFILES[row.schema_version]
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
    request = verify_candidate(expected, c, profile)
    raw = assembly(c, snapshot["review"], profile=profile)
    if (
        operation.id != row.operation_id
        or row.origin_type != "model_generation"
        or row.state != "candidate"
        or row.reason_code is not None
        or row.sent_attempts != 1
        or row.expected_head != 1
        or row.schema_version != profile.schema_version
        or row.prompt_version != profile.prompt_version
        or ctx != expected
        or row.input_snapshot["inputs"] != actual
        or str(row.request_id) != ctx["request_id"]
        or str(row.scene_id) != ctx["scene_id"]
        or str(row.plan_id) != ctx["plan_id"]
        or row.input_digest != digest(f"{profile.topic}-generation-input", snapshot=snapshot)
        or row.request_digest
        != digest(f"{profile.topic}-http-request", body=request)
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

    if profile.learner_case is not None and profile.offline_only:
        raise profile.error("PROFILE_PREPARATION_ONLY")
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
    request = verify_candidate(expected, c, profile)
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
        call_key=profile.batch,
        plan_id=pid,
        scene_id=sid,
        input_digest=digest(f"{profile.topic}-generation-input", snapshot=snapshot),
        request_digest=digest(f"{profile.topic}-http-request", body=request),
        input_snapshot=snapshot,
        response_json=raw,
        usage_json=c["receipt"]["usage"],
        origin_type="model_generation",
        prompt_version=profile.prompt_version,
        schema_version=profile.schema_version,
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
