"""Atomic incremental private learning visibility in actual PG; no Provider/runtime opening."""

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
from sqlalchemy.ext.asyncio import AsyncSession
from test_free_course_planning import candidate
from test_free_scene_generation import Gateway, authorize, response

from app.agents.free_scene_generation import generate_once
from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course import FreeCourseSceneVersion
from app.models.free_course_progress import FreeCourseEvent, FreeCourseStep
from app.models.free_course_writes import FreeCourseOperation
from app.services import free_scene_availability as availability
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, WriteFence
from app.services.free_scene_generation import load_inputs, persist_outcome
from app.services.free_scene_validation import validate_candidate

ROOT = Path(__file__).resolve().parents[2]
GOAL = "数组与单链表的学习和练习"


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value, "Actual isolated PG required; no skip"
    parsed = make_url(value)
    assert parsed.host == "127.0.0.1" and parsed.port == 15437
    assert (parsed.database or "").startswith("edumind_catalog_p15_t013_")
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
        owners = [uuid4(), uuid4()]
        try:
            async with AsyncSession(engine) as db:
                db.add_all([User(id=u, is_guest=True) for u in owners])
                await db.commit()
            await action(engine, *owners)
        finally:
            async with engine.begin() as conn:
                for u in owners:
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": u})
            await engine.dispose()

    asyncio.run(run())


async def setup(db, owner, n=4):
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(GOAL, key="create")
    cid = UUID(created["course_id"])
    fence = await repo.acquire_write_fence(cid, UUID(created["operation_id"]))
    plan = candidate(n, GOAL)["plan"]
    for s in plan["scenes"]:
        s["forms"] = ["text", "code", "exercise", "visualization"]
    if n == 4:
        plan["scenes"][3]["depends_on"] = []
    saved = await repo.store_plan(cid, fence, expected_head=None, key="plan", candidate=plan)
    pid = UUID(saved["plan_id"])
    stored = await repo.get_plan(cid, pid)
    outlined = await availability.commit_outline(
        db, owner, cid, fence, plan_id=pid, key="outline", graph_version="mvp-0.2.0"
    )
    assert (
        await availability.commit_outline(
            db, owner, cid, fence, plan_id=pid, key="outline", graph_version="mvp-0.2.0"
        )
        == outlined
    )
    await db.commit()
    return repo, cid, fence, pid, [UUID(s["scene_id"]) for s in stored["scenes"]]


async def make_validation(db, owner, cid, fence, pid, sid, head, raw=None):
    data = await load_inputs(
        db, owner, cid, fence.operation_id, plan_id=pid, scene_id=sid, expected_head=head
    )
    await db.commit()  # No transaction/owner lock spans the injected Gateway call.
    g = Gateway(raw)
    outcome = await generate_once(g, data, authorize_send=authorize)
    saved = await persist_outcome(
        db, owner, cid, fence, call_key=f"primary-{sid}-{head}", inputs=data, outcome=outcome
    )
    checked = await validate_candidate(db, owner, cid, fence, result_id=UUID(saved["result_id"]))
    await db.commit()
    return UUID(checked["validation_id"])


