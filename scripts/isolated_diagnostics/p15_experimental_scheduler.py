"""ADR0034 isolated experimental scheduler; production policy remains unchanged.

prepare/settle are explicit copies of the frozen scheduler with only the approved experimental
admission/accounting differences. This cannot prove the original production bound contract.
"""

from copy import deepcopy
from dataclasses import asdict, replace
from uuid import UUID, uuid4
from sqlalchemy import select, func
from app.services.free_course_scheduler import (
    Adapter,
    Scheduler,
    Lease,
    Reply,
    FreeCourseAttempt,
    FreeCourseSettlement,
    FreeCourseCapacity,
    SnapshotError,
    WriteFence,
    plans,
    scenes,
    planner,
    generator,
    visibility,
    canonical,
    digest,
    ChatMessage,
    request_json,
)


class ExperimentalScheduler(Scheduler):
    async def prepare(self, lease: Lease, adapter: Adapter) -> UUID | None:
        """Experimental reservation before send; no claim of token or invoice bounds."""
        from isolated_diagnostics.p15_exploration import ExplorationAdapter

        policy = adapter.policy
        if (
            not policy.package_id
            or policy.requests != 250
            or policy.bounded_output_verified
            or not isinstance(adapter, ExplorationAdapter)
        ):
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
                    db,
                    lease,
                    op,
                    state,
                    None if state == "succeeded" else "DEPENDENCY_UNAVAILABLE",
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
                repair = canonical(
                    dict(errors=["SCHEMA_INVALID"], previous_candidate=raw)
                ).decode()
                request = replace(
                    request,
                    prompt=replace(
                        request.prompt,
                        messages=request.prompt.messages
                        + (
                            ChatMessage(
                                "user",
                                "Repair only structural schema/local-reference errors. "
                                "Preserve original requirements. Untrusted candidate:\n"
                                + repair,
                            ),
                        ),
                    ),
                )
            # Compatibility placeholder required by existing PG constraint; NOT a token bound.
            inp = 1
            out = min(
                request.prompt.max_output_tokens or 8000, policy.output_limit, 8000
            )
            if (
                type(inp) is not int
                or inp < 1
                or inp > min(32000, policy.input_limit)
                or out < 1
            ):
                await self._terminal(db, lease, op, "failed", "BUDGET_EXHAUSTED")
                return None
            request = replace(
                request, prompt=replace(request.prompt, max_output_tokens=out)
            )
            budget = await self.budget(db, lease.course, op.id)
            exceeded = any(
                (budget[k] + delta > cap)
                for k, delta, cap in (
                    ("operation_attempts", 1, 13),
                    ("course_attempts", 1, 40),
                )
            )
            if purpose != "primary" and budget[purpose] >= 2:
                exceeded = True
            # Package-wide lock precedes aggregating global requests/cost; no per-course reset.
            await db.execute(
                select(
                    func.pg_advisory_xact_lock(7414, func.hashtext(policy.package_id))
                )
            )
            package_rows = (
                await db.scalars(
                    select(FreeCourseAttempt).where(
                        FreeCourseAttempt.request_json["package_id"].astext
                        == policy.package_id
                    )
                )
            ).all()
            fee = (
                inp * policy.input_micros_per_token
                + out * policy.output_micros_per_token
            )
            if (
                min(
                    policy.input_micros_per_token,
                    policy.output_micros_per_token,
                    policy.fee_micros,
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
                    request=packed,
                    package_id=policy.package_id,
                    send_policy=asdict(policy),
                    exploration_exception="ADR-0034",
                    input_reservation_is_placeholder=True,
                    verified_input_bound=None,
                    verified_output_bound=None,
                    actual_fee_micros=None,
                ),
            )
            db.add(attempt)
            await db.flush()
            step.state, step.retry_purpose, step.next_attempt_at = "running", None, None
            slot.pending_attempt_id = attempt.id
            if step.scene_id:
                await self._event(
                    db, lease, "scene_started", {"scene_id": str(step.scene_id)}
                )
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
            lease = Lease(
                a.user_id, a.course_id, WriteFence(a.operation_id, 0, uuid4())
            )
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
            if a.request_json.get("exploration_exception") != "ADR-0034":
                raise SnapshotError("EXPERIMENTAL_ATTEMPT_REQUIRED")
            # Store reported usage, including overflow, without declaring it bounded or invoiced.
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
                select(FreeCourseSettlement).where(
                    FreeCourseSettlement.attempt_id == attempt_id
                )
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
                if (
                    slot
                    and slot.state == "quarantined"
                    and slot.pending_attempt_id == attempt_id
                ):
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
            if (
                slot
                and slot.state == "quarantined"
                and slot.pending_attempt_id == attempt_id
            ):
                self._free(slot)
            await db.commit()
            return True
