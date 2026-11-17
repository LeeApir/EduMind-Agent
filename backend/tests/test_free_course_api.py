"""Isolated authenticated free-course API/SSE E2E with zero-Provider scheduling."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_free_course_answers import practice
from test_free_course_feedback import applied, draft
from test_free_course_scheduler import GOAL, PROOF, FakeAdapter
from test_free_scene_generation import response

from app.core.database import create_database_engine
from app.main import app
from app.models.free_course_writes import FreeCourseOperation
from app.services.free_course_contract import CONTRACT, validate
from app.services.free_course_quality import Maintenance, local_authority
from app.services.free_course_scheduler import Reply, Scheduler

ROOT = Path(__file__).resolve().parents[2]


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value
    parsed = make_url(value)
    assert (
        parsed.host == "127.0.0.1"
        and parsed.port == 15437
        and (parsed.database or "").startswith("edumind_catalog_p15_t020_")
    )
    return value


@pytest.fixture(scope="module", autouse=True)
def migrate():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", database_url())
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *a, **k: pytest.fail("No real Provider construction authorized"),
    )
    owners = []
    clients = []

    def guest():
        client = TestClient(app, base_url="https://testserver")
        created = client.post("/api/auth/guest")
        assert created.status_code == 201
        owner = UUID(created.json()["user"]["id"])
        owners.append(owner)
        clients.append(client)
        csrf = created.json()["csrf_token"]
        return client, owner, {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())}

    yield guest

    async def cleanup():
        engine = create_database_engine(database_url())
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE free_course_capacity SET state='free',user_id=NULL,course_id=NULL,"
                        "operation_id=NULL,epoch=NULL,expires_at=NULL,pending_attempt_id=NULL"
                    )
                )
                for owner in owners:
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), dict(u=owner))
        finally:
            await engine.dispose()

    for c in clients:
        c.close()
    asyncio.run(cleanup())


def dbwork(action):
    async def run():
        engine = create_database_engine(database_url())
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            return await action(sessions)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def ready(owner):
    async def action(sessions):
        return await practice(Scheduler(sessions, graph_version="mvp-0.2.0"), sessions, owner)

    return dbwork(action)


def test_create_read_mode_owner_csrf_and_idempotency(api, monkeypatch):
    client, owner, headers = api()
    other, _, other_headers = api()
    noauth = TestClient(app, base_url="https://testserver")
    assert noauth.get("/api/free-courses").status_code == 401
    noauth.close()
    assert client.post("/api/free-courses", json={"goal": GOAL}).status_code == 403
    wrong = {**headers, "Origin": "https://evil.invalid"}
    assert client.post("/api/free-courses", json={"goal": GOAL}, headers=wrong).status_code == 403
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    blocked = client.post("/api/free-courses", json={"goal": GOAL}, headers=headers)
    assert blocked.status_code == 409 and blocked.json()["code"] == "FREE_COURSE_DISABLED"
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    created = client.post(
        "/api/free-courses", json={"goal": GOAL, "code_language": None}, headers=headers
    )
    assert created.status_code == 201
    validate("CreatedCourse", created.json())
    assert (
        client.post(
            "/api/free-courses", json={"goal": GOAL, "code_language": None}, headers=headers
        ).json()
        == created.json()
    )
    assert (
        client.post("/api/free-courses", json={"goal": "changed"}, headers=headers).status_code
        == 409
    )
    cid = created.json()["course_id"]
    oid = created.json()["operation_id"]
    url = f"/api/free-courses/{cid}"
    read = client.get(url)
    assert read.status_code == 200
    validate("Course", read.json())
    assert (
        read.json()["head"] is None
        and read.json()["endorsement"] == "unendorsed"
        and read.json()["code_language"] is None
    )
    assert read.headers["cache-control"] == "no-store"
    assert other.get(url).status_code == 404
    assert other.get(f"{url}/operations/{oid}").status_code == 404
    assert (
        other.post(f"{url}/operations/{oid}/cancel", json={}, headers=other_headers).status_code
        == 404
    )
    listing = client.get("/api/free-courses").json()
    validate("CourseList", listing)
    assert (
        listing["items"][0]["course_id"] == cid
        and other.get("/api/free-courses").json()["items"] == []
    )
    assert (
        client.post(
            "/api/free-courses",
            json={"goal": GOAL, "published": True},
            headers={**headers, "Idempotency-Key": "unknown-field"},
        ).status_code
        == 422
    )


def test_draft_scene_answers_feedback_and_no_publishing_privilege(api, monkeypatch):
    client, owner, headers = api()
    other, _, other_headers = api()
    cid, manifest, body, a = ready(owner)
    url = f"/api/free-courses/{cid}"
    read = client.get(url)
    assert read.status_code == 200
    validate("Course", read.json())
    assert read.json()["head"]["version"] == 3 and read.json()["course_kind"] == "ai_draft"
    head = client.get(f"{url}/versions/3")
    validate("Manifest", head.json())
    scene = client.get(f"{url}/versions/3/scenes/{body['scene_id']}")
    assert scene.status_code == 200
    validate("SceneProjection", scene.json())
    assert scene.json()["blocks"][1]["exercise_version_id"] == body["exercise_version_id"]
    assert (
        "answer_key" not in scene.text
        and "solution" not in scene.text
        and "digest" not in scene.text
    )
    assert client.get(f"/api/learning-units/{cid}").status_code == 404
    assert client.post(f"{url}/publish", json={}, headers=headers).status_code == 404
    attempt = client.post(f"{url}/attempts", json=body, headers=headers)
    assert attempt.status_code == 201
    validate("AttemptReceipt", attempt.json())
    aid = attempt.json()["attempt_id"]
    read = client.get(f"{url}/attempts/{aid}")
    validate("Attempt", read.json())
    assert (
        read.json()["reliability"] == "provisional"
        and read.json()["mastery_effect"] == "course_only"
    )
    assert other.get(f"{url}/attempts/{aid}").status_code == 404
    assert other.post(f"{url}/attempts", json=body, headers=other_headers).status_code == 404
    feedback = dict(
        **{k: body[k] for k in ["course_version", "scene_id", "scene_version_id"]},
        anchor_id="e",
        exercise_id=body["exercise_id"],
        exercise_version_id=body["exercise_version_id"],
        description="请核对这个准确版本的答案",
    )
    report = client.post(f"{url}/feedback", json=feedback, headers=headers)
    assert report.status_code == 201
    fid = report.json()["feedback_id"]
    assert client.get(f"{url}/feedback/{fid}").json()["status"] == "pending"
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    assert (
        client.get(url).status_code == 200
        and client.get(f"{url}/attempts/{aid}").status_code == 200
    )
    assert client.post(f"{url}/feedback", json=feedback, headers=headers).json() == report.json()
    assert (
        client.post(f"{url}/attempts", json=body, headers=headers).json()["code"]
        == "FREE_COURSE_DISABLED"
    )

    def confirm(sessions):
        d = draft(cid, manifest, index=0)
        d.update(
            scope="exercise",
            exercise_id=body["exercise_id"],
            exercise_version_id=body["exercise_version_id"],
        )
        return applied(Maintenance(sessions, local_authority()), owner, d)

    dbwork(confirm)
    scene = client.get(f"{url}/versions/3/scenes/{body['scene_id']}")
    assert scene.status_code == 200
    validate("SceneProjection", scene.json())
    assert (
        scene.json()["blocks"][1]["kind"] == "exercise_unavailable"
        and "items" not in scene.json()["blocks"][1]
    )
    old = client.get(f"{url}/attempts/{aid}").json()
    assert (
        old["answers"] == body["answers"]
        and old["comparison_score"] is None
        and not old["question_results"]
    )
    assert client.get(f"{url}/feedback/{fid}").json()["status"] == "confirmed"


def test_operations_revision_and_stale_head_are_exact(api):
    client, owner, headers = api()
    other, _, other_headers = api()
    cid, old, body, a = ready(owner)
    url = f"/api/free-courses/{cid}"
    impact = client.get(
        f"{url}/impact", params=dict(kind="revise_scene", base_version=3, scene_id=body["scene_id"])
    )
    assert impact.status_code == 200
    validate("Impact", impact.json())
    payload = dict(
        kind="revise_scene",
        expected_head_version=3,
        scene_id=body["scene_id"],
        instruction="明确说明原题条件",
        impact_digest=impact.json()["impact_digest"],
    )
    operation = client.post(f"{url}/operations", json=payload, headers=headers)
    assert operation.status_code == 202
    validate("AcceptedOperation", operation.json())
    assert (
        client.post(f"{url}/operations", json=payload, headers=headers).json() == operation.json()
    )
    oid = operation.json()["operation_id"]
    assert client.get(f"{url}/operations/{oid}").json()["state"] == "queued"
    assert other.post(f"{url}/operations", json=payload, headers=other_headers).status_code == 404

    async def generate(sessions):
        scheduler = Scheduler(sessions)
        lease = await scheduler.claim()
        adapter = FakeAdapter(
            [
                Reply("complete_response", PROOF, response(["text", "exercise"]), 100, 100)
                for _ in range(2)
            ]
        )
        for _ in range(3):
            await scheduler.run_once(lease, adapter)

    dbwork(generate)
    op = client.get(f"{url}/operations/{oid}")
    assert op.status_code == 200
    validate("Operation", op.json())
    assert op.json()["state"] == "succeeded"
    assert (
        client.get(url).json()["head"]["version"] == 4
        and client.get(f"{url}/versions/3").status_code == 200
    )
    stale = client.post(
        f"{url}/attempts", json=body, headers={**headers, "Idempotency-Key": "stale-attempt"}
    )
    assert stale.status_code == 409 and stale.json()["code"] == "STALE_COURSE_VERSION"
    assert (
        client.post(
            f"{url}/operations", json={**payload, "expected_head_version": 4}, headers=headers
        ).status_code
        == 409
    )


def test_cancel_resume_clarify_guard_and_catalog_read_only_recovery(api, monkeypatch):
    client, owner, headers = api()
    created = client.post("/api/free-courses", json=dict(goal=GOAL), headers=headers).json()
    cid = created["course_id"]
    oid = created["operation_id"]
    url = f"/api/free-courses/{cid}"
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    cancel = client.post(f"{url}/operations/{oid}/cancel", json={}, headers=headers)
    assert cancel.status_code == 200 and cancel.json()["state"] == "cancel_requested"
    assert (
        client.post(f"{url}/operations/{oid}/cancel", json={}, headers=headers).json()
        == cancel.json()
    )

    async def reconcile(sessions):
        await Scheduler(sessions).reconcile()

    dbwork(reconcile)
    assert client.get(f"{url}/operations/{oid}").json()["state"] == "cancelled"
    resume = dict(kind="resume", expected_head_version=None, source_operation_id=oid)
    assert (
        client.post(
            f"{url}/operations", json=resume, headers={**headers, "Idempotency-Key": "resume"}
        ).json()["code"]
        == "FREE_COURSE_DISABLED"
    )
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    resumed = client.post(
        f"{url}/operations", json=resume, headers={**headers, "Idempotency-Key": "resume"}
    )
    assert resumed.status_code == 202 and resumed.json()["operation_id"] != oid
    assert (
        client.post(
            f"{url}/operations", json=dict(kind="resume", source_operation_id=oid), headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{url}/operations",
            json=dict(
                kind="clarify",
                expected_head_version=None,
                source_operation_id=oid,
                supplement="补充要求",
            ),
            headers={**headers, "Idempotency-Key": "clarify"},
        ).status_code
        == 409
    )


def test_sse_replay_order_reconnect_terminal_204_and_bad_cursor(api):
    client, owner, headers = api()
    other, _, _ = api()
    cid, manifest, body, a = ready(owner)
    url = f"/api/free-courses/{cid}"

    async def operation_id(sessions):
        async with sessions() as db:
            return await db.scalar(
                select(FreeCourseOperation.id).where(FreeCourseOperation.course_id == cid)
            )

    oid = dbwork(operation_id)
    stream = f"{url}/operations/{oid}/events"
    first = client.get(stream)
    assert first.status_code == 200 and first.headers["cache-control"] == "no-store"
    assert first.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in first.text.splitlines() if line.startswith("data: ")]
    assert events and events[-1]["type"] == "done"
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert first.text.count("event: first_scene_ready") == 1
    for e in events:
        validate("Event", e)
    for secret in ["answer_key", "solution", "lease_token", "messages", "input_snapshot"]:
        assert secret not in first.text
    last = events[-1]["seq"]
    mid = events[len(events) // 2]["seq"]
    reconnect = client.get(stream, headers={"Last-Event-ID": str(mid)})
    replay = [
        json.loads(line[6:]) for line in reconnect.text.splitlines() if line.startswith("data: ")
    ]
    assert replay == [e for e in events if e["seq"] > mid]
    assert client.get(stream, params={"after": last}).status_code == 204
    assert client.get(stream, params={"after": last + 1}).status_code == 409
    assert (
        client.get(stream, params={"after": 1}, headers={"Last-Event-ID": "2"}).status_code == 422
    )
    for value in ["-1", "abc", "1.5"]:
        assert client.get(stream, headers={"Last-Event-ID": value}).status_code == 422
    assert other.get(stream).status_code == 404


def test_pagination_openapi_contract_and_disabled_surface(api):
    client, owner, headers = api()
    cid, manifest, body, a = ready(owner)
    for i in range(2):
        created = client.post(
            "/api/free-courses",
            json=dict(goal=GOAL),
            headers={**headers, "Idempotency-Key": f"course-{i}"},
        )
        assert created.status_code == 201
        data = created.json()
        assert (
            client.post(
                f"/api/free-courses/{data['course_id']}/operations/{data['operation_id']}/cancel",
                json={},
                headers=headers,
            ).status_code
            == 200
        )

        async def reconcile(sessions):
            await Scheduler(sessions).reconcile()

        dbwork(reconcile)
    one = client.get("/api/free-courses", params={"limit": 2}).json()
    validate("CourseList", one)
    two = client.get("/api/free-courses", params={"limit": 2, "cursor": one["next_cursor"]}).json()
    assert len(one["items"]) == 2 and len(two["items"]) == 1 and two["next_cursor"] is None
    assert len({i["course_id"] for i in one["items"] + two["items"]}) == 3
    assert client.get("/api/free-courses", params={"cursor": "bad"}).status_code == 422
    url = f"/api/free-courses/{cid}"
    versions = client.get(f"{url}/versions", params={"limit": 2}).json()
    validate("VersionList", versions)
    page = client.get(
        f"{url}/versions", params={"limit": 2, "cursor": versions["next_cursor"]}
    ).json()
    assert [v["version"] for v in versions["items"] + page["items"]] == [3, 2, 1]
    spec = client.get("/openapi.json").json()
    for path, methods in CONTRACT["paths"].items():
        assert path in spec["paths"]
        assert set(spec["paths"][path]) == set(methods)
        for method, value in methods.items():
            assert spec["paths"][path][method]["responses"] == json.loads(
                json.dumps(value["responses"]).replace(
                    "#/components/schemas/", "#/components/schemas/FreeCourse"
                )
            )
    assert "/api/free-courses/{course_id}/tutor-turns" in spec["paths"]
    assert "/api/free-courses/{course_id}/tutor-turns/{turn_id}" in spec["paths"]
    assert client.post(f"{url}/attestations", json={}, headers=headers).status_code == 404
    assert client.post(f"{url}/quality-decisions", json={}, headers=headers).status_code == 404


def test_sse_capacity_and_revoked_session_stop_without_generation(api, monkeypatch):
    from app.api.free_courses import raw_event_frames
    from app.core.auth import token_hash
    from app.models.auth import GuestSessionRecord

    client, owner, headers = api()
    cid, manifest, body, a = ready(owner)

    async def find(sessions):
        async with sessions() as db:
            return await db.scalar(
                select(FreeCourseOperation.id).where(FreeCourseOperation.course_id == cid)
            )

    oid = dbwork(find)

    class Full:
        def acquire(self, *, blocking):
            return False

    monkeypatch.setattr("app.api.free_courses.STREAM_LIMIT", Full())
    rejected = client.get(f"/api/free-courses/{cid}/operations/{oid}/events")
    assert rejected.status_code == 503 and rejected.json()["code"] == "STREAM_CAPACITY"
    token = token_hash(client.cookies["edumind_session"])

    class Connected:
        async def is_disconnected(self):
            return False

    async def revoked(sessions):
        async with sessions() as db, db.begin():
            record = await db.get(GuestSessionRecord, token)
            await db.delete(record)
        return [
            frame
            async for frame in raw_event_frames(Connected(), sessions, owner, token, cid, oid, 0)
        ]

    assert dbwork(revoked) == []
    assert client.get(f"/api/free-courses/{cid}").status_code == 401
