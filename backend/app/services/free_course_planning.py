"""Load actual request evidence and persist one detached planning outcome atomically."""

from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.free_course_planning import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    PlanningOutcome,
    build_request,
    request_digest,
    snapshot_input,
    validate_response,
)
from app.models.free_course import FreeCourseRequest
from app.models.free_course_planning import FreeCoursePlanningResult
from app.models.free_course_writes import FreeCourseOperation
from app.services.free_course_snapshots import (
    SnapshotError,
    SnapshotRepository,
    WriteFence,
    canonical,
    digest,
)


async def load_inputs(
    db: AsyncSession, owner_id: UUID, course_id: UUID, operation_id: UUID
) -> dict[str, Any]:
    repo = SnapshotRepository(db, owner_id)
    course = await repo.get_course(course_id)
    operation = await db.scalar(
        select(FreeCourseOperation).where(
            FreeCourseOperation.user_id == owner_id,
            FreeCourseOperation.course_id == course_id,
            FreeCourseOperation.id == operation_id,
        )
    )
    if operation is None:
        raise SnapshotError("NOT_FOUND")
    row = await db.scalar(
        select(FreeCourseRequest).where(
            FreeCourseRequest.user_id == owner_id,
            FreeCourseRequest.course_id == course_id,
            FreeCourseRequest.id == operation.request_id,
        )
    )
    if row is None:
        raise SnapshotError("NOT_FOUND")
    current = await repo.get_request(course_id, row.version)
    sources = {}
    visited = set()
    while row is not None:
        if row.id in visited:
            raise SnapshotError("SNAPSHOT_CORRUPT")
        visited.add(row.id)
        request = await repo.get_request(course_id, row.version)
        sources[f"request_{row.version}"] = {
            "request_id": str(row.id),
            "version": row.version,
            "text": request["request_text"],
        }
        if row.parent_request_id is None:
            break
        row = await db.scalar(
            select(FreeCourseRequest).where(
                FreeCourseRequest.user_id == owner_id,
                FreeCourseRequest.course_id == course_id,
                FreeCourseRequest.id == row.parent_request_id,
            )
        )
        if row is None:
            raise SnapshotError("SNAPSHOT_CORRUPT")
    capability = {}
    if current["nonsecret_config_snapshot"].get("prompt_version") in (
        "head-goal-course-v1",
        "head-reuse-course-v1",
    ):
        from app.services.head_course_materials import support_for_goal

        capability = dict(head_support=support_for_goal(course["original_goal"]))
    return snapshot_input(
        dict(
            course_id=str(course_id),
            operation_id=str(operation_id),
            request_id=str(operation.request_id),
            original_goal=course["original_goal"],
            teaching_language=course["teaching_language"],
            code_language=course["code_language"],
            request_sources=sources,
            learner_evidence=current["evidence_snapshot"],
            profile_id=current["profile_id"],
            profile_version=current["profile_version"],
            **capability,
        )
    )


