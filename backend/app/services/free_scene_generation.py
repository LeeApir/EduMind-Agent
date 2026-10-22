"""Load exact scene/dependency inputs and retain private outcomes without publishing."""

from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.free_course_planning import request_digest
from app.agents.free_course_planning import validate_response as validate_plan
from app.agents.free_scene_generation import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    SceneOutcome,
    build_request,
    snapshot_input,
    validate_response,
)
from app.models.free_course import FreeCourseSceneVersion
from app.models.free_course_writes import FreeCourseOperation
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services.free_course_planning import load_inputs as load_request_inputs
from app.services.free_course_snapshots import (
    SnapshotError,
    SnapshotRepository,
    WriteFence,
    canonical,
    digest,
)


async def load_inputs(
    db: AsyncSession,
    owner_id: UUID,
    course_id: UUID,
    operation_id: UUID,
    *,
    plan_id: UUID,
    scene_id: UUID,
    expected_head: int | None,
) -> dict[str, Any]:
    repo = SnapshotRepository(db, owner_id)
    request = await load_request_inputs(db, owner_id, course_id, operation_id)
    epoch = await db.scalar(
        select(FreeCourseOperation.lease_epoch).where(
            FreeCourseOperation.user_id == owner_id,
            FreeCourseOperation.course_id == course_id,
            FreeCourseOperation.id == operation_id,
        )
    )
    plan = await repo.get_plan(course_id, plan_id)
    if plan["request_id"] != request["request_id"]:
        raise SnapshotError("SCENE_INPUT_INVALID")
    validate_plan(
        dict(
            needs_clarification=False,
            plan=plan["candidate"],
            questions=[],
            reason=None,
            source_keys=[],
        ),
        request,
    )
    course = await repo.get_course(course_id)
    if course["head_version"] != expected_head:
        raise SnapshotError("STALE_COURSE_VERSION")
    scene = next((s for s in plan["scenes"] if s["scene_id"] == str(scene_id)), None)
    if scene is None:
        raise SnapshotError("NOT_FOUND")
    by_id = {s["scene_id"]: s for s in plan["scenes"]}
    necessary: set[str] = set()

    def visit(sid: str) -> None:
        for dependency in by_id[sid]["depends_on"]:
            if dependency not in necessary:
                necessary.add(dependency)
                visit(dependency)

    visit(str(scene_id))
    manifest = (
        await repo.get_version(course_id, expected_head) if expected_head is not None else None
    )
    from app.services.free_course_revision import context, plan_binding, stages

    revision = await context(db, operation_id)
    if revision is not None:
        if revision.base_head != expected_head or await plan_binding(db, operation_id) != plan_id:
            raise SnapshotError("SCENE_INPUT_INVALID")
    elif manifest is not None and manifest["plan_id"] != str(plan_id):
        raise SnapshotError("SCENE_INPUT_INVALID")
    upstream = []
    for predecessor in plan["scenes"]:
        sid = predecessor["scene_id"]
        if sid not in necessary:
            continue
        if manifest is None and revision is None:
            raise SnapshotError("DEPENDENCY_UNAVAILABLE")
        try:
            if revision is not None:
                saved = await stages(db, operation_id)
                if sid not in saved:
                    raise SnapshotError("DEPENDENCY_UNAVAILABLE")
                row = await db.get(FreeCourseSceneVersion, saved[sid].scene_version_id)
                if row is None or row.plan_id != plan_id:
                    raise SnapshotError("SCENE_INPUT_INVALID")
                snapshot = dict(
                    scene_version_id=str(row.id),
                    digest=row.content_digest,
                    content=deepcopy(row.content_json),
                    actions=deepcopy(row.actions_json),
                    dependencies=deepcopy(row.dependency_bindings),
                )
            else:
                snapshot = await repo.get_scene_snapshot(course_id, expected_head, UUID(sid))
        except SnapshotError as error:
            if error.code == "SCENE_NOT_READY":
                raise SnapshotError("DEPENDENCY_UNAVAILABLE") from None
            raise
        from app.services.free_course_quality import assert_visible

        await assert_visible(db, owner_id, course_id, UUID(str(snapshot["scene_version_id"])))
        upstream.append(dict(scene_id=sid, **snapshot))
    return snapshot_input(
        dict(
            request=request,
            plan=plan,
            scene_id=str(scene_id),
            expected_head=expected_head,
            upstream=upstream,
            lease_epoch=epoch,
        )
    )


