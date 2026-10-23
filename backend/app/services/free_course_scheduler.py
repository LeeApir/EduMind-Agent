"""PG polling queue and bounded outbound attempts. No production Provider is registered here."""

import asyncio
import json
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents import free_course_planning as planner
from app.agents import free_scene_generation as generator
from app.models.auth import User
from app.models.free_course import FreeCourse
from app.models.free_course_progress import FreeCourseEvent, FreeCourseStep
from app.models.free_course_scheduler import (
    FreeCourseAttempt,
    FreeCourseCapacity,
    FreeCourseDispatch,
    FreeCourseSettlement,
)
from app.models.free_course_writes import FreeCourseOperation
from app.services import free_course_planning as plans
from app.services import free_scene_availability as visibility
from app.services import free_scene_generation as scenes
from app.services.free_course_snapshots import (
    SnapshotError,
    SnapshotRepository,
    WriteFence,
    canonical,
    digest,
)
from app.services.free_scene_validation import check_scene, validate_candidate
from app.services.provider_gateway import ChatMessage, StructuredRequest, TaskProfile, TextRequest

POLICY = json.loads(Path(__file__).with_suffix(".policy.json").read_text())
ACTIVE = ("queued", "running", "cancel_requested")


@dataclass(frozen=True)
class Lease:
    owner: UUID
    course: UUID
    fence: WriteFence


@dataclass(frozen=True)
class Reply:
    """Trusted transport evidence, never fields read from model JSON or HTTP status alone.

    An adapter must independently verify execution evidence and a content-free evidence digest.
    Generic Gateway exceptions/timeouts cannot manufacture stopped/not-executed evidence.
    """

    evidence: str = "unknown"
    evidence_digest: str | None = None
    value: dict[str, Any] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    status: int | None = None
    retry_after: str | None = None
    hard_failure: bool = False


@dataclass(frozen=True)
class SendPolicy:
    """Server-only execution-package boundary; zero by default, never an API payload.

    Production admission must supply a verified tokenizer/upper bound, total output including
    reasoning, fixed rates and a durable approved execution package. No such adapter is enabled.
    """

    package_id: str = ""
    requests: int = 0
    fee_micros: int = 0
    input_micros_per_token: int = 0
    output_micros_per_token: int = 0
    input_limit: int = 32000
    output_limit: int = 8000
    bounded_output_verified: bool = False


class Adapter(Protocol):
    policy: SendPolicy

    def input_upper_bound(self, request: StructuredRequest) -> int: ...

    async def send(self, request: StructuredRequest, *, retry_safe: bool) -> Reply: ...


def request_json(request: StructuredRequest) -> dict[str, Any]:
    if request.prompt.images or request.prompt.image_consent:
        raise SnapshotError("CAPABILITY_NOT_ADMITTED")
    return dict(
        messages=[dict(role=m.role, content=m.content) for m in request.prompt.messages],
        task_profile=request.prompt.task_profile.value,
        max_output_tokens=request.prompt.max_output_tokens,
        temperature=request.prompt.temperature,
        stage=request.stage,
        json_schema=deepcopy(dict(request.json_schema)),
    )


def from_json(value: dict[str, Any]) -> StructuredRequest:
    return StructuredRequest(
        TextRequest(
            tuple(ChatMessage(m["role"], m["content"]) for m in value["messages"]),
            task_profile=TaskProfile(value["task_profile"]),
            max_output_tokens=value["max_output_tokens"],
            temperature=value["temperature"],
        ),
        value["json_schema"],
        value["stage"],
    )


