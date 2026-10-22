"""Actual isolated PG scheduler and injected transport; no real Provider or HTTP opening."""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_free_course_planning import candidate
from test_free_scene_generation import response

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course_progress import FreeCourseEvent, FreeCourseStep
from app.models.free_course_scheduler import (
    FreeCourseAttempt,
    FreeCourseCapacity,
    FreeCourseDispatch,
    FreeCourseSettlement,
)
from app.models.free_course_writes import FreeCourseOperation, FreeCourseReceipt
from app.services.free_course_scheduler import POLICY, Lease, Reply, Scheduler, SendPolicy
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, WriteFence, digest
from app.services.free_scene_availability import read_availability

ROOT = Path(__file__).resolve().parents[2]
GOAL = "学习数组与单链表"
PROOF = "a" * 64


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value, "Actual isolated PG required, no environment skip"
    url = make_url(value)
    assert url.host == "127.0.0.1" and url.port == 15437
    assert (url.database or "").startswith("edumind_catalog_p15_t014_")
    return value


@pytest.fixture(scope="module", autouse=True)
def migrate_database():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


class FakeAdapter:
    def __init__(self, replies=(), *, n=2, policy=None):
        self.policy = policy or SendPolicy(
            package_id=str(uuid4()),
            requests=100,
            fee_micros=10000000,
            input_micros_per_token=1,
            output_micros_per_token=1,
            bounded_output_verified=True,
        )
        self.replies = list(replies)
        self.calls = []
        self.n = n
        self.observe = None

    def input_upper_bound(self, request):
        # Mock-only exact admission bound. No production tokenizer claim.
        return 1000

    async def send(self, request, *, retry_safe):
        assert retry_safe is False
        self.calls.append(request)
        if self.observe:
            await self.observe(request)
        if self.replies:
            result = self.replies.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        value = (
            candidate(self.n, GOAL)
            if request.stage == "free_course_plan_generation"
            else response(["text"])
        )
        return Reply("complete_response", PROOF, value, 100, 200)


def exercise(action):
    async def run():
        engine = create_database_engine(database_url())
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        owners = [uuid4() for _ in range(4)]
        try:
            async with sessions() as db:
                db.add_all([User(id=u, is_guest=True) for u in owners])
                await db.commit()
            await action(Scheduler(sessions), sessions, owners)
        finally:
            async with engine.begin() as conn:
                # Test-only cleanup after all injected calls finish; no real unknown remote work.
                await conn.execute(
                    text(
                        "UPDATE free_course_capacity SET state='free', user_id=NULL, "
                        "course_id=NULL, operation_id=NULL, epoch=NULL, expires_at=NULL, "
                        "pending_attempt_id=NULL"
                    )
                )
                for owner in owners:
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": owner})
            await engine.dispose()

    asyncio.run(run())


async def setup(scheduler, owner):
    result = await scheduler.enqueue(owner, GOAL, key="create")
    lease = await scheduler.claim()
    assert lease is not None and lease.owner == owner
    assert str(lease.fence.operation_id) == result["operation_id"]
    return lease


async def state(sessions, lease):
    async with sessions() as db:
        op = await db.get(FreeCourseOperation, lease.fence.operation_id)
        return op.state, op.reason_code


async def expire(sessions, lease, *, deadline=False):
    async with sessions() as db, db.begin():
        field = "deadline_at" if deadline else "lease_expires_at"
        await db.execute(
            text(
                f"UPDATE free_course_operations SET {field}=clock_timestamp()-"
                "interval '1 second' WHERE id=:id"
            ),
            {"id": lease.fence.operation_id},
        )


