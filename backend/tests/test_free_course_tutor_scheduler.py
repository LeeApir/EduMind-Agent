"""Shared PG slots/dispatch and bounded single-Tutor calls, synthetic transport only."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from test_free_course_revision import setup
from test_free_course_tutor_context import exercise, request
from test_free_course_tutor_context import migrate_database as migrate_database  # noqa: F401

from app.models.free_course_progress import FreeCourseEvent
from app.models.free_course_scheduler import (
    FreeCourseAttempt,
    FreeCourseCapacity,
    FreeCourseDispatch,
)
from app.services.free_course_scheduler import Reply, SendPolicy
from app.services.free_course_snapshots import SnapshotError
from app.services.free_course_tutor_scheduler import TutorRecovery, TutorScheduler

PROOF = "b" * 64


def value():
    return dict(
        turn_version="classroom-turn-v1",
        utterances=[
            dict(role="tutor", text="先连接旧链表，再更新头指针。这是补充解释，不代表签核。")
        ],
    )


class FakeTutor:
    def __init__(self, reply=None):
        self.policy = SendPolicy(
            package_id="TEST_ONLY_TUTOR_" + uuid4().hex,
            requests=100,
            fee_micros=0,
            input_limit=16000,
            output_limit=2000,
            bounded_output_verified=True,
        )
        self.reply = reply or Reply("complete_response", PROOF, value(), 100, 100)
        self.calls = []
        self.observe = None
        self.bound = 1000

    def input_upper_bound(self, request):
        return self.bound

    async def send(self, request, *, retry_safe):
        assert retry_safe is False
        self.calls.append(request)
        if self.observe:
            await self.observe()
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_one_turn_shared_pool_and_existing_single_tutor_request():
    async def action(gen, turns, sessions, owner, other):
        cid, manifest, _ = await setup(gen, sessions, owner, n=2)
        receipt = await turns.enqueue(owner, cid, request(manifest), key="tutor")
        s = TutorScheduler(sessions)
        adapter = FakeTutor()
        lease = await s.claim()
        assert lease is not None
        await s.run_once(lease, adapter)
        result = await TutorRecovery(sessions).read_operation(
            owner, cid, UUID(receipt["operation_id"])
        )
        assert result["state"] == "succeeded" and result["steps"][0]["state"] == "ready"
        assert (
            result["budget"]["attempts_used"] == 1 and result["budget"]["attempts_remaining"] == 0
        )
        assert result["budget"]["course_attempts_remaining"] == 36
        assert len(adapter.calls) == 1 and adapter.calls[0].prompt.max_output_tokens == 2000
        prompt = adapter.calls[0].prompt.messages[0].content
        assert "free-course-tutor-v1" in prompt and "未签核" in prompt
        assert '"answer_key"' not in adapter.calls[0].prompt.messages[1].content
        ready = await turns.read(owner, cid, UUID(receipt["turn_id"]))
        assert ready["status"] == "ready" and ready["anchor_refs"] == []
        async with sessions() as db:
            events = (
                await db.scalars(
                    select(FreeCourseEvent)
                    .where(FreeCourseEvent.operation_id == lease.fence.operation_id)
                    .order_by(FreeCourseEvent.seq)
                )
            ).all()
            assert [e.event_type for e in events] == ["queued", "started", "tutor_ready", "done"]
            assert "补充解释" not in str([e.payload for e in events])
            assert await db.scalar(select(func.count()).select_from(FreeCourseDispatch)) == 4

    exercise(action)


@pytest.mark.parametrize("kind", ["not_executed", "invalid", "unknown"])
def test_failure_never_repairs_or_retries(kind):
    async def action(gen, turns, sessions, owner, other):
        cid, manifest, _ = await setup(gen, sessions, owner, n=2)
        receipt = await turns.enqueue(owner, cid, request(manifest), key="tutor")
        reply = {
            "not_executed": Reply("not_executed", PROOF, None, status=503),
            "invalid": Reply("complete_response", PROOF, {"bad": "format"}, 100, 100),
            "unknown": RuntimeError("untrusted secret must not escape"),
        }[kind]
        s = TutorScheduler(sessions)
        adapter = FakeTutor(reply)
        lease = await s.claim()
        await s.run_once(lease, adapter)
        assert len(adapter.calls) == 1 and await s.claim() is None
        result = await turns.read(owner, cid, UUID(receipt["turn_id"]))
        assert result["status"] == "failed" and result["markdown"] is None
        assert "secret" not in str(result)
        async with sessions() as db:
            rows = (
                await db.scalars(
                    select(FreeCourseAttempt).where(
                        FreeCourseAttempt.operation_id == lease.fence.operation_id
                    )
                )
            ).all()
            assert len(rows) == 1 and rows[0].purpose == "primary"
            if kind == "unknown":
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(FreeCourseCapacity)
                        .where(FreeCourseCapacity.state == "quarantined")
                    )
                    == 1
                )

    exercise(action)


def test_duplicate_delivery_and_crash_after_reservation_never_resends():
    async def action(gen, turns, sessions, owner, other):
        cid, manifest, _ = await setup(gen, sessions, owner, n=2)
        receipt = await turns.enqueue(owner, cid, request(manifest), key="tutor")
        s = TutorScheduler(sessions)
        adapter = FakeTutor()
        lease = await s.claim()
        aid = await s.prepare(lease, adapter)
        await s.run_once(lease, adapter)
        assert not adapter.calls
        async with sessions() as db, db.begin():
            await db.execute(
                text(
                    "UPDATE free_course_operations SET lease_expires_at=clock_timestamp()"
                    "-interval '1 second' WHERE id=:o"
                ),
                {"o": lease.fence.operation_id},
            )
        await s.reconcile()
        assert await s.claim() is None
        assert (await turns.read(owner, cid, UUID(receipt["turn_id"])))["status"] == "failed"
        await s.settle(aid, Reply("complete_response", PROOF, value(), 100, 100))
        assert (await turns.read(owner, cid, UUID(receipt["turn_id"])))["markdown"] is None
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseCapacity)
                    .where(FreeCourseCapacity.state == "quarantined")
                )
                == 0
            )

    exercise(action)


def test_inflight_cancel_replay_and_late_response_only_settles():
    async def action(gen, turns, sessions, owner, other):
        cid, manifest, _ = await setup(gen, sessions, owner, n=2)
        receipt = await turns.enqueue(owner, cid, request(manifest), key="tutor")
        s = TutorScheduler(sessions)
        recovery = TutorRecovery(sessions)
        adapter = FakeTutor()
        lease = await s.claim()
        replies = []

        async def cancel():
            replies.append(
                await recovery.cancel(owner, cid, lease.fence.operation_id, key="cancel")
            )
            await s.reconcile()

        adapter.observe = cancel
        with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
            await s.run_once(lease, adapter)
        assert replies[0]["state"] == "cancel_requested"
        assert (
            await recovery.cancel(owner, cid, lease.fence.operation_id, key="cancel") == replies[0]
        )
        result = await turns.read(owner, cid, UUID(receipt["turn_id"]))
        assert result["status"] == "cancelled" and result["markdown"] is None
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseCapacity)
                    .where(FreeCourseCapacity.state != "free")
                )
                == 0
            )

    exercise(action)


def test_two_global_slots_are_shared_with_generation_and_queued_deadline():
    async def action(gen, turns, sessions, owner, other):
        cid, manifest, _ = await setup(gen, sessions, owner, n=2)
        receipt = await turns.enqueue(owner, cid, request(manifest), key="tutor")
        await gen.enqueue(other, "另一个合成学习目标", key="other")
        generation = await gen.claim()
        mentor = await TutorScheduler(sessions).claim()
        assert generation is not None and mentor is not None
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseCapacity)
                    .where(FreeCourseCapacity.state == "held")
                )
                == 2
            )
        recovery = TutorRecovery(sessions)
        await recovery.cancel(owner, cid, UUID(receipt["operation_id"]), key="cancel")
        await recovery.scheduler.reconcile()

    exercise(action)


def test_zero_authorization_input_ceiling_and_shared_package_cap():
    async def action(gen, turns, sessions, owner, other):
        cid, manifest, old_adapter = await setup(gen, sessions, owner, n=2)
        receipt = await turns.enqueue(owner, cid, request(manifest), key="tutor")
        s = TutorScheduler(sessions)
        adapter = FakeTutor()
        lease = await s.claim()
        adapter.policy = replace(adapter.policy, requests=0)
        with pytest.raises(SnapshotError, match="EXECUTION_NOT_AUTHORIZED"):
            await s.prepare(lease, adapter)
        adapter.policy = replace(
            adapter.policy, requests=100, package_id=old_adapter.policy.package_id
        )
        async with sessions() as db:
            sent = await db.scalar(
                select(func.count())
                .select_from(FreeCourseAttempt)
                .where(
                    FreeCourseAttempt.request_json["package_id"].astext
                    == old_adapter.policy.package_id
                )
            )
        adapter.policy = replace(adapter.policy, requests=sent)
        assert await s.prepare(lease, adapter) is None and not adapter.calls
        assert (await turns.read(owner, cid, UUID(receipt["turn_id"])))["status"] == "failed"
        second = await turns.enqueue(owner, cid, request(manifest), key="second")
        lease = await s.claim()
        adapter = FakeTutor()
        adapter.bound = 16001
        assert await s.prepare(lease, adapter) is None
        assert (await turns.read(owner, cid, UUID(second["turn_id"])))["status"] == "failed"

    exercise(action)


def test_course_forty_reservations_include_prior_generation_and_tutor_turns():
    async def action(gen, turns, sessions, owner, other):
        cid, manifest, _ = await setup(gen, sessions, owner, n=2)
        s = TutorScheduler(sessions)
        adapter = FakeTutor()
        async with sessions() as db:
            previous = await db.scalar(
                select(func.count())
                .select_from(FreeCourseAttempt)
                .where(FreeCourseAttempt.course_id == cid)
            )
        for i in range(40 - previous):
            await turns.enqueue(owner, cid, request(manifest), key=f"call-{i}")
            lease = await s.claim()
            await s.run_once(lease, adapter)
        assert len(adapter.calls) == 40 - previous
        receipt = await turns.enqueue(owner, cid, request(manifest), key="exhausted")
        lease = await s.claim()
        await s.run_once(lease, adapter)
        assert len(adapter.calls) == 40 - previous
        result = await TutorRecovery(sessions).read_operation(
            owner, cid, UUID(receipt["operation_id"])
        )
        assert (
            result["reason_code"] == "BUDGET_EXHAUSTED"
            and result["budget"]["course_attempts_remaining"] == 0
        )

    exercise(action)


def test_tutor_ready_step_requires_actual_dispatch_settlement_and_reply():
    from sqlalchemy.exc import DBAPIError

    async def action(gen, turns, sessions, owner, other):
        cid, manifest, _ = await setup(gen, sessions, owner, n=2)
        receipt = await turns.enqueue(owner, cid, request(manifest), key="tutor")
        s = TutorScheduler(sessions)
        lease = await s.claim()
        assert lease
        with pytest.raises(DBAPIError, match="ready tutor requires exact"):
            async with sessions() as db, db.begin():
                await db.execute(
                    text("UPDATE free_course_steps SET state='ready' WHERE operation_id=:o"),
                    {"o": UUID(receipt["operation_id"])},
                )

    exercise(action)


def test_queued_deadline_and_predispatch_source_failure_never_send(monkeypatch):
    from unittest.mock import patch

    import app.services.free_course_tutor_scheduler as tutor_module
    from app.models.free_course_scheduler import FreeCourseSettlement
    from app.models.free_course_writes import FreeCourseOperation

    async def action(gen, turns, sessions, owner, other):
        cid, manifest, _ = await setup(gen, sessions, owner, n=2)
        constructor = FreeCourseOperation.__init__

        def expired_operation(self, **kwargs):
            constructor(
                self,
                **{**kwargs, "deadline_at": func.clock_timestamp() - text("interval '1 second'")},
            )

        with patch.object(FreeCourseOperation, "__init__", expired_operation):
            receipt = await turns.enqueue(owner, cid, request(manifest), key="expired")
        s = TutorScheduler(sessions)
        await s.reconcile()
        assert (await turns.read(owner, cid, UUID(receipt["turn_id"])))["status"] == "timed_out"
        receipt = await turns.enqueue(owner, cid, request(manifest), key="sources")
        lease = await s.claim()
        adapter = FakeTutor()
        aid = await s.prepare(lease, adapter)

        async def reject(*args):
            return False

        monkeypatch.setattr(tutor_module, "check_sources", reject)
        await s.deliver(lease, aid, adapter)
        assert not adapter.calls
        async with sessions() as db:
            settled = await db.scalar(
                select(FreeCourseSettlement).where(FreeCourseSettlement.attempt_id == aid)
            )
            assert settled.evidence == "not_executed" and settled.input_tokens == 0
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseDispatch)
                    .where(FreeCourseDispatch.attempt_id == aid)
                )
                == 0
            )
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseCapacity)
                    .where(FreeCourseCapacity.state != "free")
                )
                == 0
            )
        assert (await turns.read(owner, cid, UUID(receipt["turn_id"])))["status"] == "failed"

    exercise(action)
