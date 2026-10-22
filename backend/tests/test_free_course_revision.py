"""Atomic revision sets in real isolated PG with synthetic zero-Provider transport."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_free_course_planning import candidate
from test_free_course_scheduler import GOAL, PROOF, FakeAdapter

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course import FreeCourseSceneVersion
from app.models.free_course_progress import FreeCourseEvent
from app.models.free_course_revision import FreeCourseRevisionStage
from app.services.free_course_recovery import Recovery
from app.services.free_course_revision import Revisions
from app.services.free_course_scheduler import Reply, Scheduler
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository
from app.services.free_scene_availability import read_availability

ROOT = Path(__file__).resolve().parents[2]


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value
    url = make_url(value)
    assert url.host == "127.0.0.1" and url.port == 15437
    assert (url.database or "").startswith("edumind_catalog_p15_t016_")
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
                db.add_all([User(id=o, is_guest=True) for o in owners])
                await db.commit()
            await action(
                Revisions(sessions), Scheduler(sessions), Recovery(sessions), sessions, *owners
            )
        finally:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE free_course_capacity SET state='free',user_id=NULL,course_id=NULL,"
                        "operation_id=NULL,epoch=NULL,expires_at=NULL,pending_attempt_id=NULL"
                    )
                )
                for o in owners:
                    await conn.execute(text("DELETE FROM users WHERE id=:o"), {"o": o})
            await engine.dispose()

    asyncio.run(run())


async def setup(s, sessions, owner, n=4):
    created = await s.enqueue(owner, GOAL, key="create")
    cid = UUID(created["course_id"])
    lease = await s.claim()
    plan = candidate(n, GOAL)
    if n == 4:
        plan["plan"]["scenes"][3]["depends_on"] = []
    a = FakeAdapter([Reply("complete_response", PROOF, plan, 100, 100)], n=n)
    for _ in range(n + 2):
        await s.run_once(lease, a)
    async with sessions() as db:
        manifest = await SnapshotRepository(db, owner).get_version(cid, n + 1)
    return cid, manifest, a


async def start(r, owner, cid, manifest, index=1, kind="revise_scene", key="revise"):
    sid = UUID(manifest["scenes"][index]["scene_id"]) if kind == "revise_scene" else None
    impact = await r.impact(owner, cid, kind=kind, base=manifest["version"], scene_id=sid)
    created = await r.start(
        owner,
        cid,
        kind=kind,
        base=manifest["version"],
        scene_id=sid,
        instruction="重新说明这个场景，保留原要求和共享约定",
        impact_digest=impact["impact_digest"],
        key=key,
    )
    return created, impact


def test_local_revision_stages_dependencies_and_switches_whole_set_once():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        created, impact = await start(r, owner, cid, old)
        assert impact["affected_scene_ids"] == [
            old["scenes"][1]["scene_id"],
            old["scenes"][2]["scene_id"],
        ]
        lease = await s.claim()
        await s.run_once(lease, a)
        async with sessions() as db:
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == 5
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseRevisionStage)
                    .where(FreeCourseRevisionStage.operation_id == lease.fence.operation_id)
                )
                == 3
            )
            assert (await read_availability(db, owner, cid, version=5))["ready_count"] == 4
        await s.run_once(lease, a)
        assert (await recovery.read_operation(owner, cid, lease.fence.operation_id))[
            "head_version"
        ] == 5
        await s.run_once(lease, a)
        op = await recovery.read_operation(owner, cid, lease.fence.operation_id)
        assert (
            op["state"] == "succeeded"
            and op["budget"]["attempts_used"] == 2
            and op["head_version"] == 6
        )
        async with sessions() as db:
            new = await SnapshotRepository(db, owner).get_version(cid, 6)
            assert new["plan_id"] != old["plan_id"]
            assert all(
                n["scene_version_id"] != o["scene_version_id"]
                for n, o in zip(new["scenes"], old["scenes"])
            )
            assert (await read_availability(db, owner, cid, version=6))["ready_count"] == 4
            assert (await SnapshotRepository(db, owner).get_version(cid, 5)) == old
            oldbody = await db.get(
                FreeCourseSceneVersion, UUID(old["scenes"][0]["scene_version_id"])
            )
            newbody = await db.get(
                FreeCourseSceneVersion, UUID(new["scenes"][0]["scene_version_id"])
            )
            assert (
                oldbody.content_json == newbody.content_json
                and oldbody.actions_json == newbody.actions_json
            )
        assert (
            await r.start(
                owner,
                cid,
                kind="revise_scene",
                base=5,
                scene_id=UUID(old["scenes"][1]["scene_id"]),
                instruction="重新说明这个场景，保留原要求和共享约定",
                impact_digest=impact["impact_digest"],
                key="revise",
            )
            == created
        )

    exercise(action)


def test_adjust_outline_uses_new_plan_and_no_partial_head():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, _ = await setup(s, sessions, owner, n=1)
        _, impact = await start(r, owner, cid, old, kind="adjust_outline")
        assert impact["requires_outline_adjustment"]
        lease = await s.claim()
        a = FakeAdapter(n=3)
        await s.run_once(lease, a)
        for _ in range(3):
            assert (await recovery.read_operation(owner, cid, lease.fence.operation_id))[
                "head_version"
            ] == 2
            await s.run_once(lease, a)
        await s.run_once(lease, a)
        op = await recovery.read_operation(owner, cid, lease.fence.operation_id)
        assert op["state"] == "succeeded" and op["head_version"] == 3 and len(a.calls) == 4
        async with sessions() as db:
            assert len((await SnapshotRepository(db, owner).get_version(cid, 3))["scenes"]) == 3

    exercise(action)


def test_failure_and_cancel_leave_old_head_and_private_stages():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        await start(r, owner, cid, old)
        lease = await s.claim()
        await s.run_once(lease, a)
        await recovery.cancel(owner, cid, lease.fence.operation_id, key="stop")
        await s.reconcile()
        assert (await recovery.read_operation(owner, cid, lease.fence.operation_id))[
            "head_version"
        ] == 5
        with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
            await s.run_once(lease, a)
        await start(r, owner, cid, old, key="second")
        fresh = await s.claim()
        broken = FakeAdapter(
            [Reply("complete_response", PROOF, {}), Reply("complete_response", PROOF, {})]
        )
        await s.run_once(fresh, broken)
        await s.run_once(fresh, broken)
        op = await recovery.read_operation(owner, cid, fresh.fence.operation_id)
        assert op["state"] == "failed" and op["head_version"] == 5

    exercise(action)


def test_impact_readonly_owner_baseline_and_confirmation_guards():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        sid = UUID(old["scenes"][1]["scene_id"])
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await r.impact(other, cid, kind="revise_scene", base=5, scene_id=sid)
        with pytest.raises(SnapshotError, match="STALE_COURSE_VERSION"):
            await r.impact(owner, cid, kind="revise_scene", base=4, scene_id=sid)
        with pytest.raises(SnapshotError, match="IMPACT_CHANGED"):
            await r.start(
                owner,
                cid,
                kind="revise_scene",
                base=5,
                scene_id=sid,
                instruction="说明",
                impact_digest="0" * 64,
                key="bad",
            )
        created, impact = await start(r, owner, cid, old)
        assert (
            await r.start(
                owner,
                cid,
                kind="revise_scene",
                base=5,
                scene_id=sid,
                instruction="重新说明这个场景，保留原要求和共享约定",
                impact_digest=impact["impact_digest"],
                key="revise",
            )
            == created
        )
        with pytest.raises(SnapshotError, match="OPERATION_ACTIVE"):
            await start(r, owner, cid, old, key="other")
        assert len(a.calls) == 5

    exercise(action)


def test_replacement_hook_failure_rolls_back_all_ready_head_and_events(monkeypatch):
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        await start(r, owner, cid, old, index=2)
        lease = await s.claim()
        await s.run_once(lease, a)
        from app.services import free_course_effects

        async def broken(*args):
            raise RuntimeError("injected effect rollback")

        monkeypatch.setattr(free_course_effects, "replacement_effects", broken)
        with pytest.raises(RuntimeError, match="injected"):
            await s.run_once(lease, a)
        op = await recovery.read_operation(owner, cid, lease.fence.operation_id)
        assert op["head_version"] == 5 and op["state"] == "running"
        async with sessions() as db:
            assert not await db.scalar(
                select(FreeCourseEvent.id).where(
                    FreeCourseEvent.operation_id == lease.fence.operation_id,
                    FreeCourseEvent.event_type == "scene_ready",
                )
            )

    exercise(action)


def test_adjust_outline_clarification_stays_atomic_at_original_baseline():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, _ = await setup(s, sessions, owner, n=1)
        created, _ = await start(r, owner, cid, old, kind="adjust_outline")
        lease = await s.claim()
        raw = dict(
            needs_clarification=True,
            plan=None,
            questions=["明确调整范围"],
            reason="requirements_conflict",
            source_keys=["request_1"],
        )
        a = FakeAdapter([Reply("complete_response", PROOF, raw, 100, 100)], n=2)
        await s.run_once(lease, a)
        assert (await recovery.read_operation(owner, cid, lease.fence.operation_id))[
            "state"
        ] == "awaiting_clarification"
        clarified = await recovery.start(
            owner,
            cid,
            kind="clarify",
            source_operation_id=UUID(created["operation_id"]),
            expected_head=2,
            supplement="请拆为两个场景",
            key="clarify-adjust",
        )
        fresh = await s.claim()
        for _ in range(3):
            await s.run_once(fresh, a)
            assert (await recovery.read_operation(owner, cid, fresh.fence.operation_id))[
                "head_version"
            ] == 2
        await s.run_once(fresh, a)
        op = await recovery.read_operation(owner, cid, UUID(clarified["operation_id"]))
        assert op["state"] == "succeeded" and op["head_version"] == 3

    exercise(action)


def test_impact_schema_and_private_stage_never_reads_as_public_ready():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        created, impact = await start(r, owner, cid, old, index=2)
        from jsonschema import Draft202012Validator

        api = json.loads((ROOT / "docs/api/phase-1.5-generation.openapi.json").read_text())
        Draft202012Validator(api["components"]["schemas"]["Impact"]).validate(impact)
        lease = await s.claim()
        await s.run_once(lease, a)
        async with sessions() as db:
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == 5
            staged = await db.scalar(
                select(FreeCourseRevisionStage).where(
                    FreeCourseRevisionStage.operation_id == UUID(created["operation_id"]),
                    FreeCourseRevisionStage.scene_id == UUID(old["scenes"][2]["scene_id"]),
                )
            )
            assert staged is not None
            # The old precise manifest stays the visible binding; no candidate leaks through it.
            view = await read_availability(db, owner, cid, version=5)
            assert view["scenes"][2]["scene_version_id"] == old["scenes"][2]["scene_version_id"]
            assert view["scenes"][2]["scene_version_id"] != str(staged.scene_version_id)

    exercise(action)


def test_explicit_null_base_adjustment_after_cancelled_initial_generation():
    async def action(r, s, recovery, sessions, owner, other):
        original = await s.enqueue(owner, GOAL, key="first")
        cid = UUID(original["course_id"])
        oid = UUID(original["operation_id"])
        await recovery.cancel(owner, cid, oid, key="stop")
        await s.reconcile()
        impact = await r.impact(owner, cid, kind="adjust_outline", base=None)
        assert impact["affected_scene_ids"] == []
        created = await r.start(
            owner,
            cid,
            kind="adjust_outline",
            base=None,
            scene_id=None,
            instruction="调整为两个场景",
            impact_digest=impact["impact_digest"],
            key="adjust",
        )
        lease = await s.claim()
        a = FakeAdapter(n=2)
        for _ in range(3):
            await s.run_once(lease, a)
            assert (await recovery.read_operation(owner, cid, lease.fence.operation_id))[
                "head_version"
            ] is None
        await s.run_once(lease, a)
        op = await recovery.read_operation(owner, cid, UUID(created["operation_id"]))
        assert op["state"] == "succeeded" and op["head_version"] == 1

    exercise(action)


def test_null_baseline_is_not_a_valid_local_revision_even_in_storage():
    async def action(r, s, recovery, sessions, owner, other):
        created = await s.enqueue(owner, GOAL, key="create")
        cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
        from sqlalchemy.exc import DBAPIError

        from app.models.free_course_revision import FreeCourseRevision

        async with sessions() as db:
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    db.add(
                        FreeCourseRevision(
                            user_id=owner,
                            course_id=cid,
                            operation_id=oid,
                            kind="revise_scene",
                            base_head=None,
                            instruction="x",
                            impact_json={},
                            impact_digest="0" * 64,
                        )
                    )
                    await db.flush()

    exercise(action)


def test_expired_revision_epoch_stops_before_reusing_private_stages_or_spending_again():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        await start(r, owner, cid, old)
        lease = await s.claim()
        await s.run_once(lease, a)
        sent = len(a.calls)
        async with sessions() as db, db.begin():
            await db.execute(
                text(
                    "UPDATE free_course_operations SET lease_expires_at="
                    "clock_timestamp()-interval '1 second' WHERE id=:id"
                ),
                {"id": lease.fence.operation_id},
            )
        await s.reconcile()
        view = await recovery.read_operation(owner, cid, lease.fence.operation_id)
        assert (
            view["state"] == "failed"
            and view["reason_code"] == "LEASE_LOST"
            and view["head_version"] == 5
        )
        assert await s.claim() is None and len(a.calls) == sent
        await start(r, owner, cid, old, key="new-explicit-revision")

    exercise(action)