def test_full_progressive_course_and_restart_no_browser():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        adapter = FakeAdapter()

        async def observe(request):
            async with sessions() as db:
                attempt = await db.scalar(
                    select(FreeCourseAttempt)
                    .where(FreeCourseAttempt.operation_id == lease.fence.operation_id)
                    .order_by(FreeCourseAttempt.created_at.desc())
                )
                assert attempt.sent_at and await db.scalar(
                    select(FreeCourseDispatch.id).where(FreeCourseDispatch.attempt_id == attempt.id)
                )
                assert attempt.request_json["request"]["max_output_tokens"] <= 8000

        adapter.observe = observe
        await s.run_once(lease, adapter)  # plan
        s = Scheduler(sessions)  # reconstruct entirely from durable PG, no browser/queue memory
        await s.run_once(lease, adapter)  # first scene
        async with sessions() as db:
            visible = await read_availability(db, lease.owner, lease.course, version=2)
            assert visible["ready_count"] == 1 and not visible["all_scenes_ready"]
        assert await state(sessions, lease) == ("running", None)
        await s.run_once(lease, adapter)
        await s.run_once(lease, adapter)
        assert await state(sessions, lease) == ("succeeded", None)
        assert len(adapter.calls) == 3
        async with sessions() as db:
            budget = await s.budget(db, lease.course, lease.fence.operation_id)
            assert budget["operation_attempts"] == 3 and budget["operation_input"] == 300
            events = (
                await db.scalars(
                    select(FreeCourseEvent)
                    .where(FreeCourseEvent.operation_id == lease.fence.operation_id)
                    .order_by(FreeCourseEvent.seq)
                )
            ).all()
            assert [e.seq for e in events] == list(range(1, len(events) + 1))
            assert sum(e.event_type == "first_scene_ready" for e in events) == 1
            assert events[-1].event_type == "done" and events[-1].payload == {"state": "succeeded"}
            assert not await db.scalar(
                select(FreeCourseCapacity.slot).where(FreeCourseCapacity.state != "free")
            )

    exercise(action)


def test_duplicate_create_claim_and_owner_limit():
    async def action(s, sessions, owners):
        created = await asyncio.gather(
            s.enqueue(owners[0], GOAL, key="create"), s.enqueue(owners[0], GOAL, key="create")
        )
        assert created[0] == created[1]
        with pytest.raises(SnapshotError, match="OPERATION_ACTIVE"):
            await s.enqueue(owners[0], GOAL, key="different")
        claims = await asyncio.gather(s.claim(), s.claim())
        assert sum(c is not None for c in claims) == 1
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseOperation)
                    .where(FreeCourseOperation.user_id == owners[0])
                )
                == 1
            )

    exercise(action)


def test_global_two_slots_and_queued_deadline_without_slot():
    async def action(s, sessions, owners):
        for o in owners[:2]:
            await s.enqueue(o, GOAL, key="create")
        constructor = FreeCourseOperation.__init__

        def old_operation(self, **kwargs):
            constructor(
                self,
                **{**kwargs, "deadline_at": func.clock_timestamp() - text("interval '1 second'")},
            )

        with patch.object(FreeCourseOperation, "__init__", old_operation):
            await s.enqueue(owners[2], GOAL, key="create")
        claims = await asyncio.gather(s.claim(), s.claim(), s.claim())
        assert sum(c is not None for c in claims) == 2
        async with sessions() as db:
            queued = await db.scalar(
                select(FreeCourseOperation).where(
                    FreeCourseOperation.state == "queued", FreeCourseOperation.user_id.in_(owners)
                )
            )
            lease = Lease(queued.user_id, queued.course_id, WriteFence(queued.id, 0, uuid4()))
        assert await s.reconcile() == 1
        assert await state(sessions, lease) == ("timed_out", "DEADLINE_EXCEEDED")

    exercise(action)


def test_expired_no_send_reclaimed_with_same_deadline_and_stale_fence_refused():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        async with sessions() as db:
            before = (await db.get(FreeCourseOperation, lease.fence.operation_id)).deadline_at
        await expire(sessions, lease)
        assert await s.reconcile() == 1
        fresh = await Scheduler(sessions).claim()
        assert fresh.fence.epoch > lease.fence.epoch
        with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
            await s.heartbeat(lease)
        async with sessions() as db:
            assert (
                await db.get(FreeCourseOperation, lease.fence.operation_id)
            ).deadline_at == before
        await s.run_once(fresh, FakeAdapter(n=1))

    exercise(action)


def test_sent_before_dispatch_crash_quarantines_without_resend():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter()
        aid = await s.prepare(lease, a)
        await expire(sessions, lease)
        await s.reconcile()
        assert await state(sessions, lease) == ("failed", "OUTCOME_UNKNOWN")
        assert await s.claim() is None and not a.calls
        replay = await s.enqueue(owners[0], GOAL, key="create")
        assert replay == {
            "course_id": str(lease.course),
            "operation_id": str(lease.fence.operation_id),
        }
        with pytest.raises(SnapshotError, match="OUTCOME_UNRESOLVED"):
            await s.enqueue(owners[0], GOAL, key="new-course")
        async with sessions() as db:
            cap = await db.scalar(
                select(FreeCourseCapacity).where(
                    FreeCourseCapacity.operation_id == lease.fence.operation_id
                )
            )
            assert cap.state == "quarantined" and cap.pending_attempt_id == aid
            budget = await s.budget(db, lease.course, lease.fence.operation_id)
            assert budget["operation_attempts"] == 1 and budget["operation_output"] == 8000
        assert not await s.settle(aid, Reply())
        assert await s.settle(aid, Reply("not_executed", PROOF))
        assert await state(sessions, lease) == ("failed", "OUTCOME_UNKNOWN")
        await s.enqueue(owners[0], GOAL, key="new-course")

    exercise(action)


