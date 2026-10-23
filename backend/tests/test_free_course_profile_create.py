"""Actual authenticated creation adopts owner profile once; replays never rebind it."""

import json
from uuid import UUID

from sqlalchemy import func, select
from test_free_course_api import api as _api
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate  # noqa: F401
from test_free_course_scheduler import FakeAdapter

from app.models.free_course import FreeCourseRequest
from app.models.free_course_writes import FreeCourseOperation
from app.models.learning import StudentProfile
from app.services.free_course_planning import load_inputs
from app.services.free_course_scheduler import Scheduler

api = _api


async def profile(sessions, owner, version, text):
    async with sessions() as db, db.begin():
        row = StudentProfile(
            user_id=owner,
            version=version,
            merge_rule_version="test-self-report-v1",
            knowledge_base={"self_report": text},
            evidence={
                "knowledge_base": [
                    {
                        "source": "learner_statement",
                        "confidence": 1,
                        "observed_at": "2026-10-23",
                        "profile_version": version,
                    }
                ]
            },
        )
        db.add(row)
        await db.flush()
        return row.id


def test_owner_latest_profile_is_in_real_planning_snapshot_and_replay_is_stable(api):
    client, owner, headers = api()
    _, other, _ = api()

    async def seed(sessions):
        await profile(sessions, owner, 1, "会C循环，尚未学习链表")
        current = await profile(sessions, owner, 2, "会C指针，想理解链表边界")
        await profile(sessions, other, 99, "FOREIGN_OWNER_PRIVATE")
        return current

    pid = dbwork(seed)
    created = client.post("/api/free-courses", json={"goal": "学习单链表"}, headers=headers)
    assert created.status_code == 201, created.text
    cid = UUID(created.json()["course_id"])
    oid = UUID(created.json()["operation_id"])

    async def read(sessions):
        async with sessions() as db:
            return await load_inputs(db, owner, cid, oid)

    frozen = dbwork(read)
    assert frozen["profile_id"] == str(pid) and frozen["profile_version"] == 2
    assert frozen["learner_evidence"]["knowledge_base"] == {
        "self_report": "会C指针，想理解链表边界"
    }
    assert "FOREIGN_OWNER_PRIVATE" not in json.dumps(frozen)

    async def changed(sessions):
        await profile(sessions, owner, 3, "后续用户更正，不改旧请求")

    dbwork(changed)
    replay = client.post("/api/free-courses", json={"goal": "学习单链表"}, headers=headers)
    assert replay.status_code == 201 and replay.json() == created.json()
    assert dbwork(read) == frozen
    conflict = client.post("/api/free-courses", json={"goal": "改成学习数组"}, headers=headers)
    assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    async def execute(sessions):
        scheduler = Scheduler(sessions)
        lease = await scheduler.claim()
        adapter = FakeAdapter()
        await scheduler.run_once(lease, adapter)
        assert len(adapter.calls) == 1
        prompt = json.loads(adapter.calls[0].prompt.messages[1].content)
        assert prompt["profile_id"] == str(pid) and prompt["profile_version"] == 2
        assert prompt["learner_evidence"] == frozen["learner_evidence"]
        async with sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseOperation)
                    .where(FreeCourseOperation.user_id == owner)
                )
                == 1
            )

    dbwork(execute)


def test_unknown_profile_never_borrows_other_owner_and_old_null_replay_stays_null(api):
    client, owner, headers = api()
    _, other, _ = api()

    async def seed(sessions):
        await profile(sessions, other, 1, "他人的学习经历")

    dbwork(seed)
    created = client.post("/api/free-courses", json={"goal": "学习数组"}, headers=headers)
    assert created.status_code == 201

    async def read(sessions):
        async with sessions() as db:
            return await db.scalar(
                select(FreeCourseRequest).where(FreeCourseRequest.user_id == owner)
            )

    before = dbwork(read)
    assert before.profile_id is None and before.evidence_snapshot == {}

    async def late(sessions):
        await profile(sessions, owner, 1, "创建之后才补充")

    dbwork(late)
    assert (
        client.post("/api/free-courses", json={"goal": "学习数组"}, headers=headers).json()
        == created.json()
    )
    after = dbwork(read)
    assert (
        after.profile_id is None and after.profile_version is None and after.evidence_snapshot == {}
    )