async def persist_outcome(
    db: AsyncSession,
    owner_id: UUID,
    course_id: UUID,
    fence: WriteFence,
    *,
    expected_head: int | None,
    call_key: str,
    inputs: dict[str, Any],
    outcome: PlanningOutcome,
) -> dict[str, Any]:
    """Never calls the Gateway. Network generation and outer budget reservation are separate."""
    repo = SnapshotRepository(db, owner_id)
    snapshot = snapshot_input(inputs)
    identity = digest("planning-input", snapshot=snapshot)
    if "head_support" in snapshot:
        from app.agents import head_course_planning_wire

        request = head_course_planning_wire.build_request(snapshot)
        prompt_version = head_course_planning_wire.PROMPT_VERSION
    else:
        request = build_request(snapshot)
        prompt_version = PROMPT_VERSION
    call_digest = request_digest(request)
    if outcome.input_digest != identity or outcome.request_digest != call_digest:
        raise SnapshotError("PLANNING_INPUT_MISMATCH")
    if outcome.state not in {"ready", "needs_clarification", "failed"}:
        raise SnapshotError("PLANNING_RESULT_INVALID")
    if outcome.state == "failed":
        if outcome.reason_code not in {"SCHEMA_INVALID", "PROVIDER_REJECTED", "OUTCOME_UNKNOWN"}:
            raise SnapshotError("PLANNING_RESULT_INVALID")
    else:
        value = validate_response(outcome.response, snapshot)
        if outcome.reason_code is not None or (
            value["needs_clarification"] != (outcome.state == "needs_clarification")
        ):
            raise SnapshotError("PLANNING_RESULT_INVALID")
    if outcome.body_digest != digest("planning-response", response=outcome.response):
        raise SnapshotError("PLANNING_RESULT_CHANGED")
    response = deepcopy(outcome.response)
    if response is not None and len(canonical(response)) > 16384:
        raise SnapshotError("PLANNING_RESULT_INVALID")
    fingerprint = digest(
        "planning-outcome",
        input_digest=identity,
        request_digest=call_digest,
        state=outcome.state,
        reason_code=outcome.reason_code,
        response=response,
        expected_head=expected_head,
    )
    if not 1 <= len(call_key) <= 128 or not all(32 <= ord(c) <= 126 for c in call_key):
        raise SnapshotError("INVALID_IDEMPOTENCY_KEY")
    async with db.begin_nested():
        await repo._owner_lock()
        course = await repo._course(course_id, lock=True)
        actual = await load_inputs(db, owner_id, course_id, fence.operation_id)
        if digest("planning-input", snapshot=actual) != identity:
            raise SnapshotError("PLANNING_INPUT_MISMATCH")
        existing = await db.scalar(
            select(FreeCoursePlanningResult).where(
                FreeCoursePlanningResult.user_id == owner_id,
                FreeCoursePlanningResult.course_id == course_id,
                FreeCoursePlanningResult.operation_id == fence.operation_id,
                FreeCoursePlanningResult.call_key == call_key,
            )
        )
        if existing is not None:
            if existing.response_digest != fingerprint:
                raise SnapshotError("IDEMPOTENCY_CONFLICT")
            return {
                "result_id": str(existing.id),
                "plan_id": str(existing.plan_id) if existing.plan_id else None,
                "state": existing.state,
            }
        await repo._expected(course, expected_head)
        operation = await repo._fence(course_id, fence)
        plan_id = None
        if outcome.state == "ready":
            assert response is not None
            result = await repo.store_plan(
                course_id,
                fence,
                expected_head=expected_head,
                key="planning:"
                + digest(
                    "planning-storage-key", operation_id=str(fence.operation_id), call_key=call_key
                ),
                candidate=response["plan"],
            )
            plan_id = UUID(result["plan_id"])
        row = FreeCoursePlanningResult(
            user_id=owner_id,
            course_id=course_id,
            operation_id=operation.id,
            request_id=operation.request_id,
            lease_epoch=fence.epoch,
            call_key=call_key,
            expected_head=expected_head,
            input_digest=identity,
            request_digest=call_digest,
            response_digest=fingerprint,
            prompt_version=prompt_version,
            schema_version=SCHEMA_VERSION,
            state=outcome.state,
            reason_code=outcome.reason_code,
            input_snapshot=snapshot,
            response_json=response,
            plan_id=plan_id,
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
            .values(
                state="awaiting_clarification"
                if outcome.state == "needs_clarification"
                else "failed"
                if outcome.state == "failed"
                else "running",
                reason_code=outcome.reason_code,
                clarification_questions=response["questions"]
                if outcome.state == "needs_clarification" and response is not None
                else [],
            )
            .returning(FreeCourseOperation.id)
            .execution_options(synchronize_session="fetch")
        )
        if changed is None:
            raise SnapshotError("OPERATION_FENCED")
        # Caller commits; no network or worker work occurs in this transaction.
        return {
            "result_id": str(row.id),
            "plan_id": str(plan_id) if plan_id else None,
            "state": outcome.state,
        }