@pytest.mark.parametrize(
    "failure", [Reply(), TimeoutError(), RuntimeError("synthetic secret"), Reply(status=504)]
)
def test_unknown_failure_is_never_automatically_retried(failure):
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter([failure])
        await s.run_once(lease, a)
        assert await state(sessions, lease) == ("failed", "OUTCOME_UNKNOWN") and len(a.calls) == 1
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(FreeCourseCapacity).where(
                        FreeCourseCapacity.operation_id == lease.fence.operation_id
                    )
                )
            ).state == "quarantined"
            events = (
                await db.scalars(
                    select(FreeCourseEvent).where(
                        FreeCourseEvent.operation_id == lease.fence.operation_id
                    )
                )
            ).all()
            assert "synthetic secret" not in json.dumps([e.payload for e in events])

    exercise(action)


def test_dispatch_duplicate_never_sends_twice():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter()
        aid = await s.prepare(lease, a)
        await asyncio.gather(s.deliver(lease, aid, a), s.deliver(lease, aid, a))
        assert len(a.calls) == 1
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseDispatch)
                    .where(FreeCourseDispatch.attempt_id == aid)
                )
                == 1
            )

    exercise(action)


@pytest.mark.parametrize("retry_after", [None, "0", "3"])
def test_verified_transport_retry_with_persisted_backoff(retry_after):
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter([Reply("not_executed", PROOF, status=503, retry_after=retry_after)])
        await s.run_once(lease, a)
        async with sessions() as db:
            step = await db.scalar(
                select(FreeCourseStep).where(
                    FreeCourseStep.operation_id == lease.fence.operation_id
                )
            )
            assert step.retry_purpose == "transport_retry" and step.next_attempt_at
        await s.run_once(lease, a)
        assert len(a.calls) == 1
        async with sessions() as db, db.begin():
            await db.execute(
                text(
                    "UPDATE free_course_steps SET next_attempt_at=clock_timestamp()-"
                    "interval '1 second' WHERE operation_id=:id"
                ),
                {"id": lease.fence.operation_id},
            )
        await s.run_once(lease, a)
        assert len(a.calls) == 2
        async with sessions() as db:
            b = await s.budget(db, lease.course, lease.fence.operation_id)
            assert (
                b["operation_attempts"] == 2
                and b["transport_retry"] == 1
                and b["operation_input"] == 100
            )

    exercise(action)


@pytest.mark.parametrize("retry_after", ["31", "Wed, 21 Oct 2026 07:28:00 GMT", "-1", "1.5", ""])
def test_invalid_retry_after_stops(retry_after):
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter([Reply("stopped", PROOF, status=429, retry_after=retry_after)])
        await s.run_once(lease, a)
        assert await state(sessions, lease) == ("failed", "PROVIDER_REJECTED")
        assert len(a.calls) == 1

    exercise(action)


def test_format_repair_is_bounded_and_preserves_original_requirement():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter([Reply("complete_response", PROOF, {}, 100, 100)])
        await s.run_once(lease, a)
        await s.run_once(lease, a)
        assert len(a.calls) == 2 and len(a.calls[1].prompt.messages) == 3
        assert GOAL in a.calls[1].prompt.messages[1].content
        assert "SCHEMA_INVALID" in a.calls[1].prompt.messages[-1].content
        async with sessions() as db:
            b = await s.budget(db, lease.course, lease.fence.operation_id)
            assert b["format_repair"] == 1

    exercise(action)


def test_second_invalid_format_stops_no_loop():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter(
            [Reply("complete_response", PROOF, {}), Reply("complete_response", PROOF, {})]
        )
        await s.run_once(lease, a)
        await s.run_once(lease, a)
        assert await state(sessions, lease) == ("failed", "SCHEMA_INVALID") and len(a.calls) == 2

    exercise(action)