class Scheduler:
    """Every public mutation commits its own short transaction; network stays outside it."""

    operation_policy = POLICY
    operation_kinds: tuple[str, ...] = (
        "create",
        "clarify",
        "resume",
        "adjust_outline",
        "revise_scene",
    )

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], *, graph_version: str | None = None
    ):
        self.sessions = sessions
        self.graph_version = graph_version

    async def _locked(
        self, db: AsyncSession, lease: Lease, *, live: bool = True
    ) -> tuple[SnapshotRepository, FreeCourse, FreeCourseOperation]:
        repo = SnapshotRepository(db, lease.owner)
        await repo._owner_lock()
        course = await repo._course(lease.course, lock=True)
        op = await (
            repo._fence(lease.course, lease.fence)
            if live
            else repo._operation(lease.course, lease.fence.operation_id)
        )
        return repo, course, op

    async def _event(
        self, db: AsyncSession, lease: Lease, kind: str, payload: dict[str, Any]
    ) -> None:
        repo = SnapshotRepository(db, lease.owner)
        course = await repo.get_course(lease.course)
        version = (
            await repo.get_version(lease.course, course["head_version"])
            if course["head_version"]
            else None
        )
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
            course_version=version["version"] if version else None,
            payload=payload,
        )
        Draft202012Validator(visibility.EVENT_SCHEMA).validate(event)
        if seq > 256 or len(canonical(event)) > 4096:
            raise SnapshotError("EVENT_LIMIT_EXCEEDED")
        db.add(
            FreeCourseEvent(
                user_id=lease.owner,
                course_id=lease.course,
                operation_id=lease.fence.operation_id,
                seq=seq,
                event_type=kind,
                course_version_id=UUID(version["id"]) if version else None,
                payload=payload,
            )
        )
        await db.flush()

    async def enqueue(
        self,
        owner: UUID,
        goal: str,
        *,
        key: str,
        teaching_language: str = "zh-CN",
        code_language: str | None = "C",
    ) -> dict[str, Any]:
        """Private create transaction; owner unresolved sends also bar creating another course."""
        async with self.sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            result = await repo.create_course(
                goal,
                key=key,
                policy_snapshot=POLICY,
                teaching_language=teaching_language,
                code_language=code_language,
            )
            op = await repo._operation(UUID(result["course_id"]), UUID(result["operation_id"]))
            if op.policy_snapshot != POLICY:
                raise SnapshotError("POLICY_MISMATCH")
            if await db.scalar(
                select(FreeCourseStep.id).where(
                    FreeCourseStep.operation_id == op.id, FreeCourseStep.step_key == "plan"
                )
            ):
                return result
            unresolved = await db.scalar(
                select(FreeCourseAttempt.id)
                .outerjoin(
                    FreeCourseSettlement, FreeCourseSettlement.attempt_id == FreeCourseAttempt.id
                )
                .where(FreeCourseAttempt.user_id == owner, FreeCourseSettlement.id.is_(None))
            )
            if unresolved:
                raise SnapshotError("OUTCOME_UNRESOLVED")
            db.add(
                FreeCourseStep(
                    user_id=owner,
                    course_id=op.course_id,
                    operation_id=op.id,
                    step_key="plan",
                    state="pending",
                )
            )
            await self._event(
                db, Lease(owner, op.course_id, WriteFence(op.id, 0, uuid4())), "queued", {}
            )
            return result

    async def claim(self) -> Lease | None:
        # Candidate lookup is unlocked. All locks are then acquired owner -> course -> operation
        # -> steps -> capacity. SKIP LOCKED at owner and capacity avoids queue head blocking.
        async with self.sessions() as db:
            candidates = (
                await db.execute(
                    select(
                        FreeCourseOperation.user_id,
                        FreeCourseOperation.course_id,
                        FreeCourseOperation.id,
                    )
                    .where(
                        FreeCourseOperation.state.in_(("queued", "running")),
                        FreeCourseOperation.policy_snapshot == self.operation_policy,
                        FreeCourseOperation.kind.in_(self.operation_kinds),
                    )
                    .order_by(FreeCourseOperation.created_at)
                    .limit(64)
                )
            ).all()
        for owner, cid, oid in candidates:
            async with self.sessions() as db, db.begin():
                if (
                    await db.scalar(
                        select(User.id).where(User.id == owner).with_for_update(skip_locked=True)
                    )
                    is None
                ):
                    continue
                repo = SnapshotRepository(db, owner)
                await repo._course(cid, lock=True)
                op = await repo._operation(cid, oid)
                now = await repo._now()
                if (
                    op.state not in ("queued", "running")
                    or op.cancel_requested_at
                    or op.deadline_at <= now
                ):
                    continue
                if op.lease_expires_at and op.lease_expires_at > now:
                    continue
                slot = await db.scalar(
                    select(FreeCourseCapacity)
                    .where(FreeCourseCapacity.state == "free")
                    .order_by(FreeCourseCapacity.slot)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                if slot is None:
                    continue
                # Expired active leases must pass reconcile first, never steal unknown sends.
                old = await db.scalar(
                    select(FreeCourseCapacity.slot).where(FreeCourseCapacity.operation_id == oid)
                )
                if old is not None:
                    continue
                fence = await repo.acquire_write_fence(cid, oid)
                slot.user_id, slot.course_id, slot.operation_id = owner, cid, oid
                slot.state, slot.epoch, slot.expires_at = "held", fence.epoch, op.lease_expires_at
                lease = Lease(owner, cid, fence)
                await self._event(db, lease, "started", {})
                return lease
        return None

    async def heartbeat(self, lease: Lease) -> None:
        async with self.sessions() as db, db.begin():
            repo, _, op = await self._locked(db, lease)
            slot = await self._slot(db, lease)
            now = await repo._now()
            op.lease_expires_at = min(op.deadline_at, now + timedelta(seconds=45))
            slot.expires_at = op.lease_expires_at

    async def _slot(self, db: AsyncSession, lease: Lease) -> FreeCourseCapacity:
        slot = await db.scalar(
            select(FreeCourseCapacity)
            .where(FreeCourseCapacity.operation_id == lease.fence.operation_id)
            .with_for_update()
        )
        if slot is None or slot.state != "held" or slot.epoch != lease.fence.epoch:
            raise SnapshotError("OPERATION_FENCED")
        return slot

    @staticmethod
    def _free(slot: FreeCourseCapacity) -> None:
        slot.state = "free"
        slot.user_id = slot.course_id = slot.operation_id = slot.pending_attempt_id = None
        slot.epoch = slot.expires_at = None

    async def _terminal(
        self,
        db: AsyncSession,
        lease: Lease,
        op: FreeCourseOperation,
        state: str,
        reason: str | None,
        *,
        quarantine: bool = False,
    ) -> None:
        steps = await visibility._steps(db, lease.owner, lease.course, op.id)
        for step in steps:
            if step.state in ("pending", "running"):
                step.state, step.reason_code = "failed", reason or "DEPENDENCY_UNAVAILABLE"
        slot = await db.scalar(
            select(FreeCourseCapacity)
            .where(FreeCourseCapacity.operation_id == op.id)
            .with_for_update()
        )
        if slot:
            if quarantine:
                pending = await db.scalar(
                    select(FreeCourseAttempt.id)
                    .outerjoin(
                        FreeCourseSettlement,
                        FreeCourseSettlement.attempt_id == FreeCourseAttempt.id,
                    )
                    .where(
                        FreeCourseAttempt.operation_id == op.id, FreeCourseSettlement.id.is_(None)
                    )
                )
                if pending:
                    slot.state, slot.pending_attempt_id = "quarantined", pending
                else:
                    self._free(slot)  # A trusted late settlement may have won this same lock.
            else:
                self._free(slot)
        op.state, op.reason_code = state, reason
        op.lease_epoch += 1
        op.lease_token, op.lease_expires_at = None, None
        if reason:
            await self._event(db, lease, "error", {"reason_code": reason})
        await self._event(db, lease, "done", {"state": state})

    async def _finish_cancel(self, db: AsyncSession, lease: Lease, op: FreeCourseOperation) -> None:
        for step in await visibility._steps(db, lease.owner, lease.course, op.id):
            if step.state in ("pending", "running"):
                step.state, step.reason_code = "cancelled", "CANCELLED"
        slot = await db.scalar(
            select(FreeCourseCapacity)
            .where(FreeCourseCapacity.operation_id == op.id)
            .with_for_update()
        )
        pending = await db.scalar(
            select(FreeCourseAttempt.id)
            .outerjoin(
                FreeCourseSettlement, FreeCourseSettlement.attempt_id == FreeCourseAttempt.id
            )
            .where(FreeCourseAttempt.operation_id == op.id, FreeCourseSettlement.id.is_(None))
        )
        if slot:
            if pending:
                slot.state, slot.pending_attempt_id = "quarantined", pending
            else:
                self._free(slot)
        op.state, op.reason_code = "cancelled", "CANCELLED"
        op.lease_token = op.lease_expires_at = None
        await self._event(db, lease, "done", {"state": "cancelled"})

    async def reconcile(self) -> int:
        """Restart scan. Local timeout never proves that a remote execution has stopped."""
        count = 0
        async with self.sessions() as db:
            candidates = (
                await db.execute(
                    select(
                        FreeCourseOperation.user_id,
                        FreeCourseOperation.course_id,
                        FreeCourseOperation.id,
                    ).where(
                        FreeCourseOperation.state.in_(ACTIVE),
                        FreeCourseOperation.kind.in_(self.operation_kinds),
                        or_(
                            FreeCourseOperation.policy_snapshot == self.operation_policy,
                            FreeCourseOperation.state == "cancel_requested",
                        ),
                    )
                )
            ).all()
        for owner, cid, oid in candidates:
            async with self.sessions() as db, db.begin():
                lease = Lease(owner, cid, WriteFence(oid, 0, uuid4()))
                repo, _, op = await self._locked(db, lease, live=False)
                now = await repo._now()
                if op.state == "cancel_requested":
                    await self._finish_cancel(db, lease, op)
                    count += 1
                    continue
                if op.state not in ("queued", "running"):
                    continue
                expired = op.lease_expires_at is not None and op.lease_expires_at <= now
                if not expired and op.deadline_at > now:
                    continue
                steps = await visibility._steps(db, owner, cid, oid)
                slot = await db.scalar(
                    select(FreeCourseCapacity)
                    .where(FreeCourseCapacity.operation_id == oid)
                    .with_for_update()
                )
                unresolved = await db.scalar(
                    select(FreeCourseAttempt.id)
                    .outerjoin(
                        FreeCourseSettlement,
                        FreeCourseSettlement.attempt_id == FreeCourseAttempt.id,
                    )
                    .where(FreeCourseAttempt.operation_id == oid, FreeCourseSettlement.id.is_(None))
                )
                if unresolved:
                    if slot:
                        slot.pending_attempt_id = unresolved
                    await self._terminal(
                        db, lease, op, "failed", "OUTCOME_UNKNOWN", quarantine=True
                    )
                elif op.deadline_at <= now:
                    await self._terminal(db, lease, op, "timed_out", "DEADLINE_EXCEEDED")
                elif expired:
                    from app.services.free_course_revision import context, plan_binding

                    revision = await context(db, op.id)
                    if revision is not None and await plan_binding(db, op.id) is not None:
                        # Private replacement snapshots belong to their original epoch. Do not
                        # mix/relabel them or spend calls on a plan that cannot legally publish.
                        await self._terminal(db, lease, op, "failed", "LEASE_LOST")
                    else:
                        for step in steps:
                            if step.state == "running":
                                step.state = "pending"
                        if slot:
                            self._free(slot)
                        op.state = "queued"
                        op.lease_epoch += 1
                        op.lease_token = op.lease_expires_at = None
                count += 1
        return count

    async def budget(self, db: AsyncSession, cid: UUID, oid: UUID) -> dict[str, int]:
        rows = (
            await db.execute(
                select(FreeCourseAttempt, FreeCourseSettlement)
                .outerjoin(
                    FreeCourseSettlement, FreeCourseSettlement.attempt_id == FreeCourseAttempt.id
                )
                .where(FreeCourseAttempt.course_id == cid)
            )
        ).all()
        result = dict(
            course_attempts=0,
            operation_attempts=0,
            course_input=0,
            course_output=0,
            operation_input=0,
            operation_output=0,
            transport_retry=0,
            format_repair=0,
        )
        for attempt, settled in rows:
            result["course_attempts"] += 1
            inp = (
                settled.input_tokens
                if settled and settled.input_tokens is not None
                else attempt.input_tokens
            )
            out = (
                settled.output_tokens
                if settled and settled.output_tokens is not None
                else attempt.output_tokens
            )
            result["course_input"] += inp
            result["course_output"] += out
            if attempt.operation_id == oid:
                result["operation_attempts"] += 1
                result["operation_input"] += inp
                result["operation_output"] += out
                if attempt.purpose in ("transport_retry", "format_repair"):
                    result[attempt.purpose] += 1
        return result

    async def _work(self, db: AsyncSession, lease: Lease) -> FreeCourseStep | None:
        repo = SnapshotRepository(db, lease.owner)
        steps = await visibility._steps(db, lease.owner, lease.course, lease.fence.operation_id)
        # Plan first, then exact plan order. One operation holds one execution slot.
        plan = next((s for s in steps if s.step_key == "plan"), None)
        if plan and plan.state in ("pending", "running"):
            return plan
        if plan and plan.state == "failed":
            return None
        from app.services import free_course_revision as revisions

        if await revisions.context(db, lease.fence.operation_id) is not None:
            return await revisions.next_step(db, lease.owner, lease.course, lease.fence)
        scene_steps = {str(s.scene_id): s for s in steps if s.scene_id is not None}
        if not scene_steps:
            return None
        first = next(iter(scene_steps.values()))
        assert first.plan_id is not None
        current = await repo.get_plan(lease.course, first.plan_id)
        head = (await repo.get_course(lease.course))["head_version"]
        available = await visibility.read_availability(db, lease.owner, lease.course, version=head)
        ready = {
            item["scene_id"] for item in available["scenes"] if item["content_state"] == "ready"
        }
        for scene in current["scenes"]:
            step = scene_steps.get(scene["scene_id"])
            if step is None or step.state not in ("pending", "running"):
                continue
            deps = [scene_steps[d] for d in scene["depends_on"] if d in scene_steps]
            if any(s.state in ("failed", "blocked_dependency") for s in deps):
                step.state, step.reason_code = "blocked_dependency", "DEPENDENCY_UNAVAILABLE"
                continue
            if set(scene["depends_on"]) <= ready:
                return step
        return None

    async def prepare(self, lease: Lease, adapter: Adapter) -> UUID | None:
        """Commit an irreversible conservative sent reservation BEFORE invoking adapter.send."""
        policy = adapter.policy
        if not policy.package_id or policy.requests <= 0 or not policy.bounded_output_verified:
            raise SnapshotError("EXECUTION_NOT_AUTHORIZED")
        async with self.sessions() as db, db.begin():
            repo, course, op = await self._locked(db, lease)
            from app.services import free_course_revision as revisions

            revision = await revisions.context(db, op.id)
            if revision is not None:
                await revisions.ensure_plan(db, lease.owner, lease.course, lease.fence)
            step = await self._work(db, lease)
            slot = await self._slot(db, lease)
            if slot.pending_attempt_id:
                return (
                    slot.pending_attempt_id
                )  # Caller must process settlement or quarantine, never resend.
            if step is None:
                if revision is not None:
                    await revisions.publish(db, lease.owner, lease.course, lease.fence)
                    await self._terminal(db, lease, op, "succeeded", None)
                    return None
                steps = await visibility._steps(db, lease.owner, lease.course, op.id)
                scene_steps = [s for s in steps if s.scene_id]
                ready = sum(s.state == "ready" for s in scene_steps)
                state = (
                    "succeeded"
                    if scene_steps and ready == len(scene_steps)
                    else "partially_succeeded"
                    if ready
                    else "failed"
                )
                await self._terminal(
                    db, lease, op, state, None if state == "succeeded" else "DEPENDENCY_UNAVAILABLE"
                )
                return None
            now = await repo._now()
            if step.next_attempt_at and step.next_attempt_at > now:
                return None
            previous = (
                await db.scalars(
                    select(FreeCourseAttempt)
                    .where(FreeCourseAttempt.step_id == step.id)
                    .order_by(FreeCourseAttempt.created_at)
                )
            ).all()
            # A settled response left by a crashed worker is resumed without network, even if
            # its old lease epoch is stale. Its content remains bound to exact immutable inputs.
            if previous and step.retry_purpose is None:
                return previous[-1].id
            purpose = step.retry_purpose or "primary"
            if any(a.purpose == purpose for a in previous):
                raise SnapshotError("ATTEMPT_ALREADY_SENT")
            if step.scene_id is None:
                inputs = await plans.load_inputs(db, lease.owner, lease.course, op.id)
                request = planner.build_request(inputs)
            else:
                assert step.plan_id is not None
                inputs = await scenes.load_inputs(
                    db,
                    lease.owner,
                    lease.course,
                    op.id,
                    plan_id=step.plan_id,
                    scene_id=step.scene_id,
                    expected_head=(await repo.get_course(lease.course))["head_version"],
                )
                request = generator.build_request(inputs)
            if purpose == "format_repair" or (
                purpose == "transport_retry"
                and previous
                and previous[-1].purpose == "format_repair"
            ):
                last = await db.scalar(
                    select(FreeCourseSettlement).where(
                        FreeCourseSettlement.attempt_id == previous[-1].id
                    )
                )
                raw = last.outcome_json.get("value") if last else None
                repair = canonical(dict(errors=["SCHEMA_INVALID"], previous_candidate=raw)).decode()
                request = replace(
                    request,
                    prompt=replace(
                        request.prompt,
                        messages=request.prompt.messages
                        + (
                            ChatMessage(
                                "user",
                                "Repair only structural schema/local-reference errors. "
                                "Preserve original requirements. Untrusted candidate:\n" + repair,
                            ),
                        ),
                    ),
                )
            inp = adapter.input_upper_bound(request)
            out = min(request.prompt.max_output_tokens or 8000, policy.output_limit, 8000)
            if type(inp) is not int or inp < 1 or inp > min(32000, policy.input_limit) or out < 1:
                await self._terminal(db, lease, op, "failed", "BUDGET_EXHAUSTED")
                return None
            request = replace(request, prompt=replace(request.prompt, max_output_tokens=out))
            budget = await self.budget(db, lease.course, op.id)
            exceeded = any(
                (budget[k] + delta > cap)
                for k, delta, cap in (
                    ("operation_attempts", 1, 13),
                    ("course_attempts", 1, 40),
                    ("operation_input", inp, 200000),
                    ("operation_output", out, 48000),
                    ("course_input", inp, 600000),
                    ("course_output", out, 144000),
                )
            )
            if purpose != "primary" and budget[purpose] >= 2:
                exceeded = True
            # Package-wide lock precedes aggregating global requests/cost; no per-course reset.
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
                min(
                    policy.input_micros_per_token, policy.output_micros_per_token, policy.fee_micros
                )
                < 0
            ):
                raise SnapshotError("EXECUTION_NOT_AUTHORIZED")
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
                purpose=purpose,
                lease_epoch=lease.fence.epoch,
                input_tokens=inp,
                output_tokens=out,
                fee_micros=fee,
                sent_at=now,
                input_snapshot=inputs,
                request_digest=digest("outbound-request", request=packed),
                request_json=dict(
                    request=packed, package_id=policy.package_id, send_policy=asdict(policy)
                ),
            )
            db.add(attempt)
            await db.flush()
            step.state, step.retry_purpose, step.next_attempt_at = "running", None, None
            slot.pending_attempt_id = attempt.id
            if step.scene_id:
                await self._event(db, lease, "scene_started", {"scene_id": str(step.scene_id)})
            await visibility._live(db, lease.owner, lease.course, lease.fence)
            return attempt.id

    async def settle(self, attempt_id: UUID, reply: Reply) -> bool:
        """Only trustworthy remote completion releases capacity. Late facts cannot publish."""
        if (
            reply.evidence not in ("complete_response", "not_executed", "stopped")
            or not reply.evidence_digest
        ):
            return False
        if len(reply.evidence_digest) != 64 or any(
            c not in "0123456789abcdef" for c in reply.evidence_digest
        ):
            raise SnapshotError("EVIDENCE_INVALID")
        async with self.sessions() as db:
            a = await db.get(FreeCourseAttempt, attempt_id)
            if a is None:
                raise SnapshotError("NOT_FOUND")
            lease = Lease(a.user_id, a.course_id, WriteFence(a.operation_id, 0, uuid4()))
            repo, _, _ = await self._locked(db, lease, live=False)
            slot = await db.scalar(
                select(FreeCourseCapacity)
                .where(FreeCourseCapacity.operation_id == a.operation_id)
                .with_for_update()
            )
            usage = (reply.input_tokens, reply.output_tokens)
            if any(v is not None and (type(v) is not int or v < 0) for v in usage):
                raise SnapshotError("USAGE_INVALID")
            inp, out = usage if all(v is not None for v in usage) else (None, None)
            if (inp is not None and inp > a.input_tokens) or (
                out is not None and out > a.output_tokens
            ):
                raise SnapshotError("USAGE_EXCEEDS_RESERVATION")
            if reply.evidence == "not_executed":
                inp, out = 0, 0
            value = deepcopy(reply.value)
            if value is not None and len(canonical(value)) > 65536:
                value = None
            outcome = dict(
                value=value,
                status=reply.status,
                retry_after=reply.retry_after,
                hard_failure=reply.hard_failure,
            )
            existing = await db.scalar(
                select(FreeCourseSettlement).where(FreeCourseSettlement.attempt_id == attempt_id)
            )
            if existing:
                if (
                    existing.evidence,
                    existing.evidence_digest,
                    existing.input_tokens,
                    existing.output_tokens,
                    existing.outcome_json,
                ) != (reply.evidence, reply.evidence_digest, inp, out, outcome):
                    raise SnapshotError("SETTLEMENT_CONFLICT")
                if slot and slot.state == "quarantined" and slot.pending_attempt_id == attempt_id:
                    self._free(slot)
                    await db.commit()
                return True
            db.add(
                FreeCourseSettlement(
                    user_id=a.user_id,
                    course_id=a.course_id,
                    attempt_id=attempt_id,
                    evidence=reply.evidence,
                    evidence_digest=reply.evidence_digest,
                    input_tokens=inp,
                    output_tokens=out,
                    outcome_json=outcome,
                )
            )
            await db.flush()
            if slot and slot.state == "quarantined" and slot.pending_attempt_id == attempt_id:
                self._free(slot)
            await db.commit()
            return True

    async def before_dispatch(
        self, db: AsyncSession, lease: Lease, attempt: FreeCourseAttempt
    ) -> bool:
        """Protocol specialization may recheck its exact sources under existing dispatch locks."""
        return True

    async def deliver(self, lease: Lease, attempt_id: UUID, adapter: Adapter) -> None:
        """Send only a reservation created by THIS invocation of run_once (never queue payload)."""
        async with self.sessions() as db:
            repo, _, op = await self._locked(db, lease)
            slot = await self._slot(db, lease)
            attempt = await db.get(FreeCourseAttempt, attempt_id)
            if (
                attempt is None
                or attempt.operation_id != op.id
                or attempt.lease_epoch != lease.fence.epoch
                or slot.pending_attempt_id != attempt_id
            ):
                raise SnapshotError("OPERATION_FENCED")
            dispatched = await db.scalar(
                select(FreeCourseDispatch.id).where(FreeCourseDispatch.attempt_id == attempt_id)
            )
            if dispatched is not None:
                return
            if not await self.before_dispatch(db, lease, attempt):
                await db.commit()
                return
            db.add(
                FreeCourseDispatch(
                    user_id=lease.owner, course_id=lease.course, attempt_id=attempt_id
                )
            )
            if attempt.request_json.get("send_policy") != asdict(adapter.policy):
                raise SnapshotError("EXECUTION_PACKAGE_CHANGED")
            request = from_json(attempt.request_json["request"])
            timeout = min(120.0, (op.deadline_at - await repo._now()).total_seconds())
            stop_at = asyncio.get_running_loop().time() + timeout
            await db.commit()

        async def watch_fence() -> None:
            while True:
                await asyncio.sleep(1)
                async with self.sessions() as db:
                    current = await db.get(FreeCourseOperation, lease.fence.operation_id)
                    if (
                        current is None
                        or current.state != "running"
                        or current.lease_epoch != lease.fence.epoch
                        or current.lease_token != lease.fence.token
                    ):
                        return

        async def late_settlement(task: asyncio.Task[Reply]) -> None:
            try:
                result = task.result()
                await self.settle(attempt_id, result)  # Facts only; never consumes/publishes.
            except (Exception, asyncio.CancelledError):
                pass  # No trustworthy fact: keep the durable reservation/quarantine.

        sender = asyncio.create_task(adapter.send(request, retry_safe=False))
        watcher = asyncio.create_task(watch_fence())
        try:
            done, _ = await asyncio.wait(
                [sender, watcher],
                timeout=max(0, stop_at - asyncio.get_running_loop().time()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            reply = sender.result() if sender in done and not sender.cancelled() else Reply()
        except Exception:
            reply = Reply()  # Generic exceptions cannot prove remote termination.
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            if not sender.done():
                sender.cancel()  # Best effort local abort; cannot prove remote execution stopped.
                sender.add_done_callback(lambda task: asyncio.create_task(late_settlement(task)))
        if not await self.settle(attempt_id, reply):
            async with self.sessions() as db, db.begin():
                _, _, op = await self._locked(db, lease, live=False)
                if (
                    op.state == "running"
                    and op.lease_epoch == lease.fence.epoch
                    and op.lease_token == lease.fence.token
                ):
                    await self._terminal(
                        db, lease, op, "failed", "OUTCOME_UNKNOWN", quarantine=True
                    )
            return
        await self.consume(lease, attempt_id)

    async def consume(self, lease: Lease, attempt_id: UUID) -> None:
        async with self.sessions() as db, db.begin():
            repo, _, op = await self._locked(db, lease)
            step_rows = await visibility._steps(db, lease.owner, lease.course, op.id)
            slot = await self._slot(db, lease)
            a = await db.get(FreeCourseAttempt, attempt_id)
            if a is None or a.operation_id != op.id:
                raise SnapshotError("NOT_FOUND")
            step = next(s for s in step_rows if s.id == a.step_id)
            if step.state != "running" and step.state != "pending":
                return
            settled = await db.scalar(
                select(FreeCourseSettlement).where(FreeCourseSettlement.attempt_id == a.id)
            )
            if settled is None:
                # A duplicate delivery while the original sender is still live is a no-op.
                # Only explicit unknown transport evidence or the expiry scanner quarantines.
                return
            # Reclaimed response cannot be relabelled with a newer epoch and become publishable.
            if a.lease_epoch != lease.fence.epoch:
                slot.pending_attempt_id = None
                await self._terminal(db, lease, op, "failed", "LEASE_LOST")
                return
            result = settled.outcome_json
            value = result["value"]
            status = result["status"]
            if result["hard_failure"] or (status is not None and status in (401, 403)):
                slot.pending_attempt_id = None
                await self._terminal(db, lease, op, "failed", "PROVIDER_REJECTED")
                return
            if (
                status in (429, 502, 503, 504)
                and value is None
                and settled.evidence in ("not_executed", "stopped")
            ):
                retry_after = result["retry_after"]
                delay = 2
                valid = retry_after is None or (
                    isinstance(retry_after, str)
                    and retry_after.isascii()
                    and retry_after.isdigit()
                    and 0 <= int(retry_after) <= 30
                )
                if valid:
                    delay = max(delay, int(retry_after or "0"))
                attempts = (
                    await db.scalars(
                        select(FreeCourseAttempt).where(FreeCourseAttempt.step_id == step.id)
                    )
                ).all()
                budget = await self.budget(db, lease.course, op.id)
                if (
                    valid
                    and not any(x.purpose == "transport_retry" for x in attempts)
                    and budget["transport_retry"] < 2
                    and (await repo._now()) + timedelta(seconds=delay) < op.deadline_at
                ):
                    step.state, step.retry_purpose = "pending", "transport_retry"
                    step.next_attempt_at = await repo._now() + timedelta(seconds=delay)
                    slot.pending_attempt_id = None
                    return
                await self._fail_step(db, lease, op, step, "PROVIDER_REJECTED")
                slot.pending_attempt_id = None
                return
            if status is not None and status >= 400:
                slot.pending_attempt_id = None
                await self._fail_step(db, lease, op, step, "PROVIDER_REJECTED")
                return
            inputs = a.input_snapshot
            try:
                if step.scene_id is None:
                    planner.validate_response(value, inputs)
                else:
                    generator.validate_response(value, inputs)
                    checked = check_scene(value, inputs)
                    if checked["state"] != "accepted":
                        raise SnapshotError(
                            "HARD_SAFETY_FAILURE"
                            if checked["reason_code"] == "UNSAFE_CONTENT"
                            else "SCHEMA_INVALID"
                        )
            except (SnapshotError, TypeError, ValueError):
                # Hard-safety rejection is never eligible for format repair.
                hard = (
                    step.scene_id is not None
                    and value is not None
                    and check_scene(value, inputs).get("reason_code") == "UNSAFE_CONTENT"
                )
                attempts = (
                    await db.scalars(
                        select(FreeCourseAttempt).where(FreeCourseAttempt.step_id == step.id)
                    )
                ).all()
                budget = await self.budget(db, lease.course, op.id)
                if (
                    not hard
                    and not any(x.purpose == "format_repair" for x in attempts)
                    and budget["format_repair"] < 2
                ):
                    step.state, step.retry_purpose = "pending", "format_repair"
                    slot.pending_attempt_id = None
                    return
                slot.pending_attempt_id = None
                await self._fail_step(db, lease, op, step, "SCHEMA_INVALID")
                return
            if step.scene_id is None:
                outcome = planner.PlanningOutcome(
                    "needs_clarification" if value["needs_clarification"] else "ready",
                    None,
                    digest("planning-input", snapshot=inputs),
                    planner.request_digest(planner.build_request(inputs)),
                    value,
                )
                saved = await plans.persist_outcome(
                    db,
                    lease.owner,
                    lease.course,
                    lease.fence,
                    expected_head=op.base_head_version,
                    call_key=str(a.id),
                    inputs=inputs,
                    outcome=outcome,
                )
                if saved["state"] == "needs_clarification":
                    step.state = "failed"
                    await self._event(
                        db, lease, "clarification_required", {"questions": value["questions"]}
                    )
                    await self._terminal(db, lease, op, "awaiting_clarification", None)
                else:
                    # Completed planning step is separate from learnable scene readiness.
                    step.state = "ready"
                    from app.services import free_course_revision as revisions

                    if await revisions.context(db, op.id) is not None:
                        await revisions.bind_plan(
                            db, lease.owner, lease.course, lease.fence, UUID(saved["plan_id"])
                        )
                    else:
                        await visibility.commit_outline(
                            db,
                            lease.owner,
                            lease.course,
                            lease.fence,
                            plan_id=UUID(saved["plan_id"]),
                            key=f"scheduler-outline:{a.id}",
                            graph_version=self.graph_version,
                        )
            else:
                usage = dict(input_tokens=settled.input_tokens, output_tokens=settled.output_tokens)
                scene_outcome = generator.SceneOutcome(
                    "candidate",
                    None,
                    digest("scene-generation-input", snapshot=inputs),
                    planner.request_digest(generator.build_request(inputs)),
                    value,
                    usage,
                )
                saved = await scenes.persist_outcome(
                    db,
                    lease.owner,
                    lease.course,
                    lease.fence,
                    call_key=str(a.id),
                    inputs=inputs,
                    outcome=scene_outcome,
                )
                admitted = await validate_candidate(
                    db, lease.owner, lease.course, lease.fence, result_id=UUID(saved["result_id"])
                )
                from app.services import free_course_revision as revisions

                if await revisions.context(db, op.id) is not None:
                    await revisions.stage_validation(
                        db, lease.owner, lease.course, lease.fence, UUID(admitted["validation_id"])
                    )
                else:
                    await visibility.commit_scene(
                        db,
                        lease.owner,
                        lease.course,
                        lease.fence,
                        validation_id=UUID(admitted["validation_id"]),
                        expected_head=inputs["expected_head"],
                        key=f"scheduler-scene:{a.id}",
                    )
            if slot.state == "held":
                slot.pending_attempt_id = None

    async def _fail_step(
        self,
        db: AsyncSession,
        lease: Lease,
        op: FreeCourseOperation,
        step: FreeCourseStep,
        reason: str,
    ) -> None:
        from app.services.free_course_revision import context

        if step.scene_id is None or await context(db, op.id) is not None:
            await self._terminal(db, lease, op, "failed", reason)
        else:
            repo = SnapshotRepository(db, lease.owner)
            head = (await repo.get_course(lease.course))["head_version"]
            await visibility.fail_scene(
                db,
                lease.owner,
                lease.course,
                lease.fence,
                scene_id=step.scene_id,
                expected_head=head,
                reason_code=reason,
                key=f"scheduler-fail:{step.id}",
            )

    async def run_once(self, lease: Lease, adapter: Adapter) -> None:
        """Duplicate delivery never resends an existing conservative sent fact."""
        async with self.sessions() as db:
            previous = set(
                (
                    await db.scalars(
                        select(FreeCourseAttempt.id).where(
                            FreeCourseAttempt.operation_id == lease.fence.operation_id
                        )
                    )
                ).all()
            )
        attempt_id = await self.prepare(lease, adapter)
        if attempt_id is None:
            return
        if attempt_id in previous:
            await self.consume(lease, attempt_id)
            return
        # Only a successfully committed *new* reservation may cross the outbound boundary.
        await self.deliver(lease, attempt_id, adapter)

    async def work(self, adapter: Adapter, stop: asyncio.Event) -> None:
        """Explicitly invoked private worker. Restart scans DB, never browser state.

        Deploy/CLI registration is intentionally absent until runtime authorization and API tasks.
        """
        while not stop.is_set():
            await self.reconcile()
            lease = await self.claim()
            if lease is None:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1)
                except TimeoutError:
                    pass
                continue

            async def renew() -> None:
                while True:
                    await asyncio.sleep(10)
                    await self.heartbeat(lease)

            pulse = asyncio.create_task(renew())
            try:
                while not stop.is_set():
                    async with self.sessions() as db:
                        op = await db.get(FreeCourseOperation, lease.fence.operation_id)
                        if op is None or op.state != "running":
                            break
                    await self.run_once(lease, adapter)
                    await asyncio.sleep(1)
            except SnapshotError:
                # Stop renewing a broken/fenced execution. The next scan resolves durable facts;
                # never send again in this handler or keep a failing lease alive indefinitely.
                await self.reconcile()
            finally:
                pulse.cancel()
                await asyncio.gather(pulse, return_exceptions=True)
