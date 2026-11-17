"""Single-send tutor specialization of the existing durable PG budget/dispatch scheduler."""

from dataclasses import asdict, replace
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.classroom_context import ClassroomTurnContext
from app.agents.classroom_turn_schema import TurnSchemaError, validate_classroom_turn
from app.agents.tutor_agent import TutorAgent
from app.models.free_course_progress import FreeCourseEvent, FreeCourseStep
from app.models.free_course_scheduler import FreeCourseAttempt, FreeCourseSettlement
from app.models.free_course_tutor import FreeCourseTutorTurn
from app.services.free_course_contract import validate
from app.services.free_course_recovery import Recovery
from app.services.free_course_scheduler import Adapter, Lease, Scheduler, request_json
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from app.services.free_course_tutor import POLICY, check_sources, identity, store_reply
from app.services.free_scene_availability import _live


class TutorScheduler(Scheduler):
    operation_policy = POLICY
    operation_kinds = ("tutor_turn",)

    async def _event(
        self, db: AsyncSession, lease: Lease, kind: str, payload: dict[str, Any]
    ) -> None:
        turn = await db.scalar(
            select(FreeCourseTutorTurn).where(
                FreeCourseTutorTurn.user_id == lease.owner,
                FreeCourseTutorTurn.course_id == lease.course,
                FreeCourseTutorTurn.operation_id == lease.fence.operation_id,
            )
        )
        if turn is None:
            raise SnapshotError("NOT_FOUND")
        seq = (
            await db.scalar(
                select(func.max(FreeCourseEvent.seq)).where(
                    FreeCourseEvent.operation_id == lease.fence.operation_id
                )
            )
            or 0
        ) + 1
        event = dict(
            schema_version="free-course-events-v1",
            operation_id=str(lease.fence.operation_id),
            seq=seq,
            type=kind,
            course_version=turn.binding_json["course_version"],
            payload=payload,
        )
        validate("TutorEvent", event)
        if seq > 256 or len(canonical(event)) > 4096:
            raise SnapshotError("EVENT_LIMIT_EXCEEDED")
        db.add(
            FreeCourseEvent(
                user_id=lease.owner,
                course_id=lease.course,
                operation_id=lease.fence.operation_id,
                seq=seq,
                event_type=kind,
                course_version_id=turn.course_version_id,
                payload=payload,
            )
        )
        await db.flush()

    async def prepare(self, lease: Lease, adapter: Adapter) -> UUID | None:
        policy = adapter.policy
        if (
            not policy.package_id
            or policy.requests <= 0
            or not policy.bounded_output_verified
            or min(policy.input_micros_per_token, policy.output_micros_per_token, policy.fee_micros)
            < 0
        ):
            raise SnapshotError("EXECUTION_NOT_AUTHORIZED")
        async with self.sessions() as db, db.begin():
            repo, course, op = await self._locked(db, lease)
            if op.kind != "tutor_turn" or op.policy_snapshot != POLICY:
                raise SnapshotError("POLICY_MISMATCH")
            slot = await self._slot(db, lease)
            step = await db.scalar(
                select(FreeCourseStep).where(
                    FreeCourseStep.operation_id == op.id, FreeCourseStep.step_key == "tutor"
                )
            )
            turn = await db.scalar(
                select(FreeCourseTutorTurn).where(
                    FreeCourseTutorTurn.operation_id == op.id,
                    FreeCourseTutorTurn.user_id == lease.owner,
                )
            )
            if step is None or turn is None or turn.context_digest != identity(turn):
                raise SnapshotError("TUTOR_BINDING_MISMATCH")
            previous = await db.scalar(
                select(FreeCourseAttempt).where(FreeCourseAttempt.operation_id == op.id)
            )
            if previous is not None:
                return previous.id
            if slot.pending_attempt_id or step.state != "pending":
                raise SnapshotError("ATTEMPT_ALREADY_SENT")
            try:
                await repo._expected(course, turn.binding_json["course_version"])
                if not await check_sources(db, lease.owner, lease.course, turn.sources_json):
                    raise SnapshotError("CONTEXT_UNAVAILABLE")
            except SnapshotError:
                await self._terminal(db, lease, op, "failed", "CONTEXT_UNAVAILABLE")
                return None
            context = ClassroomTurnContext(
                canonical(dict(**turn.context_json, message=turn.message)).decode()
            )
            request = TutorAgent.build_request(
                mode="focus", enabled_roles=[], context=context, public_draft=True
            )
            inp = adapter.input_upper_bound(request)
            out = min(2000, policy.output_limit)
            if type(inp) is not int or not 1 <= inp <= min(16000, policy.input_limit) or out < 1:
                await self._terminal(db, lease, op, "failed", "BUDGET_EXHAUSTED")
                return None
            request = replace(request, prompt=replace(request.prompt, max_output_tokens=out))
            budget = await self.budget(db, lease.course, op.id)
            exceeded = any(
                budget[k] + delta > cap
                for k, delta, cap in [
                    ("operation_attempts", 1, 1),
                    ("course_attempts", 1, 40),
                    ("operation_input", inp, 16000),
                    ("operation_output", out, 2000),
                    ("course_input", inp, 600000),
                    ("course_output", out, 144000),
                ]
            )
            await db.execute(
                select(func.pg_advisory_xact_lock(7414, func.hashtext(policy.package_id)))
            )
            package_rows = (
                await db.scalars(
                    select(FreeCourseAttempt).where(
                        FreeCourseAttempt.request_json["package_id"].astext == policy.package_id
                    )
                )
            ).all()
            fee = inp * policy.input_micros_per_token + out * policy.output_micros_per_token
            if (
                exceeded
                or len(package_rows) >= policy.requests
                or sum(a.fee_micros for a in package_rows) + fee > policy.fee_micros
            ):
                await self._terminal(db, lease, op, "failed", "BUDGET_EXHAUSTED")
                return None
            packed = request_json(request)
            attempt = FreeCourseAttempt(
                user_id=lease.owner,
                course_id=lease.course,
                operation_id=op.id,
                step_id=step.id,
                purpose="primary",
                lease_epoch=lease.fence.epoch,
                input_tokens=inp,
                output_tokens=out,
                fee_micros=fee,
                sent_at=await repo._now(),
                input_snapshot=dict(turn_id=str(turn.id), context_digest=turn.context_digest),
                request_digest=digest("outbound-request", request=packed),
                request_json=dict(
                    request=packed, package_id=policy.package_id, send_policy=asdict(policy)
                ),
            )
            db.add(attempt)
            await db.flush()
            step.state = "running"
            slot.pending_attempt_id = attempt.id
            await _live(db, lease.owner, lease.course, lease.fence)
            return attempt.id

    async def before_dispatch(
        self, db: AsyncSession, lease: Lease, attempt: FreeCourseAttempt
    ) -> bool:
        repo, course, op = await self._locked(db, lease)
        turn = await db.scalar(
            select(FreeCourseTutorTurn).where(FreeCourseTutorTurn.operation_id == op.id)
        )
        if turn is None or turn.context_digest != identity(turn):
            raise SnapshotError("TUTOR_BINDING_MISMATCH")
        try:
            await repo._expected(course, turn.binding_json["course_version"])
            if not await check_sources(db, lease.owner, lease.course, turn.sources_json):
                raise SnapshotError("CONTEXT_UNAVAILABLE")
        except SnapshotError:
            # Reservation was committed but this transaction proves no dispatch happened.
            # Record trusted local nonexecution, rather than leaving phantom usage/quarantine.
            from app.models.free_course_scheduler import FreeCourseSettlement

            db.add(
                FreeCourseSettlement(
                    user_id=lease.owner,
                    course_id=lease.course,
                    attempt_id=attempt.id,
                    evidence="not_executed",
                    evidence_digest=digest(
                        "tutor-local-not-dispatched", attempt_id=str(attempt.id)
                    ),
                    input_tokens=0,
                    output_tokens=0,
                    outcome_json=dict(value=None, status=None, retry_after=None, hard_failure=True),
                )
            )
            await db.flush()
            await self._terminal(db, lease, op, "failed", "CONTEXT_UNAVAILABLE")
            return False
        return True

    async def consume(self, lease: Lease, attempt_id: UUID) -> None:
        async with self.sessions() as db, db.begin():
            repo, _, op = await self._locked(db, lease)
            slot = await self._slot(db, lease)
            a = await db.get(FreeCourseAttempt, attempt_id)
            if a is None or a.operation_id != op.id:
                raise SnapshotError("NOT_FOUND")
            step = await db.get(FreeCourseStep, a.step_id)
            if step is None or step.state not in ("pending", "running"):
                return
            settled = await db.scalar(
                select(FreeCourseSettlement).where(FreeCourseSettlement.attempt_id == a.id)
            )
            if settled is None:
                return
            slot.pending_attempt_id = None
            if a.lease_epoch != lease.fence.epoch:
                await self._terminal(db, lease, op, "failed", "LEASE_LOST")
                return
            turn = await db.scalar(
                select(FreeCourseTutorTurn).where(FreeCourseTutorTurn.operation_id == op.id)
            )
            if turn is None or a.input_snapshot != {
                "turn_id": str(turn.id),
                "context_digest": turn.context_digest,
            }:
                raise SnapshotError("TUTOR_BINDING_MISMATCH")
            outcome = settled.outcome_json
            if (
                settled.evidence != "complete_response"
                or outcome["hard_failure"]
                or (outcome["status"] is not None and outcome["status"] >= 400)
            ):
                await self._terminal(db, lease, op, "failed", "PROVIDER_REJECTED")
                return
            try:
                validated = validate_classroom_turn(outcome["value"], eligible_roles=["tutor"])
                utterances = validated["utterances"]
                assert isinstance(utterances, list)
                # Existing single-Tutor output has no qualified citation field: do not invent refs.
                markdown = utterances[0]["text"]
                async with db.begin_nested():
                    await store_reply(
                        db, lease.owner, lease.course, lease.fence, turn.id, markdown, []
                    )
            except (TurnSchemaError, SnapshotError) as error:
                reason = error.code if isinstance(error, SnapshotError) else "SCHEMA_INVALID"
                await self._terminal(db, lease, op, "failed", reason)
                return
            step.state = "ready"
            await self._event(db, lease, "tutor_ready", dict(turn_id=str(turn.id)))
            await self._terminal(db, lease, op, "succeeded", None)


class TutorRecovery(Recovery):
    tutor_allowed = True

    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        super().__init__(sessions)
        self.scheduler = TutorScheduler(sessions)