async def persist_outcome(
    db: AsyncSession,
    owner_id: UUID,
    course_id: UUID,
    fence: WriteFence,
    *,
    call_key: str,
    inputs: dict[str, Any],
    outcome: SceneOutcome,
) -> dict[str, Any]:
    """No ready scene, head switch, grading, event or operation success is emitted here."""
    snapshot = snapshot_input(inputs)
    identity = digest("scene-generation-input", snapshot=snapshot)
    if outcome.input_digest != identity or outcome.request_digest != request_digest(
        build_request(snapshot)
    ):
        raise SnapshotError("SCENE_INPUT_MISMATCH")
    if outcome.sent_attempts != 1 or outcome.state not in {"candidate", "failed"}:
        raise SnapshotError("SCENE_RESULT_INVALID")
    if outcome.state == "candidate":
        validate_response(outcome.response, snapshot)
        if outcome.reason_code is not None:
            raise SnapshotError("SCENE_RESULT_INVALID")
    elif outcome.reason_code not in {"SCHEMA_INVALID", "PROVIDER_REJECTED", "OUTCOME_UNKNOWN"}:
        raise SnapshotError("SCENE_RESULT_INVALID")
    if outcome.body_digest != digest(
        "scene-call-body", response=outcome.response, usage=outcome.usage
    ):
        raise SnapshotError("SCENE_RESULT_CHANGED")
    if outcome.response is not None and len(canonical(outcome.response)) > 65536:
        raise SnapshotError("SCENE_RESULT_INVALID")
    if not 1 <= len(call_key) <= 128 or not all(32 <= ord(c) <= 126 for c in call_key):
        raise SnapshotError("INVALID_IDEMPOTENCY_KEY")
    fingerprint = digest(
        "scene-generation-outcome",
        input_digest=identity,
        request_digest=outcome.request_digest,
        state=outcome.state,
        reason_code=outcome.reason_code,
        response=outcome.response,
        usage=outcome.usage,
        sent_attempts=outcome.sent_attempts,
    )
    repo = SnapshotRepository(db, owner_id)
    async with db.begin_nested():
        await repo._owner_lock()
        course = await repo._course(course_id, lock=True)
        existing = await db.scalar(
            select(FreeSceneGenerationResult).where(
                FreeSceneGenerationResult.user_id == owner_id,
                FreeSceneGenerationResult.course_id == course_id,
                FreeSceneGenerationResult.operation_id == fence.operation_id,
                FreeSceneGenerationResult.scene_id == UUID(snapshot["scene_id"]),
                FreeSceneGenerationResult.call_key == call_key,
            )
        )
        if existing is not None:
            if existing.response_digest != fingerprint:
                raise SnapshotError("IDEMPOTENCY_CONFLICT")
            return dict(result_id=str(existing.id), state=existing.state)
        await repo._expected(course, snapshot["expected_head"])
        operation = await repo._fence(course_id, fence)
        actual = await load_inputs(
            db,
            owner_id,
            course_id,
            fence.operation_id,
            plan_id=UUID(snapshot["plan"]["id"]),
            scene_id=UUID(snapshot["scene_id"]),
            expected_head=snapshot["expected_head"],
        )
        if digest("scene-generation-input", snapshot=actual) != identity:
            raise SnapshotError("SCENE_INPUT_MISMATCH")
        row = FreeSceneGenerationResult(
            user_id=owner_id,
            course_id=course_id,
            operation_id=operation.id,
            request_id=operation.request_id,
            lease_epoch=fence.epoch,
            call_key=call_key,
            expected_head=snapshot["expected_head"],
            plan_id=UUID(snapshot["plan"]["id"]),
            scene_id=UUID(snapshot["scene_id"]),
            input_digest=identity,
            request_digest=outcome.request_digest,
            response_digest=fingerprint,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            state=outcome.state,
            reason_code=outcome.reason_code,
            input_snapshot=snapshot,
            response_json=deepcopy(outcome.response),
            usage_json=deepcopy(outcome.usage),
            sent_attempts=outcome.sent_attempts,
        )
        db.add(row)
        await db.flush()
        changed = await db.scalar(
            update(FreeCourseOperation)
            .where(
                FreeCourseOperation.id == operation.id,
                FreeCourseOperation.user_id == owner_id,
                FreeCourseOperation.course_id == course_id,
                FreeCourseOperation.state == "running",
                FreeCourseOperation.lease_epoch == fence.epoch,
                FreeCourseOperation.lease_token == fence.token,
                FreeCourseOperation.cancel_requested_at.is_(None),
                FreeCourseOperation.lease_expires_at > func.clock_timestamp(),
                FreeCourseOperation.deadline_at > func.clock_timestamp(),
            )
            .values(state="running")
            .returning(FreeCourseOperation.id)
            .execution_options(synchronize_session="fetch")
        )
        if changed is None:
            raise SnapshotError("OPERATION_FENCED")
        return dict(result_id=str(row.id), state=outcome.state)