@pytest.mark.parametrize("status", [401, 403])
def test_hard_provider_failure_stops_without_format_repair(status):
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter([Reply("not_executed", PROOF, status=status)])
        await s.run_once(lease, a)
        assert await state(sessions, lease) == ("failed", "PROVIDER_REJECTED")
        async with sessions() as db:
            assert (await s.budget(db, lease.course, lease.fence.operation_id))[
                "format_repair"
            ] == 0

    exercise(action)


def test_unknown_usage_keeps_full_reservation_and_package_exhaustion_persists():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter([Reply("complete_response", PROOF, candidate(1, GOAL))])
        a.policy = replace(a.policy, requests=1)
        await s.run_once(lease, a)
        await s.run_once(lease, a)
        assert await state(sessions, lease) == ("failed", "BUDGET_EXHAUSTED") and len(a.calls) == 1
        async with sessions() as db:
            b = await s.budget(db, lease.course, lease.fence.operation_id)
            assert (
                b["operation_attempts"] == 1
                and b["operation_input"] == 1000
                and b["operation_output"] == 8000
            )

    exercise(action)


def test_package_fee_is_shared_across_owners_and_not_reset_by_new_course():
    async def action(s, sessions, owners):
        a = FakeAdapter(
            policy=SendPolicy(
                package_id=str(uuid4()),
                requests=10,
                fee_micros=9000,
                input_micros_per_token=1,
                output_micros_per_token=1,
                bounded_output_verified=True,
            )
        )
        first = await setup(s, owners[0])
        await s.run_once(first, a)
        second = await setup(s, owners[1])
        await s.run_once(second, a)
        assert await state(sessions, second) == ("failed", "BUDGET_EXHAUSTED") and len(a.calls) == 1

    exercise(action)


def test_default_zero_authorization_and_unbounded_input_refuse_before_send():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter(policy=SendPolicy())
        with pytest.raises(SnapshotError, match="EXECUTION_NOT_AUTHORIZED"):
            await s.run_once(lease, a)
        a = FakeAdapter()
        a.input_upper_bound = lambda request: 32001
        await s.run_once(lease, a)
        assert await state(sessions, lease) == ("failed", "BUDGET_EXHAUSTED") and not a.calls

    exercise(action)


def test_response_crash_reclaim_does_not_relabel_old_epoch_or_resend():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter()
        aid = await s.prepare(lease, a)
        await s.settle(aid, Reply("complete_response", PROOF, candidate(1, GOAL), 100, 100))
        await expire(sessions, lease)
        await s.reconcile()
        fresh = await s.claim()
        await s.run_once(fresh, a)
        assert await state(sessions, fresh) == ("failed", "LEASE_LOST") and not a.calls
        async with sessions() as db:
            assert (await s.budget(db, lease.course, lease.fence.operation_id))[
                "operation_attempts"
            ] == 1

    exercise(action)


def test_late_response_can_settle_but_not_publish_or_continue():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter()
        aid = await s.prepare(lease, a)
        await expire(sessions, lease)
        await s.reconcile()
        reply = Reply("complete_response", PROOF, candidate(1, GOAL), 100, 200)
        await s.settle(aid, reply)
        await s.settle(aid, reply)
        with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
            await s.consume(lease, aid)
        with pytest.raises(SnapshotError, match="SETTLEMENT_CONFLICT"):
            await s.settle(aid, replace(reply, output_tokens=201))
        async with sessions() as db:
            assert (await SnapshotRepository(db, lease.owner).get_course(lease.course))[
                "head_version"
            ] is None
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseSettlement)
                    .where(FreeCourseSettlement.attempt_id == aid)
                )
                == 1
            )

    exercise(action)


def test_heartbeat_keeps_deadline_and_wrong_owner_cannot_reserve():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        await s.heartbeat(lease)
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await s.prepare(Lease(owners[1], lease.course, lease.fence), FakeAdapter())
        async with sessions() as db:
            op = await db.get(FreeCourseOperation, lease.fence.operation_id)
            assert op.lease_expires_at <= op.deadline_at

    exercise(action)


def test_reservation_audit_immutable_and_nonempty_downgrade_refused():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        aid = await s.prepare(lease, FakeAdapter())
        async with sessions() as db:
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(
                        text("UPDATE free_course_attempts SET input_tokens=1 WHERE id=:id"),
                        {"id": aid},
                    )
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "downgrade", "0040_free_scene_availability"],
            cwd=ROOT / "backend",
            env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode != 0 and "scheduler audit prevents downgrade" in result.stderr

    exercise(action)


