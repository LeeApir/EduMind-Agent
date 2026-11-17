"""Atomic revision sets in real isolated PG with synthetic zero-Provider transport."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_free_course_revision import setup, start

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course_quality import FreeCourseQualityDecision, FreeCourseVisibilityFact
from app.services.free_course_quality import (
    Feedback,
    Maintenance,
    MaintenanceAuthority,
    local_authority,
)
from app.services.free_course_recovery import Recovery
from app.services.free_course_revision import Revisions
from app.services.free_course_scheduler import Scheduler
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository
from app.services.free_scene_availability import read_availability, read_ready_scene

ROOT = Path(__file__).resolve().parents[2]


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value
    url = make_url(value)
    assert url.host == "127.0.0.1" and url.port == 15437
    assert (url.database or "").startswith("edumind_catalog_p15_t017_")
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


def draft(cid, manifest, index=1, action="confirm_defect", target=None, key="decision"):
    item = manifest["scenes"][index]
    return dict(
        decision_key=key,
        course_id=str(cid),
        binding=dict(
            course_version=manifest["version"],
            scene_id=item["scene_id"],
            scene_version_id=item["scene_version_id"],
        ),
        exercise_id=None,
        exercise_version_id=None,
        action=action,
        target_decision_id=target,
        scope="scene",
        impact_digest="0" * 64,
        reason="人工独立推演发现此处链指针顺序错误，仅影响准确版本",
        basis=[
            dict(
                kind="manual_derivation",
                source_ref="synthetic:independent-static-check",
                excerpt="仅供隔离测试的人工推演",
                reason="记录来源、反例与影响范围，不执行代码",
            )
        ],
    )


async def applied(m, owner, d):
    impact = await m.dry_run(owner, d)
    d["impact_digest"] = impact["impact_digest"]
    return await m.apply(owner, d)


async def report(f, owner, cid, manifest, index=1):
    d = draft(cid, manifest, index)
    return await f.submit(
        owner,
        cid,
        dict(
            **d["binding"],
            anchor_id="intro",
            exercise_id=None,
            exercise_version_id=None,
            description="这里可能有问题，请复核",
        ),
        key="feedback",
    )


def test_pending_feedback_owner_and_receipt():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        f = Feedback(sessions)
        # Pick actual immutable anchor; schema never guesses a position.
        async with sessions() as db:
            raw = await SnapshotRepository(db, owner).get_scene_snapshot(
                cid, 5, UUID(old["scenes"][1]["scene_id"])
            )
        body = dict(
            course_version=5,
            scene_id=old["scenes"][1]["scene_id"],
            scene_version_id=old["scenes"][1]["scene_version_id"],
            anchor_id=raw["content"]["blocks"][0]["anchor_id"],
            exercise_id=None,
            exercise_version_id=None,
            description="可能存在错误",
        )
        x = await f.submit(owner, cid, body, key="feedback")
        assert await f.submit(owner, cid, body, key="feedback") == x
        assert (await f.read(owner, cid, UUID(x["feedback_id"])))["status"] == "pending"
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await f.read(other, cid, UUID(x["feedback_id"]))
        with pytest.raises(SnapshotError, match="IDEMPOTENCY_CONFLICT"):
            await f.submit(owner, cid, {**body, "description": "不同内容"}, key="feedback")
        async with sessions() as db:
            assert (await read_availability(db, owner, cid, version=5))["ready_count"] == 4

    exercise(action)


def test_confirm_exact_dependency_closure_and_replay():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        m = Maintenance(sessions, local_authority())
        d = draft(cid, old)
        impact = await m.dry_run(owner, d)
        assert len(impact["targets"]) == 2
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(FreeCourseQualityDecision)) == 0
        x = await applied(m, owner, d)
        assert await m.apply(owner, d) == x
        async with sessions() as db:
            av = await read_availability(db, owner, cid, version=5)
            assert av["ready_count"] == 2
            for i in [1, 2]:
                with pytest.raises(SnapshotError, match="CONTENT_UNAVAILABLE"):
                    await read_ready_scene(
                        db, owner, cid, version=5, scene_id=UUID(old["scenes"][i]["scene_id"])
                    )
            await read_ready_scene(
                db, owner, cid, version=5, scene_id=UUID(old["scenes"][3]["scene_id"])
            )
            assert await db.scalar(select(func.count()).select_from(FreeCourseVisibilityFact)) == 2
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await m.dry_run(other, d)

    exercise(action)


def test_correction_never_revives_restore_exact_and_dependencies():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        m = Maintenance(sessions, local_authority())
        first = await applied(m, owner, draft(cid, old))
        correction = draft(
            cid, old, action="decision_correction", target=first["decision_id"], key="correction"
        )
        await applied(m, owner, correction)
        async with sessions() as db:
            assert (await read_availability(db, owner, cid, version=5))["ready_count"] == 2
        dep = draft(cid, old, 2, action="restore", target=first["decision_id"], key="restore-dep")
        with pytest.raises(SnapshotError, match="CONTENT_UNAVAILABLE"):
            await applied(m, owner, dep)
        await applied(
            m, owner, draft(cid, old, action="restore", target=first["decision_id"], key="restore")
        )
        async with sessions() as db:
            assert (await read_availability(db, owner, cid, version=5))["ready_count"] == 3

    exercise(action)


def test_model_opinion_and_forged_authority_denied():
    with pytest.raises(PermissionError):
        Maintenance(None, MaintenanceAuthority("Lee", object()))

    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        m = Maintenance(sessions, local_authority())
        d = draft(cid, old)
        d["basis"][0]["kind"] = "model_opinion"
        with pytest.raises(SnapshotError, match="INVALID_QUALITY_INPUT"):
            await m.dry_run(owner, d)
        d["basis"][0]["kind"] = "mechanical_rule"
        with pytest.raises(SnapshotError, match="MECHANICAL_FAILURE_NOT_FOUND"):
            await applied(m, owner, d)
        async with sessions() as db:
            assert (await read_availability(db, owner, cid, version=5))["ready_count"] == 4

    exercise(action)


def test_old_version_copies_propagate_but_new_generated_context_does_not():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        await start(r, owner, cid, old)
        lease = await s.claim()
        for _ in range(3):
            await s.run_once(lease, a)
        m = Maintenance(sessions, local_authority())
        d = draft(cid, old, index=0)
        impact = await m.dry_run(owner, d)
        assert len(impact["targets"]) == 6
        await applied(m, owner, d)
        async with sessions() as db:
            assert (await read_availability(db, owner, cid, version=6))["ready_count"] == 1
            assert (await read_availability(db, owner, cid, version=5))["ready_count"] == 1

    exercise(action)


def test_quality_fences_active_revision_and_stale_dryrun():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        m = Maintenance(sessions, local_authority())
        d = draft(cid, old, index=0)
        d["impact_digest"] = (await m.dry_run(owner, d))["impact_digest"]
        op, _ = await start(r, owner, cid, old)
        lease = await s.claim()
        with pytest.raises(SnapshotError, match="IMPACT_CHANGED"):
            await m.apply(owner, d)
        await applied(m, owner, d)
        state = await recovery.read_operation(owner, cid, UUID(op["operation_id"]))
        assert (
            state["state"] == "cancel_requested" and state["reason_code"] == "CONTENT_UNAVAILABLE"
        )
        count = len(a.calls)
        with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
            await s.run_once(lease, a)
        assert len(a.calls) == count
        async with sessions() as db:
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == 5

    exercise(action)


def test_not_confirmed_and_bound_feedback_status():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        f = Feedback(sessions)
        async with sessions() as db:
            raw = await SnapshotRepository(db, owner).get_scene_snapshot(
                cid, 5, UUID(old["scenes"][1]["scene_id"])
            )
        d = draft(cid, old)
        body = dict(
            **d["binding"],
            anchor_id=raw["content"]["blocks"][0]["anchor_id"],
            exercise_id=None,
            exercise_version_id=None,
            description="待核对",
        )
        fid = UUID((await f.submit(owner, cid, body, key="feedback"))["feedback_id"])
        m = Maintenance(sessions, local_authority())
        d["action"] = "not_confirmed"
        await applied(m, owner, d)
        assert (await f.read(owner, cid, fid))["status"] == "not_confirmed"
        async with sessions() as db:
            assert (await read_availability(db, owner, cid, version=5))["ready_count"] == 4
        body["scene_version_id"] = old["scenes"][0]["scene_version_id"]
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await f.submit(owner, cid, body, key="wrong")

    exercise(action)


def test_quality_transaction_failure_rolls_back_all_facts(monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("synthetic transaction failure")

    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        m = Maintenance(sessions, local_authority())
        monkeypatch.setattr("app.services.free_course_effects.quality_effects", broken)
        with pytest.raises(RuntimeError, match="synthetic"):
            await applied(m, owner, draft(cid, old))
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(FreeCourseVisibilityFact)) == 0
            assert await db.scalar(select(func.count()).select_from(FreeCourseQualityDecision)) == 0
            assert (await read_availability(db, owner, cid, version=5))["ready_count"] == 4

    exercise(action)


def test_quality_audit_is_immutable_at_database_boundary():
    from sqlalchemy.exc import DBAPIError

    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        m = Maintenance(sessions, local_authority())
        decision = await applied(m, owner, draft(cid, old))
        async with sessions() as db:
            with pytest.raises(DBAPIError):
                await db.execute(
                    text(
                        "UPDATE free_course_quality_decisions SET authority='forged' WHERE id=:id"
                    ),
                    dict(id=UUID(decision["decision_id"])),
                )
                await db.commit()
            await db.rollback()
            with pytest.raises(DBAPIError):
                await db.execute(
                    text("DELETE FROM free_course_visibility_facts WHERE user_id=:owner"),
                    dict(owner=owner),
                )
                await db.commit()

    exercise(action)


def test_restore_cannot_bypass_disabled_necessary_upstream():
    async def action(r, s, recovery, sessions, owner, other):
        cid, old, a = await setup(s, sessions, owner)
        m = Maintenance(sessions, local_authority())
        await applied(m, owner, draft(cid, old, index=0, key="root"))
        child = await applied(m, owner, draft(cid, old, index=1, key="child"))
        with pytest.raises(SnapshotError, match="CONTENT_UNAVAILABLE"):
            await applied(
                m,
                owner,
                draft(
                    cid,
                    old,
                    index=1,
                    action="restore",
                    target=child["decision_id"],
                    key="badrestore",
                ),
            )
        async with sessions() as db:
            assert (await read_availability(db, owner, cid, version=5))["ready_count"] == 1

    exercise(action)


def test_exercise_defect_disables_only_group_and_necessary_descendants():
    from test_free_course_planning import candidate
    from test_free_course_scheduler import GOAL, PROOF, FakeAdapter
    from test_free_scene_generation import response

    from app.services.free_course_exercise_identity import exercise_identity
    from app.services.free_course_scheduler import Reply

    async def action(r, s, recovery, sessions, owner, other):
        created = await s.enqueue(owner, GOAL, key="create")
        cid = UUID(created["course_id"])
        plan = candidate(2, GOAL)
        for scene in plan["plan"]["scenes"]:
            scene["forms"] = ["text", "exercise"]
        adapter = FakeAdapter(
            [
                Reply("complete_response", PROOF, plan, 100, 100),
                Reply("complete_response", PROOF, response(["text", "exercise"]), 100, 100),
                Reply("complete_response", PROOF, response(["text", "exercise"]), 100, 100),
            ]
        )
        lease = await s.claim()
        for _ in range(4):
            await s.run_once(lease, adapter)
        async with sessions() as db:
            manifest = await SnapshotRepository(db, owner).get_version(cid, 3)
        item = manifest["scenes"][0]
        ids = exercise_identity(
            owner, cid, UUID(item["scene_id"]), UUID(item["scene_version_id"]), "practice"
        )
        d = draft(cid, manifest, index=0)
        d.update(scope="exercise", exercise_id=str(ids[0]), exercise_version_id=str(ids[1]))
        m = Maintenance(sessions, local_authority())
        await applied(m, owner, d)
        async with sessions() as db:
            body = await read_ready_scene(
                db, owner, cid, version=3, scene_id=UUID(item["scene_id"])
            )
            assert body["blocks"][0]["kind"] == "text"
            assert body["blocks"][1]["disabled"] is True and body["blocks"][1]["items"] == []
            with pytest.raises(SnapshotError, match="CONTENT_UNAVAILABLE"):
                await read_ready_scene(
                    db, owner, cid, version=3, scene_id=UUID(manifest["scenes"][1]["scene_id"])
                )

    exercise(action)
