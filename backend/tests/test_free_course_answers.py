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
from test_free_course_feedback import applied, draft
from test_free_course_planning import candidate
from test_free_course_revision import start
from test_free_course_scheduler import GOAL, PROOF, FakeAdapter
from test_free_scene_generation import response

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course_answers import FreeCourseAnswerAttempt, FreeCourseAssessmentExposure
from app.models.learning_state import LearningEvidence
from app.services.free_course_answers import (
    Answers,
    ensure_exercise,
    public_exercise,
    record_exposure,
)
from app.services.free_course_exercise_identity import exercise_identity
from app.services.free_course_quality import (
    Maintenance,
    local_authority,
    validate_schema,
)
from app.services.free_course_recovery import Recovery
from app.services.free_course_revision import Revisions
from app.services.free_course_scheduler import Reply, Scheduler
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository

ROOT = Path(__file__).resolve().parents[2]


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value
    url = make_url(value)
    assert url.host == "127.0.0.1" and url.port == 15437
    assert (url.database or "").startswith("edumind_catalog_p15_t018_")
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


async def practice(s, sessions, owner, *, create_key="create", raw=None):
    created = await s.enqueue(owner, GOAL, key=create_key)
    cid = UUID(created["course_id"])
    plan = candidate(2, GOAL)
    for scene in plan["plan"]["scenes"]:
        scene["forms"] = ["text", "exercise"]
    adapter = FakeAdapter(
        [Reply("complete_response", PROOF, plan, 100, 100)]
        + [
            Reply("complete_response", PROOF, raw or response(["text", "exercise"]), 100, 100)
            for _ in range(2)
        ]
    )
    lease = await s.claim()
    for _ in range(4):
        await s.run_once(lease, adapter)
    async with sessions() as db:
        manifest = await SnapshotRepository(db, owner).get_version(cid, 3)
    item = manifest["scenes"][0]
    eid, evid = exercise_identity(
        owner, cid, UUID(item["scene_id"]), UUID(item["scene_version_id"]), "practice"
    )
    body = dict(
        course_version=3,
        scene_id=item["scene_id"],
        scene_version_id=item["scene_version_id"],
        exercise_id=str(eid),
        exercise_version_id=str(evid),
        answers=[dict(question_id="q0", answer="０"), dict(question_id="q1", answer="  1  ")],
    )
    return cid, manifest, body, adapter


def test_partial_no_answer_then_complete_provisional_and_immutable_receipt():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        answers = Answers(sessions)
        partial = {**body, "answers": body["answers"][:1]}
        first = await answers.submit(owner, cid, partial, key="partial")
        read = await answers.read(owner, cid, UUID(first["attempt_id"]))
        validate_schema("Attempt", read)
        assert (
            read["completeness"] == "incomplete"
            and read["comparison_score"] is None
            and not read["question_results"]
        )
        second = await answers.submit(owner, cid, body, key="complete")
        assert await answers.submit(owner, cid, body, key="complete") == second
        read = await answers.read(owner, cid, UUID(second["attempt_id"]))
        validate_schema("Attempt", read)
        assert (
            read["comparison_score"] == 1
            and read["mastery_effect"] == "course_only"
            and read["reliability"] == "provisional"
        )
        assert read["answers"] == body["answers"] and all(
            q["matches_reference"] for q in read["question_results"]
        )
        async with sessions() as db:
            rows = (
                await db.scalars(
                    select(FreeCourseAnswerAttempt).order_by(FreeCourseAnswerAttempt.created_at)
                )
            ).all()
            assert len(rows) == 2 and rows[1].qualification_json["first_complete"] is True
            assert await db.scalar(select(func.count()).select_from(LearningEvidence)) == 0
            assert (
                await db.scalar(select(func.count()).select_from(FreeCourseAssessmentExposure)) == 1
            )
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await answers.read(other, cid, UUID(second["attempt_id"]))
        with pytest.raises(SnapshotError, match="NOT_FOUND"):
            await answers.submit(other, cid, body, key="complete")
        with pytest.raises(SnapshotError, match="IDEMPOTENCY_CONFLICT"):
            await answers.submit(owner, cid, partial, key="complete")

    exercise(action)


@pytest.mark.parametrize(
    "mode", ["blank", "duplicate", "foreign", "too_long", "score", "wrong_scene", "wrong_exercise"]
)
def test_invalid_submission_rolls_back_without_consuming_first_complete(mode):
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        answers = Answers(sessions)
        if mode == "blank":
            body["answers"] = [dict(question_id="q0", answer="  ")]
        if mode == "duplicate":
            body["answers"] = [body["answers"][0], body["answers"][0]]
        if mode == "foreign":
            body["answers"][0]["question_id"] = "unknown"
        if mode == "too_long":
            body["answers"][0]["answer"] = "x" * 501
        if mode == "score":
            body["score"] = 1
        if mode == "wrong_scene":
            body["scene_id"] = manifest["scenes"][1]["scene_id"]
        if mode == "wrong_exercise":
            body["exercise_version_id"] = str(uuid4())
        with pytest.raises(SnapshotError):
            await answers.submit(owner, cid, body, key="invalid")
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(FreeCourseAnswerAttempt)) == 0
            assert (
                await db.scalar(select(func.count()).select_from(FreeCourseAssessmentExposure)) == 0
            )

    exercise(action)