def test_first_scene_then_independent_append_and_explicit_failed_dependency():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes = await setup(db, owner)
            initial = await availability.read_availability(db, owner, cid, version=1)
            assert initial["ready_count"] == 0 and initial["all_scenes_ready"] is False
            assert [
                e["type"]
                for e in await availability.read_events(db, owner, cid, fence.operation_id)
            ] == ["outline_ready"]
            with pytest.raises(SnapshotError, match="SCENE_NOT_READY"):
                await availability.read_ready_scene(db, owner, cid, version=1, scene_id=scenes[0])
            vid = await make_validation(db, owner, cid, fence, pid, scenes[0], 1)
            saved = await availability.commit_scene(
                db, owner, cid, fence, validation_id=vid, expected_head=1, key="first"
            )
            await db.commit()
            current = await availability.read_availability(db, owner, cid, version=2)
            assert current["ready_count"] == 1 and not current["all_scenes_ready"]
            assert (await availability.read_availability(db, owner, cid, version=1))[
                "ready_count"
            ] == 0
            public = await availability.read_ready_scene(
                db, owner, cid, version=2, scene_id=scenes[0]
            )
            assert "answer_key" not in json.dumps(public) and "solution" not in json.dumps(public)
            public["blocks"][0]["markdown"] = "modified copy"
            assert (
                await availability.read_ready_scene(db, owner, cid, version=2, scene_id=scenes[0])
            )["blocks"][0]["markdown"] != "modified copy"
            await availability.fail_scene(
                db,
                owner,
                cid,
                fence,
                scene_id=scenes[1],
                expected_head=2,
                reason_code="SCHEMA_INVALID",
                key="failure",
            )
            await db.commit()
            current = await availability.read_availability(db, owner, cid, version=2)
            assert [s["generation_state"] for s in current["scenes"]] == [
                "ready",
                "failed",
                "blocked_dependency",
                "pending",
            ]
            assert current["ready_count"] == 1
            with pytest.raises(SnapshotError, match="DEPENDENCY_UNAVAILABLE"):
                await make_validation(db, owner, cid, fence, pid, scenes[2], 2)
            independent = await make_validation(db, owner, cid, fence, pid, scenes[3], 2)
            await availability.commit_scene(
                db, owner, cid, fence, validation_id=independent, expected_head=2, key="independent"
            )
            await db.commit()
            assert (await availability.read_availability(db, owner, cid, version=3))[
                "ready_count"
            ] == 2
            assert (await db.get(FreeCourseOperation, fence.operation_id)).state == "running"
            assert (
                await availability.commit_scene(
                    db, owner, cid, fence, validation_id=vid, expected_head=1, key="first"
                )
                == saved
            )
            await db.commit()
            assert (await repo.get_course(cid))["head_version"] == 3
            events = await availability.read_events(db, owner, cid, fence.operation_id)
            assert [e["seq"] for e in events] == list(range(1, 6))
            assert [e["type"] for e in events] == [
                "outline_ready",
                "scene_ready",
                "first_scene_ready",
                "error",
                "scene_ready",
            ]
            assert (
                len(await availability.read_events(db, owner, cid, fence.operation_id, after=3))
                == 2
            )
            assert await availability.read_events(db, owner, cid, fence.operation_id, after=5) == []
            for e in events:
                Draft202012Validator(availability.EVENT_SCHEMA).validate(e)
            assert "answer_key" not in json.dumps(events) and "markdown" not in json.dumps(events)

    exercise(action)


def test_all_scenes_ready_does_not_fake_operation_completion():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes = await setup(db, owner)
            for i, sid in enumerate(scenes):
                vid = await make_validation(db, owner, cid, fence, pid, sid, i + 1)
                await availability.commit_scene(
                    db, owner, cid, fence, validation_id=vid, expected_head=i + 1, key=f"ready-{i}"
                )
                await db.commit()
            state = await availability.read_availability(db, owner, cid, version=5)
            assert state["all_scenes_ready"] is True and state["ready_count"] == 4
            events = await availability.read_events(db, owner, cid, fence.operation_id)
            assert sum(e["type"] == "first_scene_ready" for e in events) == 1
            assert not any(e["type"] == "done" for e in events)
            assert (await db.get(FreeCourseOperation, fence.operation_id)).state == "running"

    exercise(action)


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_replay_or_stale_candidate_has_one_atomic_winner(same_key):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            _, cid, fence, pid, scenes = await setup(db, owner)
            vid = await make_validation(db, owner, cid, fence, pid, scenes[0], 1)

        async def worker(i):
            async with AsyncSession(engine) as db:
                result = await availability.commit_scene(
                    db,
                    owner,
                    cid,
                    fence,
                    validation_id=vid,
                    expected_head=1,
                    key="same" if same_key else f"key-{i}",
                )
                await db.commit()
                return result

        results = await asyncio.gather(worker(0), worker(1), return_exceptions=True)
        if same_key:
            assert results[0] == results[1] and isinstance(results[0], dict)
        else:
            assert (
                sum(isinstance(r, SnapshotError) for r in results) == 1
                and sum(isinstance(r, dict) for r in results) == 1
            )
        async with AsyncSession(engine) as db:
            assert await db.scalar(select(func.count()).select_from(FreeCourseSceneVersion)) == 1
            assert await db.scalar(select(func.count()).select_from(FreeCourseEvent)) == 3
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == 2

    exercise(action)


