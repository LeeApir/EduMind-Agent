"""Owner-private cancellation, explicit new operations and read-only checkpoint recovery."""

from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.free_course import FreeCourseRequest
from app.models.free_course_progress import FreeCourseEvent, FreeCourseStep
from app.models.free_course_recovery import FreeCourseOperationSource
from app.models.free_course_scheduler import FreeCourseAttempt, FreeCourseSettlement
from app.models.free_course_writes import FreeCourseOperation
from app.services.free_course_scheduler import ACTIVE, POLICY, Lease, Scheduler
from app.services.free_course_snapshots import (
    SCHEMA,
    SnapshotError,
    SnapshotRepository,
    WriteFence,
    digest,
)
from app.services.free_scene_availability import read_availability

FINITE_HEAD_PROMPT_VERSIONS = frozenset(
    {"head-goal-course-v1", "head-reuse-course-v1", "head-fixed-course-v1"}
)


class Recovery:
    """Private service facade. HTTP owner/CSRF/mode controllers remain T020, not opened here."""

    tutor_allowed = False

    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions
        self.scheduler = Scheduler(sessions)

    async def cancel(self, owner: UUID, cid: UUID, oid: UUID, *, key: str) -> dict[str, Any]:
        route = f"/api/free-courses/{cid}/operations/{oid}/cancel"
        fingerprint = digest("cancel-operation", course_id=str(cid), operation_id=str(oid))
        async with self.sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            await repo._course(cid, lock=True)
            replay = await repo._receipt(route, key, fingerprint)
            if replay is not None:
                return replay
            op = await repo._operation(cid, oid)
            if op.kind == "tutor_turn" and not self.tutor_allowed:
                raise SnapshotError("OPERATION_KIND_INVALID")
            if op.state in ACTIVE and op.state != "cancel_requested":
                steps = await db.scalars(
                    select(FreeCourseStep)
                    .where(
                        FreeCourseStep.user_id == owner,
                        FreeCourseStep.course_id == cid,
                        FreeCourseStep.operation_id == oid,
                    )
                    .with_for_update()
                )
                for step in steps:
                    if step.state == "pending":
                        step.state, step.reason_code = "cancelled", "CANCELLED"
                op.state, op.cancel_requested_at = "cancel_requested", await repo._now()
                op.lease_epoch += 1
                op.lease_token = op.lease_expires_at = None
                await self.scheduler._event(
                    db,
                    Lease(owner, cid, WriteFence(oid, op.lease_epoch, uuid4())),
                    "cancel_requested",
                    {"state": "cancel_requested"},
                )
            await db.flush()
            result = await self._view(db, owner, cid, oid)
            return await repo._record(cid, route, key, fingerprint, result, status_code=200)

    async def _unresolved(self, db: AsyncSession, owner: UUID) -> bool:
        return (
            await db.scalar(
                select(FreeCourseAttempt.id)
                .outerjoin(
                    FreeCourseSettlement, FreeCourseSettlement.attempt_id == FreeCourseAttempt.id
                )
                .where(FreeCourseAttempt.user_id == owner, FreeCourseSettlement.id.is_(None))
            )
            is not None
        )

    async def start(
        self,
        owner: UUID,
        cid: UUID,
        *,
        kind: str,
        source_operation_id: UUID,
        expected_head: int | None,
        key: str,
        supplement: str | None = None,
    ) -> dict[str, Any]:
        if kind not in ("resume", "clarify"):
            raise SnapshotError("OPERATION_KIND_INVALID")
        if expected_head is not None and (type(expected_head) is not int or expected_head < 1):
            raise SnapshotError("STALE_COURSE_VERSION")
        if (kind == "resume" and supplement is not None) or (
            kind == "clarify"
            and (
                not isinstance(supplement, str) or not supplement.strip() or len(supplement) > 4000
            )
        ):
            raise SnapshotError("INVALID_OPERATION_INPUT")
        route = f"/api/free-courses/{cid}/operations"
        fingerprint = digest(
            "explicit-operation",
            kind=kind,
            source_operation_id=str(source_operation_id),
            expected_head=expected_head,
            supplement=supplement,
        )
        async with self.sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            course = await repo._course(cid, lock=True)
            replay = await repo._receipt(route, key, fingerprint)
            if replay is not None:
                return replay
            source = await repo._operation(cid, source_operation_id)
            if source.state in ACTIVE:
                raise SnapshotError("OPERATION_ACTIVE")
            if source.kind == "tutor_turn" or source.policy_snapshot != POLICY:
                raise SnapshotError("OPERATION_KIND_INVALID")
            if await db.scalar(
                select(FreeCourseOperation.id).where(
                    FreeCourseOperation.user_id == owner, FreeCourseOperation.state.in_(ACTIVE)
                )
            ):
                raise SnapshotError("OPERATION_ACTIVE")
            if await self._unresolved(db, owner):
                raise SnapshotError("OUTCOME_UNRESOLVED")
            await repo._expected(course, expected_head)
            latest = await db.scalar(
                select(FreeCourseOperation.id)
                .where(
                    FreeCourseOperation.user_id == owner,
                    FreeCourseOperation.course_id == cid,
                    FreeCourseOperation.kind != "tutor_turn",
                )
                .order_by(FreeCourseOperation.created_at.desc(), FreeCourseOperation.id.desc())
                .limit(1)
            )
            if latest != source.id:
                raise SnapshotError("STALE_SOURCE_OPERATION")
            if kind == "clarify" and source.state != "awaiting_clarification":
                raise SnapshotError("CLARIFICATION_NOT_REQUIRED")
            from app.services.free_course_revision import context as revision_context

            source_revision = await revision_context(db, source.id) if kind == "clarify" else None
            request = await db.get(FreeCourseRequest, source.request_id)
            if request is None:
                raise SnapshotError("SNAPSHOT_CORRUPT")
            await repo.get_request(cid, request.version)
            # resume binds the same immutable original request/plan. It never invents a new
            # source, relabels an old candidate or copies a ready scene into another plan.
            recoverable: list[dict[str, Any]] | None = None
            plan_id: UUID | None = None
            if kind == "resume" and expected_head is not None:
                manifest = await repo.get_version(cid, expected_head)
                plan_id = UUID(manifest["plan_id"])
                plan = await repo.get_plan(cid, plan_id)
                if plan["request_id"] != str(request.id):
                    raise SnapshotError("STALE_SOURCE_OPERATION")
                availability = await read_availability(db, owner, cid, version=expected_head)
                missing = {
                    s["scene_id"] for s in availability["scenes"] if s["content_state"] != "ready"
                }
                if any(
                    s["scene_version_id"] is not None and s["scene_id"] in missing
                    for s in manifest["scenes"]
                ):
                    raise SnapshotError("HEAD_NOT_RECOVERABLE")
                # A ready descendant cannot be silently regenerated by a missing predecessor.
                affected = set(missing)
                for scene in plan["scenes"]:
                    if set(scene["depends_on"]) & affected:
                        affected.add(scene["scene_id"])
                if affected != missing:
                    raise SnapshotError("HEAD_NOT_RECOVERABLE")
                recoverable = [s for s in plan["scenes"] if s["scene_id"] in missing]
                if not recoverable:
                    raise SnapshotError("NOTHING_TO_RESUME")
            if kind == "clarify":
                if expected_head is not None and (
                    source_revision is None
                    or source_revision.kind != "adjust_outline"
                    or source_revision.base_head != expected_head
                ):
                    raise SnapshotError("STALE_COURSE_VERSION")
                number = await db.scalar(
                    select(func.max(FreeCourseRequest.version)).where(
                        FreeCourseRequest.course_id == cid, FreeCourseRequest.user_id == owner
                    )
                )
                payload = dict(
                    request_text=supplement,
                    kind="adjustment",
                    profile_id=str(request.profile_id) if request.profile_id else None,
                    profile_version=request.profile_version,
                    evidence_snapshot=deepcopy(request.evidence_snapshot),
                    nonsecret_config_snapshot=deepcopy(request.nonsecret_config_snapshot),
                    parent_request_id=str(request.id),
                )
                request = FreeCourseRequest(
                    user_id=owner,
                    course_id=cid,
                    version=(number or 0) + 1,
                    schema_version=SCHEMA,
                    digest=digest("request", **payload),
                    **{
                        **payload,
                        "profile_id": request.profile_id,
                        "parent_request_id": request.id,
                    },
                )
                db.add(request)
                await db.flush()
            used = await self.scheduler.budget(db, cid, source.id)
            if (
                used["course_attempts"] >= 40
                or used["course_input"] >= 600000
                or used["course_output"] >= 144000
            ):
                raise SnapshotError("BUDGET_EXHAUSTED")
            op = FreeCourseOperation(
                user_id=owner,
                course_id=cid,
                request_id=request.id,
                kind=kind,
                state="queued",
                base_head_version=expected_head,
                config_snapshot=deepcopy(source.config_snapshot),
                policy_snapshot=deepcopy(POLICY),
            )
            db.add(op)
            await db.flush()
            db.add(
                FreeCourseOperationSource(
                    user_id=owner, course_id=cid, operation_id=op.id, source_operation_id=source.id
                )
            )
            if source_revision is not None:
                from app.models.free_course_revision import FreeCourseRevision

                db.add(
                    FreeCourseRevision(
                        user_id=owner,
                        course_id=cid,
                        operation_id=op.id,
                        kind=source_revision.kind,
                        base_head=source_revision.base_head,
                        instruction=supplement or "",
                        impact_json=deepcopy(source_revision.impact_json),
                        impact_digest=source_revision.impact_digest,
                    )
                )
            if recoverable is None:
                db.add(
                    FreeCourseStep(
                        user_id=owner,
                        course_id=cid,
                        operation_id=op.id,
                        step_key="plan",
                        state="pending",
                    )
                )
            else:
                for scene in recoverable:
                    db.add(
                        FreeCourseStep(
                            user_id=owner,
                            course_id=cid,
                            operation_id=op.id,
                            plan_id=plan_id,
                            scene_id=UUID(scene["scene_id"]),
                            step_key="scene:" + scene["scene_key"],
                            state="pending",
                        )
                    )
            await self.scheduler._event(
                db, Lease(owner, cid, WriteFence(op.id, 0, uuid4())), "queued", {}
            )
            return await repo._record(
                cid,
                route,
                key,
                fingerprint,
                dict(course_id=str(cid), operation_id=str(op.id)),
                status_code=202,
            )

    async def read_operation(self, owner: UUID, cid: UUID, oid: UUID) -> dict[str, Any]:
        """Read-only, repeatable snapshot. No lease, send, receipt, resume or settlement writes."""
        async with self.sessions() as db, db.begin():
            # SET TRANSACTION must be the first statement. No locks or mutation are acquired.
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            return await self._view(db, owner, cid, oid)

    async def _view(self, db: AsyncSession, owner: UUID, cid: UUID, oid: UUID) -> dict[str, Any]:
        repo = SnapshotRepository(db, owner)
        course = await repo.get_course(cid)
        op = await db.scalar(
            select(FreeCourseOperation).where(
                FreeCourseOperation.user_id == owner,
                FreeCourseOperation.course_id == cid,
                FreeCourseOperation.id == oid,
            )
        )
        if op is None or (op.kind == "tutor_turn" and not self.tutor_allowed):
            raise SnapshotError("NOT_FOUND")
        steps = (
            await db.scalars(
                select(FreeCourseStep)
                .where(
                    FreeCourseStep.user_id == owner,
                    FreeCourseStep.course_id == cid,
                    FreeCourseStep.operation_id == oid,
                )
                .order_by(FreeCourseStep.created_at, FreeCourseStep.step_key)
            )
        ).all()
        prompt_version = op.config_snapshot.get("prompt_version")
        execution_mode = None
        if prompt_version in FINITE_HEAD_PROMPT_VERSIONS:
            execution_mode = "finite_head_foreground"
        elif prompt_version == "stack-lifo-course-v1":
            execution_mode = "finite_stack_foreground"
        elif prompt_version in ("queue-fifo-course-v1", "queue-fifo-q01-revision-v1"):
            execution_mode = "finite_queue_foreground"
        elif prompt_version in (
            "binary-search-course-v1",
            "binary-search-revision-v1",
            "binary-search-program-frames-v1",
        ):
            execution_mode = "finite_binary_search_foreground"
        b = await self.scheduler.budget(db, cid, oid)
        unknown = await db.scalar(
            select(FreeCourseAttempt.id)
            .outerjoin(
                FreeCourseSettlement, FreeCourseSettlement.attempt_id == FreeCourseAttempt.id
            )
            .where(
                FreeCourseAttempt.operation_id == oid,
                (
                    FreeCourseSettlement.input_tokens.is_(None)
                    | FreeCourseSettlement.output_tokens.is_(None)
                ),
            )
        )
        last = (
            await db.scalar(
                select(func.max(FreeCourseEvent.seq)).where(FreeCourseEvent.operation_id == oid)
            )
            or 0
        )
        return dict(
            operation_id=str(oid),
            course_id=str(cid),
            kind=op.kind,
            state=op.state,
            base_head_version=op.base_head_version,
            head_version=course["head_version"],
            last_event_id=last,
            deadline_at=op.deadline_at.isoformat(),
            reason_code=op.reason_code,
            clarification_questions=deepcopy(op.clarification_questions),
            request_id=str(op.request_id),
            steps=[
                dict(
                    step_key=s.step_key,
                    scene_id=str(s.scene_id) if s.scene_id else None,
                    state=s.state,
                    reason_code=s.reason_code,
                )
                for s in steps
            ],
            **({"execution_mode": execution_mode} if execution_mode else {}),
            budget=None
            if execution_mode
            else dict(
                attempts_used=b["operation_attempts"],
                attempts_remaining=max(
                    0, (1 if op.kind == "tutor_turn" else 13) - b["operation_attempts"]
                ),
                course_attempts_remaining=max(0, 40 - b["course_attempts"]),
                input_tokens_charged=b["operation_input"],
                output_tokens_charged=b["operation_output"],
                usage_unknown=unknown is not None,
                input_tokens_remaining=max(
                    0, (16000 if op.kind == "tutor_turn" else 200000) - b["operation_input"]
                ),
                output_tokens_remaining=max(
                    0, (2000 if op.kind == "tutor_turn" else 48000) - b["operation_output"]
                ),
                course_input_tokens_remaining=max(0, 600000 - b["course_input"]),
                course_output_tokens_remaining=max(0, 144000 - b["course_output"]),
            ),
        )