def test_policy_is_exact_approved_copy():
    assert POLICY == json.loads(
        (ROOT / "docs/acceptance/phase-1.5-generation-contract-r01/policy.json").read_text()
    )


def test_all_thirteen_attempts_use_the_two_shared_retry_pools():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])

        def ok(value):
            return Reply("complete_response", PROOF, value, 100, 200)

        a = FakeAdapter(
            [
                ok({}),
                ok(candidate(8, GOAL)),
                Reply("not_executed", PROOF, status=503),
                ok(response(["text"])),
                ok({}),
                ok(response(["text"])),
                Reply("not_executed", PROOF, status=429),
                ok(response(["text"])),
            ],
            n=8,
        )
        for _ in range(14):
            if (await state(sessions, lease))[0] != "running":
                break
            async with sessions() as db, db.begin():
                await db.execute(
                    text(
                        "UPDATE free_course_steps SET next_attempt_at=clock_timestamp() "
                        "WHERE operation_id=:oid AND next_attempt_at IS NOT NULL"
                    ),
                    {"oid": lease.fence.operation_id},
                )
            await s.run_once(lease, a)
        assert await state(sessions, lease) == ("succeeded", None)
        assert len(a.calls) == 13
        async with sessions() as db:
            b = await s.budget(db, lease.course, lease.fence.operation_id)
            assert b["operation_attempts"] == 13 and b["format_repair"] == b["transport_retry"] == 2
            assert (await read_availability(db, lease.owner, lease.course, version=9))[
                "ready_count"
            ] == 8

    exercise(action)


def test_local_failure_propagates_dependencies_but_independent_scene_continues():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        planned = candidate(4, GOAL)
        planned["plan"]["scenes"][3]["depends_on"] = []

        def ok(value):
            return Reply("complete_response", PROOF, value, 100, 100)

        a = FakeAdapter(
            [ok(planned), ok(response(["text"])), ok({}), ok({}), ok(response(["text"]))]
        )
        for _ in range(6):
            await s.run_once(lease, a)
        assert await state(sessions, lease) == ("partially_succeeded", "DEPENDENCY_UNAVAILABLE")
        assert len(a.calls) == 5
        async with sessions() as db:
            v = await read_availability(db, lease.owner, lease.course, version=3)
            assert [i["generation_state"] for i in v["scenes"]] == [
                "ready",
                "failed",
                "blocked_dependency",
                "ready",
            ]
            assert v["ready_count"] == 2

    exercise(action)


def test_course_lifetime_forty_sent_reservations_survive_new_operation():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        # Construct 40 historical sent facts through the same DB schema. Each operation has a
        # single planning step and terminates; new operation does not reset course aggregates.
        async with sessions() as db, db.begin():
            current = await db.get(FreeCourseOperation, lease.fence.operation_id)
            current.state = "failed"
            for i in range(40):
                op = FreeCourseOperation(
                    user_id=lease.owner,
                    course_id=lease.course,
                    request_id=current.request_id,
                    kind="resume",
                    state="running",
                    lease_epoch=1,
                    config_snapshot={},
                    policy_snapshot=POLICY,
                )
                db.add(op)
                await db.flush()
                step = FreeCourseStep(
                    user_id=lease.owner,
                    course_id=lease.course,
                    operation_id=op.id,
                    step_key="plan",
                    state="running",
                )
                db.add(step)
                await db.flush()
                attempt = FreeCourseAttempt(
                    user_id=lease.owner,
                    course_id=lease.course,
                    operation_id=op.id,
                    step_id=step.id,
                    purpose="primary",
                    lease_epoch=1,
                    input_tokens=1,
                    output_tokens=1,
                    fee_micros=0,
                    sent_at=func.clock_timestamp(),
                    request_digest=PROOF,
                    input_snapshot={},
                    request_json={},
                )
                db.add(attempt)
                await db.flush()
                db.add(
                    FreeCourseSettlement(
                        user_id=lease.owner,
                        course_id=lease.course,
                        attempt_id=attempt.id,
                        evidence="not_executed",
                        evidence_digest=PROOF,
                        input_tokens=0,
                        output_tokens=0,
                        outcome_json={},
                    )
                )
                op.state = "failed"
                await db.flush()
            current.state = "running"
        a = FakeAdapter()
        await s.run_once(lease, a)
        assert await state(sessions, lease) == ("failed", "BUDGET_EXHAUSTED") and not a.calls
        async with sessions() as db:
            b = await s.budget(db, lease.course, lease.fence.operation_id)
            assert b["course_attempts"] == 40 and b["operation_attempts"] == 0

    exercise(action)