@pytest.mark.parametrize("failure", ["manifest", "first_event", "receipt", "lease_expires"])
def test_failure_anywhere_rolls_back_body_head_ready_and_events(monkeypatch, failure):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes = await setup(db, owner)
            vid = await make_validation(db, owner, cid, fence, pid, scenes[0], 1)
            if failure == "manifest":

                async def fail(*_a, **_k):
                    raise RuntimeError("synthetic manifest failure")

                monkeypatch.setattr(SnapshotRepository, "commit_manifest", fail)
            elif failure == "receipt":
                original = SnapshotRepository._record

                async def fail(self, course_id, route, *args):
                    if route.startswith("availability:scene"):
                        raise RuntimeError("synthetic receipt failure")
                    return await original(self, course_id, route, *args)

                monkeypatch.setattr(SnapshotRepository, "_record", fail)
            else:
                original = availability._emit

                async def fail(db, owner, cid, fence, kind, *args):
                    if kind == "first_scene_ready":
                        if failure == "first_event":
                            raise RuntimeError("synthetic event failure")
                        await db.execute(
                            text(
                                "UPDATE free_course_operations SET "
                                "lease_expires_at=now()-interval '1 second' WHERE id=:i"
                            ),
                            {"i": fence.operation_id},
                        )
                    return await original(db, owner, cid, fence, kind, *args)

                monkeypatch.setattr(availability, "_emit", fail)
            with pytest.raises((RuntimeError, SnapshotError)):
                await availability.commit_scene(
                    db, owner, cid, fence, validation_id=vid, expected_head=1, key="first"
                )
            await db.rollback()
            assert (await repo.get_course(cid))["head_version"] == 1
            assert await db.scalar(select(func.count()).select_from(FreeCourseSceneVersion)) == 0
            assert [
                e["type"]
                for e in await availability.read_events(db, owner, cid, fence.operation_id)
            ] == ["outline_ready"]
            assert all(
                s.state == "pending" for s in (await db.scalars(select(FreeCourseStep))).all()
            )

    exercise(action)


def test_uncommitted_ready_is_invisible_to_another_connection():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as writer:
            repo, cid, fence, pid, scenes = await setup(writer, owner)
            vid = await make_validation(writer, owner, cid, fence, pid, scenes[0], 1)
            await availability.commit_scene(
                writer, owner, cid, fence, validation_id=vid, expected_head=1, key="first"
            )
            async with AsyncSession(engine) as observer:
                assert (await SnapshotRepository(observer, owner).get_course(cid))[
                    "head_version"
                ] == 1
                assert (await availability.read_availability(observer, owner, cid, version=1))[
                    "ready_count"
                ] == 0
                assert (
                    len(await availability.read_events(observer, owner, cid, fence.operation_id))
                    == 1
                )
            await writer.commit()
        async with AsyncSession(engine) as observer:
            assert (await availability.read_availability(observer, owner, cid, version=2))[
                "ready_count"
            ] == 1
            assert (
                len(await availability.read_events(observer, owner, cid, fence.operation_id)) == 3
            )

    exercise(action)


@pytest.mark.parametrize(
    "mode",
    ["owner", "wrong_validation", "cancel", "expired", "stale", "new_epoch", "invalid_candidate"],
)
def test_bad_identity_version_or_candidate_cannot_commit_ready(mode):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes = await setup(db, owner)
            raw = response()
            if mode == "invalid_candidate":
                raw["actions"][0]["anchor_id"] = "foreign"
            vid = await make_validation(db, owner, cid, fence, pid, scenes[0], 1, raw)
            if mode == "cancel":
                await db.execute(
                    text("UPDATE free_course_operations SET cancel_requested_at=now() WHERE id=:i"),
                    {"i": fence.operation_id},
                )
            if mode == "expired":
                await db.execute(
                    text(
                        "UPDATE free_course_operations SET "
                        "lease_expires_at=now()-interval '1 second' WHERE id=:i"
                    ),
                    {"i": fence.operation_id},
                )
            if mode == "stale":
                await repo.commit_manifest(
                    cid, fence, expected_head=1, key="next", plan_id=pid, bindings=[None] * 4
                )
            if mode == "new_epoch":
                token = uuid4()
                await db.execute(
                    text(
                        "UPDATE free_course_operations SET lease_epoch=lease_epoch+1,"
                        "lease_token=:token WHERE id=:i"
                    ),
                    {"i": fence.operation_id, "token": token},
                )
                fence = WriteFence(fence.operation_id, fence.epoch + 1, token)
            await db.commit()
            with pytest.raises(SnapshotError):
                await availability.commit_scene(
                    db,
                    other if mode == "owner" else owner,
                    cid,
                    fence,
                    validation_id=uuid4() if mode == "wrong_validation" else vid,
                    expected_head=1,
                    key="first",
                )
            await db.rollback()
            assert await db.scalar(select(func.count()).select_from(FreeCourseSceneVersion)) == 0
            assert len(await availability.read_events(db, owner, cid, fence.operation_id)) == 1
            assert (await repo.get_course(cid))["head_version"] == (2 if mode == "stale" else 1)

    exercise(action)


