"""Real PG/HTTP owner record indexes, synthetic course fixtures and zero real Provider."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_free_course_answers import practice
from test_free_course_api import api as _api
from test_free_course_api import dbwork, ready
from test_free_course_api import migrate as migrate  # noqa: F401
from test_free_course_tutor_context import request
from test_free_course_tutor_scheduler import FakeTutor

from app.main import app
from app.models.free_course_quality import FreeCourseFeedback
from app.services.free_course_contract import validate
from app.services.free_course_records import MODELS
from app.services.free_course_scheduler import Reply, Scheduler
from app.services.free_course_tutor_scheduler import TutorScheduler

api = _api


def report_body(body):
    return {
        **{k: body[k] for k in ["course_version", "scene_id", "scene_version_id"]},
        "anchor_id": "e",
        "exercise_id": body["exercise_id"],
        "exercise_version_id": body["exercise_version_id"],
        "description": "TEST_ONLY private student feedback",
    }


def new_ready(owner):
    async def action(sessions):
        return await practice(
            Scheduler(sessions, graph_version="mvp-0.2.0"), sessions, owner, create_key=str(uuid4())
        )

    return dbwork(action)


def test_auth_required_kind_limits_and_uniform_missing_course(api):
    client, owner, _ = api()
    other, _, _ = api()
    cid, _, _, _ = ready(owner)
    url = f"/api/free-courses/{cid}/records"
    with TestClient(app, base_url="https://testserver") as noauth:
        assert noauth.get(url, params={"kind": "attempt"}).status_code == 401
    for params in [
        {},
        {"kind": "bad"},
        {"kind": "attempt", "limit": 0},
        {"kind": "attempt", "limit": 51},
        {"kind": "attempt", "before_id": "bad"},
    ]:
        assert client.get(url, params=params).status_code == 422
    foreign = other.get(url, params={"kind": "attempt"})
    missing = other.get(f"/api/free-courses/{uuid4()}/records", params={"kind": "attempt"})
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["code"] == missing.json()["code"] == "NOT_FOUND"
    for kind in ["attempt", "feedback", "tutor"]:
        empty = client.get(url, params={"kind": kind})
        assert empty.status_code == 200 and empty.json()["items"] == []
        assert empty.json()["next_before_id"] is None
        assert empty.headers["cache-control"] == "no-store"
        validate("RecordPage", empty.json())


def test_all_record_kinds_are_only_refs_and_readable_in_catalog_mode(api, monkeypatch):
    client, owner, headers = api()
    cid, manifest, body, _ = ready(owner)
    root = f"/api/free-courses/{cid}"
    aid = client.post(root + "/attempts", json=body, headers=headers).json()["attempt_id"]
    fid = client.post(root + "/feedback", json=report_body(body), headers=headers).json()[
        "feedback_id"
    ]
    tutor = client.post(root + "/tutor-turns", json=request(manifest), headers=headers)
    assert tutor.status_code == 202, tutor.text
    tid = tutor.json()["turn_id"]
    oid = tutor.json()["operation_id"]
    assert (
        client.post(root + f"/operations/{oid}/cancel", json={}, headers=headers).status_code == 200
    )

    async def reconcile(sessions):
        await TutorScheduler(sessions).reconcile()

    dbwork(reconcile)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    expected = {"attempt": aid, "feedback": fid, "tutor": tid, "operation": oid}
    for kind, identity in expected.items():
        result = client.get(root + "/records", params={"kind": kind})
        assert result.status_code == 200, result.text
        validate("RecordPage", result.json())
        assert identity in [r["record_id"] for r in result.json()["items"]]
        for row in result.json()["items"]:
            assert set(row) == {"record_id", "created_at"}
        assert "private student" not in result.text and "answers" not in result.text
    assert client.get(root + f"/operations/{oid}").json()["state"] == "cancelled"
    assert client.get(root + f"/attempts/{aid}").json()["answers"] == body["answers"]
    assert client.get(root + f"/feedback/{fid}").json()["status"] == "pending"
    assert client.get(root + f"/tutor-turns/{tid}").json()["status"] == "cancelled"


def test_stable_same_timestamp_pagination_and_cursor_scope(api):
    client, owner, _ = api()
    cid, manifest, body, _ = ready(owner)
    cid2, _, _, _ = new_ready(owner)
    other, other_owner, other_headers = api()
    other_cid, _, other_body, _ = ready(other_owner)
    foreign_id = other.post(
        f"/api/free-courses/{other_cid}/feedback",
        json=report_body(other_body),
        headers=other_headers,
    ).json()["feedback_id"]
    ids = [uuid4() for _ in range(5)]

    async def insert(sessions):
        # Explicit immutable synthetic feedback facts; use normal insert, never rewrite history.
        async with sessions() as db:
            db.add_all(
                [
                    FreeCourseFeedback(
                        id=identity,
                        user_id=owner,
                        course_id=cid,
                        course_version_id=UUID(manifest["id"]),
                        scene_version_id=UUID(body["scene_version_id"]),
                        location_json=report_body(body),
                        description="TEST_ONLY body excluded",
                        created_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
                    )
                    for identity in ids
                ]
            )
            await db.commit()

    dbwork(insert)
    root = f"/api/free-courses/{cid}/records"
    found = []
    cursor = None
    for _ in range(3):
        result = client.get(
            root,
            params={"kind": "feedback", "limit": 2, **({"before_id": cursor} if cursor else {})},
        )
        assert result.status_code == 200, result.text
        page = result.json()
        found.extend(UUID(r["record_id"]) for r in page["items"])
        cursor = page["next_before_id"]
    assert found == sorted(ids, reverse=True) and cursor is None
    assert (
        client.get(root, params={"kind": "feedback", "before_id": str(found[-1])}).json()["items"]
        == []
    )
    for url, kind, identity in [
        (root, "feedback", str(uuid4())),
        (root, "feedback", foreign_id),
        (f"/api/free-courses/{cid2}/records", "feedback", str(ids[0])),
        (root, "attempt", str(ids[0])),
    ]:
        response = client.get(url, params={"kind": kind, "before_id": identity})
        assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"


def test_failed_unknown_operation_index_survives_and_gets_do_not_write(api):
    client, owner, headers = api()
    cid, manifest, _, _ = ready(owner)
    root = f"/api/free-courses/{cid}"
    receipt = client.post(root + "/tutor-turns", json=request(manifest), headers=headers).json()

    async def fail(sessions):
        scheduler = TutorScheduler(sessions)
        lease = await scheduler.claim()
        assert lease
        transport = FakeTutor(Reply("unknown", None))
        await scheduler.run_once(lease, transport)
        assert len(transport.calls) == 1

    dbwork(fail)
    op = client.get(root + "/operations/" + receipt["operation_id"]).json()
    assert op["state"] == "failed" and op["budget"]["usage_unknown"]

    async def counts(sessions):
        async with sessions() as db:
            return [
                await db.scalar(select(func.count()).select_from(m).where(m.user_id == owner))
                for m in MODELS.values()
            ]

    before = dbwork(counts)
    for _ in range(2):
        page = client.get(root + "/records", params={"kind": "operation"}).json()
        assert receipt["operation_id"] in [r["record_id"] for r in page["items"]]
    assert dbwork(counts) == before