def test_attempt_and_event_failure_roll_back_entire_reservation(monkeypatch):
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter()
        await s.run_once(lease, a)  # scene_started will be emitted for next reservation
        before = len(a.calls)
        original = s._event

        async def broken(db, lease, kind, payload):
            if kind == "scene_started":
                raise RuntimeError("injected event failure")
            return await original(db, lease, kind, payload)

        monkeypatch.setattr(s, "_event", broken)
        with pytest.raises(RuntimeError, match="injected"):
            await s.prepare(lease, a)
        async with sessions() as db:
            b = await s.budget(db, lease.course, lease.fence.operation_id)
            assert b["operation_attempts"] == 1
            slot = await db.scalar(
                select(FreeCourseCapacity).where(
                    FreeCourseCapacity.operation_id == lease.fence.operation_id
                )
            )
            assert slot.pending_attempt_id is None
        assert len(a.calls) == before

    exercise(action)


def test_package_binding_cannot_switch_between_reservation_and_send():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter()
        aid = await s.prepare(lease, a)
        a.policy = replace(a.policy, package_id="different")
        with pytest.raises(SnapshotError, match="EXECUTION_PACKAGE_CHANGED"):
            await s.deliver(lease, aid, a)
        assert not a.calls

    exercise(action)


def test_duplicate_run_delivery_during_live_send_is_noop():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter()
        entered, finish = asyncio.Event(), asyncio.Event()

        async def slow(request):
            entered.set()
            await finish.wait()

        a.observe = slow
        first = asyncio.create_task(s.run_once(lease, a))
        await asyncio.wait_for(entered.wait(), timeout=5)
        try:
            await s.run_once(lease, a)
            assert await state(sessions, lease) == ("running", None)
            assert len(a.calls) == 1
        finally:
            finish.set()
            await first
        async with sessions() as db:
            assert (await SnapshotRepository(db, lease.owner).get_course(lease.course))[
                "head_version"
            ] == 1

    exercise(action)


def test_budget_exhaustion_retains_already_learnable_scene():
    async def action(s, sessions, owners):
        lease = await setup(s, owners[0])
        a = FakeAdapter()
        a.policy = replace(a.policy, requests=2)
        await s.run_once(lease, a)
        await s.run_once(lease, a)
        await s.run_once(lease, a)
        assert await state(sessions, lease) == ("failed", "BUDGET_EXHAUSTED")
        async with sessions() as db:
            v = await read_availability(db, lease.owner, lease.course, version=2)
            assert v["ready_count"] == 1
            assert v["scenes"][0]["content_state"] == "ready"
        assert len(a.calls) == 2

    exercise(action)


def test_timeout_after_persisted_deadline_quarantines_immediately():
    async def action(s, sessions, owners):
        constructor = FreeCourseOperation.__init__

        def short_operation(self, **kwargs):
            constructor(
                self,
                **{**kwargs, "deadline_at": func.clock_timestamp() + text("interval '0.2 second'")},
            )

        with patch.object(FreeCourseOperation, "__init__", short_operation):
            lease = await setup(s, owners[0])
        a = FakeAdapter()

        async def slow(request):
            await asyncio.sleep(1)

        a.observe = slow
        await s.run_once(lease, a)
        assert await state(sessions, lease) == ("failed", "OUTCOME_UNKNOWN")
        async with sessions() as db:
            cap = await db.scalar(
                select(FreeCourseCapacity).where(
                    FreeCourseCapacity.operation_id == lease.fence.operation_id
                )
            )
            assert cap.state == "quarantined"
            assert (await s.budget(db, lease.course, lease.fence.operation_id))[
                "operation_attempts"
            ] == 1

    exercise(action)


def test_legacy_empty_policy_create_receipt_digest_remains_compatible():
    async def action(s, sessions, owners):
        async with sessions() as db:
            repo = SnapshotRepository(db, owners[0])
            original = await repo.create_course(GOAL, key="legacy")
            await db.commit()
            receipt = await db.scalar(
                select(FreeCourseReceipt).where(
                    FreeCourseReceipt.user_id == owners[0],
                    FreeCourseReceipt.idempotency_key == "legacy",
                )
            )
            assert receipt.request_digest == digest(
                "create",
                goal=GOAL,
                teaching_language="zh-CN",
                code_language="C",
                profile_id=None,
                config={},
            )
            assert await repo.create_course(GOAL, key="legacy") == original

    exercise(action)
