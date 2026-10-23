"""Exact-context tutor records: synthetic content, actual isolated PostgreSQL, no Provider."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_free_course_answers import practice
from test_free_course_feedback import applied, draft
from test_free_course_revision import setup

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course_answers import FreeCourseAssessmentExposure
from app.models.free_course_tutor import FreeCourseTutorReply, FreeCourseTutorTurn
from app.models.free_course_writes import FreeCourseOperation
from app.services.free_course_quality import Maintenance, local_authority
from app.services.free_course_scheduler import Scheduler
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, canonical
from app.services.free_course_tutor import TutorTurns, store_reply

ROOT = Path(__file__).resolve().parents[2]


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value
    url = make_url(value)
    assert url.host == "127.0.0.1" and url.port == 15437
    assert (url.database or "").startswith("edumind_catalog_p15_t043_")
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
                Scheduler(sessions, graph_version="mvp-0.2.0"),
                TutorTurns(sessions),
                sessions,
                *owners,
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


def request(manifest, index=0):
    scene = manifest["scenes"][index]
    return dict(
        course_version=manifest["version"],
        scene_id=scene["scene_id"],
        scene_version_id=scene["scene_version_id"],
        message="请用当前例子补充解释，不要改课。",
        acknowledge_assisted_practice=True,
    )


async def finish(sessions, owner, cid, receipt, markdown="补充解释", anchors=None):
    async with sessions() as db, db.begin():
        repo = SnapshotRepository(db, owner)
        fence = await repo.acquire_write_fence(cid, UUID(receipt["operation_id"]))
        await store_reply(db, owner, cid, fence, UUID(receipt["turn_id"]), markdown, anchors or [])
        op = await repo._operation(cid, fence.operation_id)
        op.state = "succeeded"


def test_owner_exact_binding_replay_assistance_and_no_private_answers():
    async def action(s, t, sessions, owner, other):
        cid, manifest, _, _ = await practice(s, sessions, owner)
        body = request(manifest)
        receipt = await t.enqueue(owner, cid, body, key="tutor")
        assert await t.enqueue(owner, cid, body, key="tutor") == receipt
        async with sessions() as db:
            turn = await db.get(FreeCourseTutorTurn, UUID(receipt["turn_id"]))
            assert turn.context_json["original_goal"]
            assert "answer_key" not in canonical(turn.context_json).decode()
            assert '"solution"' not in canonical(turn.context_json).decode()
            assert turn.context_json["learner"]["effective_mastery"] == []
            assert await db.scalar(
                select(func.count()).select_from(FreeCourseAssessmentExposure)
            ) == len(turn.sources_json["exercises"])
            assert (await db.get(FreeCourseOperation, turn.operation_id)).kind == "tutor_turn"
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await t.read(other, cid, UUID(receipt["turn_id"]))
        with pytest.raises(SnapshotError, match="IDEMPOTENCY_CONFLICT"):
            await t.enqueue(owner, cid, {**body, "message": "另一个问题"}, key="tutor")
        assert (await t.read(owner, cid, UUID(receipt["turn_id"])))["status"] == "queued"

    exercise(action)


def test_active_generation_and_missing_acknowledgement_reject_without_side_effects():
    async def action(s, t, sessions, owner, other):
        cid, manifest, _ = await setup(s, sessions, owner, n=2)
        body = request(manifest)
        with pytest.raises(SnapshotError):
            await t.enqueue(owner, cid, {**body, "acknowledge_assisted_practice": False}, key="bad")
        result = await s.enqueue(other, "另一个目标", key="other")
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await t.enqueue(other, cid, body, key="foreign")
        receipt = await t.enqueue(owner, cid, body, key="one")
        with pytest.raises(SnapshotError, match="OPERATION_ACTIVE"):
            await t.enqueue(owner, cid, body, key="two")
        assert result["course_id"] != str(cid)
        assert receipt["turn_id"]

    exercise(action)


def test_upstreams_and_same_version_history_bounded_and_reply_is_escaped():
    async def action(s, t, sessions, owner, other):
        cid, manifest, _ = await setup(s, sessions, owner, n=4)
        body = request(manifest, 2)
        for i in range(3):
            receipt = await t.enqueue(
                owner, cid, {**body, "message": f"第{i}次解释"}, key=f"turn-{i}"
            )
            await finish(
                sessions, owner, cid, receipt, "<script>bad()</script> [link](https://bad.example)"
            )
        receipt = await t.enqueue(owner, cid, body, key="last")
        async with sessions() as db:
            turn = await db.get(FreeCourseTutorTurn, UUID(receipt["turn_id"]))
            assert len(turn.context_json["upstream"]) <= 2
            assert len(turn.context_json["history"]) == 2
            assert all("&lt;script&gt;" in h["markdown"] for h in turn.context_json["history"])
            assert "第0次解释" not in [h["message"] for h in turn.context_json["history"]]
        assert (await t.read(owner, cid, UUID(receipt["turn_id"])))["markdown"] is None

    exercise(action)


def test_confirmed_defect_invalidates_ready_body_and_replay_never_restores_it():
    async def action(s, t, sessions, owner, other):
        cid, manifest, _, _ = await practice(s, sessions, owner)
        body = request(manifest)
        receipt = await t.enqueue(owner, cid, body, key="turn")
        await finish(sessions, owner, cid, receipt)
        assert (await t.read(owner, cid, UUID(receipt["turn_id"])))["status"] == "ready"
        m = Maintenance(sessions, local_authority())
        await applied(m, owner, draft(cid, manifest, index=0))
        invalid = await t.read(owner, cid, UUID(receipt["turn_id"]))
        assert (
            invalid["status"] == "invalidated"
            and invalid["markdown"] is None
            and invalid["anchor_refs"] == []
        )
        assert invalid["message"] == body["message"]
        assert await t.enqueue(owner, cid, body, key="turn") == receipt

    exercise(action)


def test_cancel_fences_output_and_source_mutation_rolls_back():
    async def action(s, t, sessions, owner, other):
        cid, manifest, _ = await setup(s, sessions, owner, n=2)
        receipt = await t.enqueue(owner, cid, request(manifest), key="turn")
        async with sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            fence = await repo.acquire_write_fence(cid, UUID(receipt["operation_id"]))
        async with sessions() as db, db.begin():
            await SnapshotRepository(db, owner).fence_cancellation(cid, fence.operation_id)
        with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
            async with sessions() as db, db.begin():
                await store_reply(db, owner, cid, fence, UUID(receipt["turn_id"]), "迟到解释", [])
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(FreeCourseTutorReply)) == 0
        with pytest.raises(DBAPIError):
            async with sessions() as db, db.begin():
                await db.execute(
                    text("UPDATE free_course_tutor_turns SET message='tamper' WHERE id=:id"),
                    {"id": UUID(receipt["turn_id"])},
                )

    exercise(action)


def test_unapproved_anchor_and_stale_version_do_not_publish_or_create_new_head():
    async def action(s, t, sessions, owner, other):
        cid, manifest, _ = await setup(s, sessions, owner, n=2)
        body = request(manifest)
        with pytest.raises(SnapshotError):
            await t.enqueue(owner, cid, {**body, "course_version": 1}, key="old")
        receipt = await t.enqueue(owner, cid, body, key="turn")
        with pytest.raises(SnapshotError, match="TUTOR_OUTPUT_INVALID"):
            await finish(sessions, owner, cid, receipt, anchors=["invented"])
        async with sessions() as db:
            assert (await SnapshotRepository(db, owner).get_course(cid))[
                "head_version"
            ] == manifest["version"]
            assert await db.scalar(select(func.count()).select_from(FreeCourseTutorReply)) == 0

    exercise(action)


def test_ready_history_survives_ordinary_revision_but_late_output_cannot_change_head():
    from test_free_course_revision import start

    from app.services.free_course_revision import Revisions

    async def action(s, t, sessions, owner, other):
        cid, manifest, adapter = await setup(s, sessions, owner, n=4)
        receipt = await t.enqueue(owner, cid, request(manifest, 0), key="turn")
        await finish(sessions, owner, cid, receipt)
        await start(Revisions(sessions), owner, cid, manifest)
        lease = await s.claim()
        for _ in range(4):
            await s.run_once(lease, adapter)
            async with sessions() as db:
                op = await db.get(FreeCourseOperation, lease.fence.operation_id)
                if op.state == "succeeded":
                    break
        async with sessions() as db:
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] > manifest[
                "version"
            ]
        old = await t.read(owner, cid, UUID(receipt["turn_id"]))
        assert old["status"] == "ready" and old["binding"]["course_version"] == manifest["version"]
        with pytest.raises(SnapshotError):
            await t.enqueue(owner, cid, request(manifest, 0), key="stale")

    exercise(action)


def test_confirmed_answer_attestation_revocation_invalidates_ready_without_hiding_scene():
    from test_free_course_evidence import attest

    from app.services.free_course_answers import ensure_exercise
    from app.services.free_course_evidence import revoke_exercises

    async def action(s, t, sessions, owner, other):
        cid, manifest, answer, _ = await practice(s, sessions, owner)
        await attest(sessions, owner, cid, answer, "answer_attestation", "trusted-synthetic")
        receipt = await t.enqueue(owner, cid, request(manifest), key="turn")
        await finish(sessions, owner, cid, receipt)
        async with sessions() as db, db.begin():
            await SnapshotRepository(db, owner)._owner_lock()
            exercise_row = await ensure_exercise(
                db, owner, cid, answer, answer["exercise_id"], answer["exercise_version_id"]
            )
            await revoke_exercises(
                db,
                owner,
                cid,
                [exercise_row],
                {"kind": "confirmed_defect", "source": "synthetic independent review"},
            )
        old = await t.read(owner, cid, UUID(receipt["turn_id"]))
        assert old["status"] == "invalidated" and old["markdown"] is None

    exercise(action)


def test_effective_learner_evidence_invalidation_is_rechecked_across_courses():
    from test_free_course_evidence import qualify

    from app.services.free_course_answers import Answers, ensure_exercise
    from app.services.free_course_evidence import revoke_exercises

    async def action(s, t, sessions, owner, other):
        first, _, answer, _ = await practice(s, sessions, owner, create_key="old-course")
        await qualify(sessions, owner, first, answer)
        await Answers(sessions).submit(owner, first, answer, key="independent-first-answer")
        cid, manifest, _, _ = await practice(s, sessions, owner, create_key="new-course")
        receipt = await t.enqueue(owner, cid, request(manifest), key="turn")
        async with sessions() as db:
            turn = await db.get(FreeCourseTutorTurn, UUID(receipt["turn_id"]))
            assert turn.context_json["learner"]["effective_mastery"]
            assert turn.sources_json["evidence_ids"]
        await finish(sessions, owner, cid, receipt)
        async with sessions() as db, db.begin():
            await SnapshotRepository(db, owner)._owner_lock()
            exercise_row = await ensure_exercise(
                db, owner, first, answer, answer["exercise_id"], answer["exercise_version_id"]
            )
            await revoke_exercises(db, owner, first, [exercise_row], {"kind": "confirmed_defect"})
        assert (await t.read(owner, cid, UUID(receipt["turn_id"])))["status"] == "invalidated"

    exercise(action)


def test_audit_data_blocks_downgrade_and_empty_database_roundtrips():
    async def action(s, t, sessions, owner, other):
        cid, manifest, _ = await setup(s, sessions, owner, n=2)
        await t.enqueue(owner, cid, request(manifest), key="turn")
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0046_free_course_evidence"],
            cwd=ROOT / "backend",
            env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode != 0 and "Tutor audit data exists" in result.stderr

    exercise(action)
    for target in ["0046_free_course_evidence", "head"]:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade" if target != "head" else "upgrade",
                target,
            ],
            cwd=ROOT / "backend",
            env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