def test_exposure_and_repeated_completion_do_not_requalify():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        answers = Answers(sessions)
        binding = {k: body[k] for k in ["course_version", "scene_id", "scene_version_id"]}
        async with sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            await repo._course(cid, lock=True)
            e = await ensure_exercise(
                db, owner, cid, binding, body["exercise_id"], body["exercise_version_id"]
            )
            await record_exposure(db, owner, e, "help", binding)
        first = await answers.submit(owner, cid, body, key="first")
        second = await answers.submit(owner, cid, body, key="second")
        async with sessions() as db:
            for x in [first, second]:
                attempt = await db.get(FreeCourseAnswerAttempt, UUID(x["attempt_id"]))
                assert attempt.qualification_json["first_complete"] is False
        assert (await answers.read(owner, cid, UUID(second["attempt_id"])))[
            "reliability"
        ] == "provisional"

    exercise(action)


def test_disabled_attempt_projection_withdraws_answers_but_preserves_raw_and_receipt():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        answers = Answers(sessions)
        receipt = await answers.submit(owner, cid, body, key="first")
        d = draft(cid, manifest, index=0)
        d.update(
            scope="exercise",
            exercise_id=body["exercise_id"],
            exercise_version_id=body["exercise_version_id"],
        )
        await applied(Maintenance(sessions, local_authority()), owner, d)
        assert await answers.submit(owner, cid, body, key="first") == receipt
        with pytest.raises(SnapshotError, match="CONTENT_UNAVAILABLE"):
            await answers.submit(owner, cid, body, key="new")
        read = await answers.read(owner, cid, UUID(receipt["attempt_id"]))
        validate_schema("Attempt", read)
        assert (
            read["answers"] == body["answers"]
            and read["reliability"] == "withdrawn"
            and read["comparison_score"] is None
            and not read["question_results"]
        )
        async with sessions() as db:
            old = await db.get(FreeCourseAnswerAttempt, UUID(receipt["attempt_id"]))
            assert old.feedback_json["comparison_score"] == 1

    exercise(action)


def test_stale_head_rejects_new_attempt_keeps_original_and_copy_identity():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        answers = Answers(sessions)
        receipt = await answers.submit(owner, cid, body, key="old")
        await start(r, owner, cid, manifest, index=1)
        a.replies.append(
            Reply("complete_response", PROOF, response(["text", "exercise"]), 100, 100)
        )
        lease = await s.claim()
        for _ in range(2):
            await s.run_once(lease, a)
        assert (await recovery.read_operation(owner, cid, lease.fence.operation_id))[
            "state"
        ] == "succeeded"
        with pytest.raises(SnapshotError, match="STALE_COURSE_VERSION"):
            await answers.submit(owner, cid, body, key="stale")
        assert await answers.submit(owner, cid, body, key="old") == receipt
        read = await answers.read(owner, cid, UUID(receipt["attempt_id"]))
        assert read["binding"]["course_version"] == 3
        async with sessions() as db:
            current = await SnapshotRepository(db, owner).get_course(cid)
            new = await SnapshotRepository(db, owner).get_version(cid, current["head_version"])
            item = new["scenes"][0]
            raw = await SnapshotRepository(db, owner).get_scene_snapshot(
                cid, new["version"], UUID(item["scene_id"])
            )
        block = raw["content"]["blocks"][1]
        public = public_exercise(
            owner, cid, UUID(item["scene_id"]), UUID(item["scene_version_id"]), block
        )
        validate_schema("ExerciseBlock", public)
        assert (
            public["exercise_id"] == body["exercise_id"]
            and public["exercise_version_id"] != body["exercise_version_id"]
        )
        assert "answer_key" not in json.dumps(public) and "solution" not in json.dumps(public)
        disabled = public_exercise(
            owner, cid, UUID(item["scene_id"]), UUID(item["scene_version_id"]), block, disabled=True
        )
        validate_schema("DisabledExerciseBlock", disabled)

    exercise(action)


def test_concurrent_complete_submissions_consume_one_independent_slot():
    async def action(r, s, recovery, sessions, owner, other):
        cid, manifest, body, a = await practice(s, sessions, owner)
        answers = Answers(sessions)
        receipts = await asyncio.gather(
            *(answers.submit(owner, cid, body, key=f"parallel-{i}") for i in range(2))
        )
        async with sessions() as db:
            attempts = [
                await db.get(FreeCourseAnswerAttempt, UUID(x["attempt_id"])) for x in receipts
            ]
            assert sum(a.qualification_json["first_complete"] for a in attempts) == 1
            assert await db.scalar(select(func.count()).select_from(LearningEvidence)) == 0

    exercise(action)