def test_event_cap_rolls_back_the_entire_first_scene_commit():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes = await setup(db, owner)
            vid = await make_validation(db, owner, cid, fence, pid, scenes[0], 1)
            await repo._owner_lock()
            await repo._course(cid, lock=True)
            await repo._fence(cid, fence)
            manifest = await repo.get_version(cid, 1)
            for _ in range(254):
                await availability._emit(
                    db,
                    owner,
                    cid,
                    fence,
                    "progress",
                    dict(version=1, version_id=manifest["id"]),
                    dict(state="running"),
                )
            await db.commit()
            with pytest.raises(SnapshotError, match="EVENT_LIMIT_EXCEEDED"):
                await availability.commit_scene(
                    db, owner, cid, fence, validation_id=vid, expected_head=1, key="first"
                )
            await db.rollback()
            assert await db.scalar(select(func.count()).select_from(FreeCourseEvent)) == 255
            assert await db.scalar(select(func.count()).select_from(FreeCourseSceneVersion)) == 0
            assert (await repo.get_course(cid))["head_version"] == 1

    exercise(action)


def test_event_guards_replay_cursor_and_owner_rules():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes = await setup(db, owner)
            vid = await make_validation(db, owner, cid, fence, pid, scenes[0], 1)
            await availability.commit_scene(
                db, owner, cid, fence, validation_id=vid, expected_head=1, key="first"
            )
            await db.commit()
            for after in [-1, True, "1"]:
                with pytest.raises(SnapshotError, match="EVENT_CURSOR_INVALID"):
                    await availability.read_events(db, owner, cid, fence.operation_id, after=after)
            with pytest.raises(SnapshotError, match="EVENT_CURSOR_AHEAD"):
                await availability.read_events(db, owner, cid, fence.operation_id, after=4)
            with pytest.raises(SnapshotError, match="NOT_FOUND"):
                await availability.read_events(db, other, cid, fence.operation_id)
            with pytest.raises(SnapshotError, match="NOT_FOUND"):
                await availability.read_ready_scene(db, other, cid, version=2, scene_id=scenes[0])
            events = await availability.read_events(db, owner, cid, fence.operation_id)
            events[0]["payload"]["injected"] = "bad"
            assert (await availability.read_events(db, owner, cid, fence.operation_id))[0][
                "payload"
            ] == {}
            first = await db.scalar(
                select(FreeCourseEvent).where(FreeCourseEvent.event_type == "first_scene_ready")
            )
            for sql in [
                "UPDATE free_course_events SET payload='{}' WHERE id=:i",
                "DELETE FROM free_course_events WHERE id=:i",
            ]:
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await db.execute(text(sql), {"i": first.id})
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    db.add(
                        FreeCourseEvent(
                            user_id=owner,
                            course_id=cid,
                            operation_id=fence.operation_id,
                            seq=5,
                            event_type="progress",
                            course_version_id=first.course_version_id,
                            payload={},
                        )
                    )
                    await db.flush()
            with pytest.raises(DBAPIError):
                async with db.begin_nested():
                    db.add(
                        FreeCourseEvent(
                            user_id=owner,
                            course_id=cid,
                            operation_id=fence.operation_id,
                            seq=4,
                            event_type="first_scene_ready",
                            course_version_id=first.course_version_id,
                            payload=first.payload,
                        )
                    )
                    await db.flush()
        down = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0039_free_scene_actions"],
            cwd=ROOT / "backend",
            env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert down.returncode != 0 and "free course data prevents downgrade" in down.stderr

    exercise(action)


def test_event_schema_is_exact_approved_copy():
    schemas = json.loads((ROOT / "docs/api/phase-1.5-generation.openapi.json").read_text())[
        "components"
    ]["schemas"]
    actual = json.loads(
        json.dumps(availability.EVENT_SCHEMA).replace("#/$defs/", "#/components/schemas/")
    )
    actual.pop("$schema")
    defs = actual.pop("$defs")
    assert actual == schemas["Event"] and defs == dict(EventPayload=schemas["EventPayload"])
