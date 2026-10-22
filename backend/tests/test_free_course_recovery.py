"""Actual isolated PG cancellation, explicit new operations and pure recovery reads."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_free_course_planning import candidate
from test_free_course_scheduler import GOAL, PROOF, FakeAdapter
from test_free_scene_availability import make_validation
from test_free_scene_generation import response

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course import FreeCourseRequest
from app.models.free_course_progress import FreeCourseEvent
from app.models.free_course_recovery import FreeCourseOperationSource
from app.models.free_course_scheduler import FreeCourseCapacity
from app.models.free_course_writes import FreeCourseOperation, FreeCourseReceipt
from app.services import free_scene_availability as visibility
from app.services.free_course_recovery import Recovery
from app.services.free_course_scheduler import Reply, Scheduler
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository

ROOT = Path(__file__).resolve().parents[2]


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value, "Actual isolated PG required, no skip"
    url = make_url(value)
    assert url.host == "127.0.0.1" and url.port == 15437
    assert (url.database or "").startswith("edumind_catalog_p15_t015_")
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


def exercise(action):
    async def run():
        engine = create_database_engine(database_url())
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        owners = [uuid4(), uuid4()]
        try:
            async with sessions() as db:
                db.add_all([User(id=u, is_guest=True) for u in owners])
                await db.commit()
            await action(Recovery(sessions), Scheduler(sessions), sessions, *owners)
        finally:
            async with engine.begin() as conn:
                # Synthetic transport is finished; test cleanup has no real remote operation.
                await conn.execute(
                    text(
                        "UPDATE free_course_capacity SET state='free',user_id=NULL,course_id=NULL,"
                        "operation_id=NULL,epoch=NULL,expires_at=NULL,pending_attempt_id=NULL"
                    )
                )
                for owner in owners:
                    await conn.execute(text("DELETE FROM users WHERE id=:id"), {"id": owner})
            await engine.dispose()

    asyncio.run(run())


async def queued(s, owner):
    result = await s.enqueue(owner, GOAL, key="create")
    return UUID(result["course_id"]), UUID(result["operation_id"])


async def running(s, owner):
    cid, oid = await queued(s, owner)
    lease = await s.claim()
    assert lease.owner == owner and lease.course == cid and lease.fence.operation_id == oid
    return lease


async def resume(r, lease, head, *, key="resume"):
    return await r.start(
        lease.owner,
        lease.course,
        kind="resume",
        source_operation_id=lease.fence.operation_id,
        expected_head=head,
        key=key,
    )


async def stop(r, s, lease):
    await r.cancel(lease.owner, lease.course, lease.fence.operation_id, key="cancel")
    assert await s.reconcile() == 1


async def snapshot(sessions, cid):
    async with sessions() as db:
        result = {}
        for table in [
            "free_course_operations",
            "free_course_steps",
            "free_course_events",
            "free_course_attempts",
            "free_course_receipts",
            "free_course_versions",
        ]:
            result[table] = (
                (
                    await db.execute(
                        text(
                            f"SELECT to_jsonb(t) FROM {table} t WHERE course_id=:id "
                            "ORDER BY to_jsonb(t)::text"
                        ),
                        {"id": cid},
                    )
                )
                .scalars()
                .all()
            )
        return result


def test_queued_cancel_immediate_fence_then_durable_sweep_and_original_receipt():
    async def action(r, s, sessions, owner, other):
        cid, oid = await queued(s, owner)
        ack = await r.cancel(owner, cid, oid, key="stop")
        assert ack["state"] == "cancel_requested" and await s.claim() is None
        assert (await r.read_operation(owner, cid, oid))["steps"][0]["state"] == "cancelled"
        assert await Scheduler(sessions).reconcile() == 1
        assert await Scheduler(sessions).reconcile() == 0
        final = await r.read_operation(owner, cid, oid)
        assert final["state"] == "cancelled" and final["budget"]["attempts_used"] == 0
        assert await r.cancel(owner, cid, oid, key="stop") == ack
        before = await snapshot(sessions, cid)
        assert (await r.cancel(owner, cid, oid, key="after"))["state"] == "cancelled"
        after = await snapshot(sessions, cid)
        for table in before:
            if table != "free_course_receipts":
                assert before[table] == after[table]
        async with sessions() as db:
            receipt = await db.scalar(
                select(FreeCourseReceipt).where(
                    FreeCourseReceipt.user_id == owner, FreeCourseReceipt.idempotency_key == "stop"
                )
            )
            assert receipt.status_code == 200

    exercise(action)


def test_resume_keeps_ready_identity_and_only_sends_missing_scenes():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter(n=3)
        await s.run_once(lease, a)
        await s.run_once(lease, a)
        async with sessions() as db:
            before = await SnapshotRepository(db, owner).get_version(lease.course, 2)
        await stop(r, s, lease)
        new = await resume(r, lease, 2)
        op = await r.read_operation(owner, lease.course, UUID(new["operation_id"]))
        assert len(op["steps"]) == 2 and op["budget"]["attempts_used"] == 0
        assert op["budget"]["course_attempts_remaining"] == 38
        assert op["base_head_version"] == op["head_version"] == 2
        assert (await r.read_operation(owner, lease.course, lease.fence.operation_id))[
            "state"
        ] == "cancelled"
        fresh = await Scheduler(sessions).claim()
        await s.run_once(fresh, a)
        await s.run_once(fresh, a)
        await s.run_once(fresh, a)
        assert len(a.calls) == 4
        assert (await r.read_operation(owner, lease.course, fresh.fence.operation_id))[
            "state"
        ] == "succeeded"
        async with sessions() as db:
            end = await SnapshotRepository(db, owner).get_version(lease.course, 4)
            assert before["plan_id"] == end["plan_id"]
            assert before["scenes"][0] == end["scenes"][0]
            assert (await visibility.read_availability(db, owner, lease.course, version=4))[
                "all_scenes_ready"
            ]
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseEvent)
                    .where(
                        FreeCourseEvent.course_id == lease.course,
                        FreeCourseEvent.event_type == "first_scene_ready",
                    )
                )
                == 1
            )
            row = await db.scalar(
                select(FreeCourseOperationSource).where(
                    FreeCourseOperationSource.operation_id == fresh.fence.operation_id
                )
            )
            assert row.source_operation_id == lease.fence.operation_id
        assert await resume(r, lease, 2) == new  # Replay even after head and operation changed.
        with pytest.raises(SnapshotError, match="STALE_COURSE_VERSION"):
            await resume(r, lease, 2, key="old-head")

    exercise(action)


def test_resume_after_no_head_is_new_planning_not_old_attempt_replay():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        await stop(r, s, lease)
        new = await resume(r, lease, None)
        fresh = await s.claim()
        a = FakeAdapter(n=1)
        assert fresh.fence.operation_id == UUID(new["operation_id"])
        await s.run_once(fresh, a)
        await s.run_once(fresh, a)
        await s.run_once(fresh, a)
        assert len(a.calls) == 2
        old = await r.read_operation(owner, lease.course, lease.fence.operation_id)
        assert old["state"] == "cancelled" and old["budget"]["attempts_used"] == 0

    exercise(action)


def test_duplicate_resume_is_atomic_and_changed_body_conflicts():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        await stop(r, s, lease)
        rows = await asyncio.gather(resume(r, lease, None), resume(r, lease, None))
        assert rows[0] == rows[1]
        with pytest.raises(SnapshotError, match="OPERATION_ACTIVE"):
            await resume(r, lease, None, key="different")
        with pytest.raises(SnapshotError, match="IDEMPOTENCY_CONFLICT"):
            await resume(r, lease, 1)
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseOperation)
                    .where(FreeCourseOperation.course_id == lease.course)
                )
                == 2
            )
            receipt = await db.scalar(
                select(FreeCourseReceipt).where(
                    FreeCourseReceipt.user_id == owner,
                    FreeCourseReceipt.idempotency_key == "resume",
                )
            )
            assert receipt.status_code == 202

    exercise(action)


def test_nothing_to_resume_after_full_success_and_terminal_cancel_has_no_event_effect():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter(n=1)
        for _ in range(3):
            await s.run_once(lease, a)
        with pytest.raises(SnapshotError, match="NOTHING_TO_RESUME"):
            await resume(r, lease, 2)
        old = await r.read_operation(owner, lease.course, lease.fence.operation_id)
        ack = await r.cancel(owner, lease.course, lease.fence.operation_id, key="done")
        assert ack["state"] == "succeeded"
        assert await r.read_operation(owner, lease.course, lease.fence.operation_id) == old

    exercise(action)


def test_resume_rejects_nonterminal_stale_source_wrong_owner_and_missing_baseline():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        with pytest.raises(SnapshotError, match="OPERATION_ACTIVE"):
            await resume(r, lease, None)
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await r.start(
                other,
                lease.course,
                kind="resume",
                source_operation_id=lease.fence.operation_id,
                expected_head=None,
                key="foreign",
            )
        with pytest.raises(TypeError):
            await r.start(
                owner,
                lease.course,
                kind="resume",
                source_operation_id=lease.fence.operation_id,
                key="missing",
            )
        await stop(r, s, lease)
        new = await resume(r, lease, None)
        await r.cancel(owner, lease.course, UUID(new["operation_id"]), key="second-stop")
        await s.reconcile()
        with pytest.raises(SnapshotError, match="STALE_SOURCE_OPERATION"):
            await resume(r, lease, None, key="ancestor")

    exercise(action)


@pytest.mark.parametrize("head", [True, 0, -1, "1"])
def test_baseline_type_does_not_silently_resolve_latest(head):
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        await stop(r, s, lease)
        with pytest.raises(SnapshotError, match="STALE_COURSE_VERSION"):
            await resume(r, lease, head)

    exercise(action)


def test_cancel_wins_before_scene_commit_fences_and_keeps_empty_head():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter()
        await s.run_once(lease, a)
        async with sessions() as db:
            manifest = await SnapshotRepository(db, owner).get_version(lease.course, 1)
            vid = await make_validation(
                db,
                owner,
                lease.course,
                lease.fence,
                UUID(manifest["plan_id"]),
                UUID(manifest["scenes"][0]["scene_id"]),
                1,
                raw=response(["text"]),
            )
        await r.cancel(owner, lease.course, lease.fence.operation_id, key="race")
        async with sessions() as db:
            with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
                await visibility.commit_scene(
                    db,
                    owner,
                    lease.course,
                    lease.fence,
                    validation_id=vid,
                    expected_head=1,
                    key="late",
                )
        await s.reconcile()
        async with sessions() as db:
            assert (await SnapshotRepository(db, owner).get_course(lease.course))[
                "head_version"
            ] == 1
            assert (await visibility.read_availability(db, owner, lease.course, version=1))[
                "ready_count"
            ] == 0

    exercise(action)


def test_ready_wins_lock_race_cancel_waits_then_preserves_exact_scene():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter()
        await s.run_once(lease, a)
        async with sessions() as db:
            manifest = await SnapshotRepository(db, owner).get_version(lease.course, 1)
            sid = UUID(manifest["scenes"][0]["scene_id"])
            vid = await make_validation(
                db,
                owner,
                lease.course,
                lease.fence,
                UUID(manifest["plan_id"]),
                sid,
                1,
                raw=response(["text"]),
            )
            ready = await visibility.commit_scene(
                db,
                owner,
                lease.course,
                lease.fence,
                validation_id=vid,
                expected_head=1,
                key="first",
            )
            cancelling = asyncio.create_task(
                r.cancel(owner, lease.course, lease.fence.operation_id, key="race")
            )
            await asyncio.sleep(0.05)
            assert not cancelling.done()
            async with sessions() as observer:
                assert (await SnapshotRepository(observer, owner).get_course(lease.course))[
                    "head_version"
                ] == 1
            await db.commit()
            await asyncio.wait_for(cancelling, timeout=5)
        await s.reconcile()
        async with sessions() as db:
            course = await SnapshotRepository(db, owner).get_course(lease.course)
            assert course["head_version"] == ready["version"] == 2
            assert (await visibility.read_availability(db, owner, lease.course, version=2))[
                "ready_count"
            ] == 1

    exercise(action)


def test_inflight_cancel_best_effort_abort_quarantines_and_late_settlement_cannot_publish():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter()
        entered, aborted = asyncio.Event(), asyncio.Event()

        async def wait(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                aborted.set()
                raise

        a.observe = wait
        task = asyncio.create_task(s.run_once(lease, a))
        await asyncio.wait_for(entered.wait(), 5)
        await r.cancel(owner, lease.course, lease.fence.operation_id, key="abort")
        await s.reconcile()
        await asyncio.wait_for(task, 5)
        await asyncio.wait_for(aborted.wait(), 5)
        op = await r.read_operation(owner, lease.course, lease.fence.operation_id)
        assert (
            op["state"] == "cancelled"
            and op["budget"]["attempts_used"] == 1
            and op["budget"]["usage_unknown"]
        )
        with pytest.raises(SnapshotError, match="OUTCOME_UNRESOLVED"):
            await resume(r, lease, None)
        async with sessions() as db:
            cap = await db.scalar(
                select(FreeCourseCapacity).where(
                    FreeCourseCapacity.operation_id == lease.fence.operation_id
                )
            )
            assert cap.state == "quarantined"
            aid = cap.pending_attempt_id
        await s.settle(aid, Reply("complete_response", PROOF, candidate(2, GOAL), 100, 200))
        with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
            await s.consume(lease, aid)
        assert (await r.read_operation(owner, lease.course, lease.fence.operation_id))[
            "head_version"
        ] is None
        await resume(r, lease, None)

    exercise(action)


def test_worker_interruption_cancel_scan_and_duplicate_restart_are_durable():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter()
        aid = await s.prepare(lease, a)
        await r.cancel(owner, lease.course, lease.fence.operation_id, key="stop")
        r2 = Recovery(sessions)
        s2 = Scheduler(sessions)
        assert await s2.reconcile() == 1 and await s2.reconcile() == 0
        assert (await r2.read_operation(owner, lease.course, lease.fence.operation_id))[
            "state"
        ] == "cancelled"
        assert not a.calls
        assert not await s2.settle(aid, Reply())
        await s2.settle(aid, Reply("not_executed", PROOF))
        new = await resume(r2, lease, None)
        assert await resume(r2, lease, None) == new

    exercise(action)


def test_read_refresh_is_repeatable_public_safe_and_has_zero_write_effect():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter()
        await s.run_once(lease, a)
        before = await snapshot(sessions, lease.course)
        rows = [
            await Recovery(sessions).read_operation(owner, lease.course, lease.fence.operation_id)
            for _ in range(3)
        ]
        assert rows[0] == rows[1] == rows[2]
        assert before == await snapshot(sessions, lease.course) and len(a.calls) == 1
        encoded = json.dumps(rows)
        for secret in [
            "lease_token",
            "config_snapshot",
            "answer_key",
            "input_snapshot",
            "request_text",
        ]:
            assert secret not in encoded
        api = json.loads((ROOT / "docs/api/phase-1.5-generation.openapi.json").read_text())
        schema = {
            **api["components"]["schemas"]["Operation"],
            "$defs": api["components"]["schemas"],
        }
        schema = json.loads(json.dumps(schema).replace("#/components/schemas/", "#/$defs/"))
        Draft202012Validator(schema).validate(rows[0])
        rows[0]["steps"][0]["state"] = "corrupted-client-copy"
        assert (await r.read_operation(owner, lease.course, lease.fence.operation_id)) == rows[1]
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await r.read_operation(other, lease.course, lease.fence.operation_id)

    exercise(action)


def test_clarification_new_request_preserves_original_sources_without_inferred_profile():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        value = dict(
            needs_clarification=True,
            plan=None,
            questions=["请明确冲突要求"],
            reason="requirements_conflict",
            source_keys=["request_1"],
        )
        a = FakeAdapter([Reply("complete_response", PROOF, value, 100, 100)], n=1)
        await s.run_once(lease, a)
        old = await r.read_operation(owner, lease.course, lease.fence.operation_id)
        assert old["state"] == "awaiting_clarification"
        new = await r.start(
            owner,
            lease.course,
            kind="clarify",
            source_operation_id=lease.fence.operation_id,
            expected_head=None,
            supplement="仅学习数组，保留原练习要求",
            key="clarify",
        )
        fresh = await s.claim()
        await s.run_once(fresh, a)
        assert len(a.calls) == 2
        assert GOAL in a.calls[1].prompt.messages[1].content
        assert "仅学习数组" in a.calls[1].prompt.messages[1].content
        async with sessions() as db:
            newop = await db.get(FreeCourseOperation, UUID(new["operation_id"]))
            req = await db.get(FreeCourseRequest, newop.request_id)
            assert req.version == 2 and req.evidence_snapshot == {} and req.profile_id is None
            original = await db.get(FreeCourseRequest, req.parent_request_id)
            assert original.request_text == GOAL
        assert (await r.read_operation(owner, lease.course, lease.fence.operation_id))[
            "state"
        ] == "awaiting_clarification"
        assert (
            await r.start(
                owner,
                lease.course,
                kind="clarify",
                source_operation_id=lease.fence.operation_id,
                expected_head=None,
                supplement="仅学习数组，保留原练习要求",
                key="clarify",
            )
            == new
        )

    exercise(action)


@pytest.mark.parametrize("supplement", ["", " ", "x" * 4001, None])
def test_invalid_supplement_never_creates_request_or_operation(supplement):
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        await stop(r, s, lease)
        before = await snapshot(sessions, lease.course)
        with pytest.raises(SnapshotError, match="INVALID_OPERATION_INPUT"):
            await r.start(
                owner,
                lease.course,
                kind="clarify",
                source_operation_id=lease.fence.operation_id,
                expected_head=None,
                supplement=supplement,
                key="invalid",
            )
        assert before == await snapshot(sessions, lease.course)

    exercise(action)


def test_real_failed_steps_keep_history_while_new_steps_become_pending():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter(
            [
                Reply("complete_response", PROOF, candidate(2, GOAL), 100, 100),
                Reply("complete_response", PROOF, {}),
                Reply("complete_response", PROOF, {}),
            ]
        )
        for _ in range(4):
            await s.run_once(lease, a)
        old = await r.read_operation(owner, lease.course, lease.fence.operation_id)
        assert old["state"] == "failed" and any(x["state"] == "failed" for x in old["steps"])
        await resume(r, lease, 1)
        assert await r.read_operation(owner, lease.course, lease.fence.operation_id) == old
        async with sessions() as db:
            v = await visibility.read_availability(db, owner, lease.course, version=1)
            assert [x["generation_state"] for x in v["scenes"]] == ["pending", "pending"]

    exercise(action)


def test_new_operation_transaction_failure_rolls_back_receipt_and_lineage(monkeypatch):
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        await stop(r, s, lease)
        before = await snapshot(sessions, lease.course)

        async def broken(*args, **kwargs):
            raise RuntimeError("injected queued event failure")

        monkeypatch.setattr(r.scheduler, "_event", broken)
        with pytest.raises(RuntimeError, match="injected"):
            await resume(r, lease, None)
        assert before == await snapshot(sessions, lease.course)

    exercise(action)


def test_lineage_is_immutable_and_nonempty_downgrade_refused():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        await stop(r, s, lease)
        new = await resume(r, lease, None)
        async with sessions() as db:
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    await db.execute(
                        text(
                            "UPDATE free_course_operation_sources SET source_operation_id=NULL "
                            "WHERE operation_id=:id"
                        ),
                        {"id": UUID(new["operation_id"])},
                    )
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "alembic", "downgrade", "0041_free_course_scheduler"],
            cwd=ROOT / "backend",
            env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode != 0 and "recovery lineage prevents downgrade" in result.stderr

    exercise(action)


def test_cancel_transaction_event_failure_restores_epoch_steps_and_receipt(monkeypatch):
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        before = await snapshot(sessions, lease.course)

        async def broken(*args, **kwargs):
            raise RuntimeError("injected cancel event failure")

        monkeypatch.setattr(r.scheduler, "_event", broken)
        with pytest.raises(RuntimeError, match="injected"):
            await r.cancel(owner, lease.course, lease.fence.operation_id, key="atomic-cancel")
        assert before == await snapshot(sessions, lease.course)
        await s.heartbeat(lease)

    exercise(action)


def test_cancel_lock_wins_concurrent_scene_writer(monkeypatch):
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter()
        await s.run_once(lease, a)
        async with sessions() as db:
            manifest = await SnapshotRepository(db, owner).get_version(lease.course, 1)
            vid = await make_validation(
                db,
                owner,
                lease.course,
                lease.fence,
                UUID(manifest["plan_id"]),
                UUID(manifest["scenes"][0]["scene_id"]),
                1,
                raw=response(["text"]),
            )
        entered, release = asyncio.Event(), asyncio.Event()
        original = r.scheduler._event

        async def gated(db, lease, kind, payload):
            await original(db, lease, kind, payload)
            if kind == "cancel_requested":
                entered.set()
                await release.wait()

        monkeypatch.setattr(r.scheduler, "_event", gated)
        cancelling = asyncio.create_task(
            r.cancel(owner, lease.course, lease.fence.operation_id, key="wins")
        )
        await asyncio.wait_for(entered.wait(), 5)

        async def commit():
            async with sessions() as db:
                return await visibility.commit_scene(
                    db,
                    owner,
                    lease.course,
                    lease.fence,
                    validation_id=vid,
                    expected_head=1,
                    key="late-writer",
                )

        writer = asyncio.create_task(commit())
        await asyncio.sleep(0.05)
        assert not writer.done()
        release.set()
        await cancelling
        with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
            await writer
        await s.reconcile()
        assert (await r.read_operation(owner, lease.course, lease.fence.operation_id))[
            "head_version"
        ] == 1

    exercise(action)


def test_transport_ignores_local_abort_late_callback_only_settles():
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter()
        entered = asyncio.Event()

        async def ignores_abort(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return  # Synthetic remote response arrives after abort.

        a.observe = ignores_abort
        task = asyncio.create_task(s.run_once(lease, a))
        await asyncio.wait_for(entered.wait(), 5)
        await r.cancel(owner, lease.course, lease.fence.operation_id, key="stop")
        await s.reconcile()
        await asyncio.wait_for(task, 5)
        for _ in range(50):
            view = await r.read_operation(owner, lease.course, lease.fence.operation_id)
            if not view["budget"]["usage_unknown"]:
                break
            await asyncio.sleep(0.02)
        assert view["state"] == "cancelled" and view["head_version"] is None
        assert not view["budget"]["usage_unknown"] and len(a.calls) == 1
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(FreeCourseCapacity.slot).where(
                        FreeCourseCapacity.operation_id == lease.fence.operation_id
                    )
                )
                is None
            )

    exercise(action)


def test_late_settlement_winning_unknown_terminal_lock_does_not_leak_capacity(monkeypatch):
    async def action(r, s, sessions, owner, other):
        lease = await running(s, owner)
        a = FakeAdapter([Reply()])
        original = s.settle

        async def late_before_terminal(aid, reply):
            if reply.evidence == "unknown":
                await original(aid, Reply("not_executed", PROOF))
                return False
            return await original(aid, reply)

        monkeypatch.setattr(s, "settle", late_before_terminal)
        await s.run_once(lease, a)
        view = await r.read_operation(owner, lease.course, lease.fence.operation_id)
        assert view["state"] == "failed" and view["reason_code"] == "OUTCOME_UNKNOWN"
        assert view["budget"]["attempts_used"] == 1 and not view["budget"]["usage_unknown"]
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(FreeCourseCapacity.slot).where(
                        FreeCourseCapacity.operation_id == lease.fence.operation_id
                    )
                )
                is None
            )
        await resume(r, lease, None)

    exercise(action)


def test_cancel_receipt_matches_approved_operation_schema():
    async def action(r, s, sessions, owner, other):
        cid, oid = await queued(s, owner)
        receipt = await r.cancel(owner, cid, oid, key="schema")
        api = json.loads((ROOT / "docs/api/phase-1.5-generation.openapi.json").read_text())
        schema = {
            **api["components"]["schemas"]["Operation"],
            "$defs": api["components"]["schemas"],
        }
        schema = json.loads(json.dumps(schema).replace("#/components/schemas/", "#/$defs/"))
        Draft202012Validator(schema).validate(receipt)
        await s.reconcile()
        assert await r.cancel(owner, cid, oid, key="schema") == receipt

    exercise(action)


def test_catalog_only_cancel_can_finish_pre_scheduler_free_operation():
    async def action(r, s, sessions, owner, other):
        async with sessions() as db:
            old = await SnapshotRepository(db, owner).create_course(GOAL, key="old-storage-only")
            await db.commit()
        cid, oid = UUID(old["course_id"]), UUID(old["operation_id"])
        ack = await r.cancel(owner, cid, oid, key="legacy-stop")
        assert ack["state"] == "cancel_requested"
        assert await s.reconcile() == 1
        final = await r.read_operation(owner, cid, oid)
        assert final["state"] == "cancelled" and final["budget"]["attempts_used"] == 0
        assert await s.claim() is None

    exercise(action)
