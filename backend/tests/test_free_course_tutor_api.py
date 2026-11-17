"""Real authenticated HTTP/SSE with actual PG and explicit synthetic single-Tutor transport."""

import json
from uuid import uuid4

from sqlalchemy import func, select
from test_free_course_api import api as _api
from test_free_course_api import dbwork, ready
from test_free_course_api import migrate as migrate  # noqa: F401
from test_free_course_feedback import applied, draft
from test_free_course_tutor_context import request
from test_free_course_tutor_scheduler import FakeTutor

from app.models.free_course_tutor import FreeCourseTutorTurn
from app.services.free_course_quality import Maintenance, local_authority
from app.services.free_course_tutor_scheduler import TutorScheduler

# Reuse the real isolated HTTP fixture without changing its auth/session semantics.
api = _api


def create(guest):
    client, owner, headers = guest()
    cid, manifest, _, _ = ready(owner)
    body = request(manifest)
    url = f"/api/free-courses/{cid}/tutor-turns"
    result = client.post(url, json=body, headers=headers)
    assert result.status_code == 202, result.text
    return client, owner, headers, cid, manifest, body, result.json()


def complete():
    async def action(sessions):
        scheduler = TutorScheduler(sessions)
        lease = await scheduler.claim()
        assert lease
        adapter = FakeTutor()
        await scheduler.run_once(lease, adapter)
        return len(adapter.calls)

    assert dbwork(action) == 1


def events(response):
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


def test_create_poll_ready_event_replay_and_terminal_cursor_204(api):
    client, owner, headers, cid, manifest, body, receipt = create(api)
    op = f"/api/free-courses/{cid}/operations/{receipt['operation_id']}"
    turn = f"/api/free-courses/{cid}/tutor-turns/{receipt['turn_id']}"
    pending = client.get(op)
    assert pending.status_code == 200 and pending.json()["kind"] == "tutor_turn"
    assert pending.json()["budget"]["attempts_remaining"] == 1
    assert client.get(turn).json()["markdown"] is None
    complete()
    result = client.get(turn)
    assert result.status_code == 200 and result.json()["status"] == "ready"
    assert result.json()["binding"]["course_version"] == manifest["version"]
    assert "补充解释" in result.json()["markdown"]
    assert result.headers["cache-control"] == "no-store"
    streamed = client.get(op + "/events")
    assert streamed.status_code == 200
    replay = events(streamed)
    assert [e["type"] for e in replay] == ["queued", "started", "tutor_ready", "done"]
    assert replay[2]["payload"] == {"turn_id": receipt["turn_id"]}
    assert "补充解释" not in streamed.text and "answer_key" not in streamed.text
    assert client.get(op + "/events?after=4").status_code == 204
    assert client.get(op + "/events", headers={"Last-Event-ID": "4"}).status_code == 204
    assert client.get(op + "/events?after=99").status_code == 409
    assert client.get(op + "/events?after=1", headers={"Last-Event-ID": "2"}).status_code == 422
    assert (
        client.post(f"/api/free-courses/{cid}/tutor-turns", json=body, headers=headers).json()
        == receipt
    )

    async def count(sessions):
        async with sessions() as db:
            return await db.scalar(
                select(func.count())
                .select_from(FreeCourseTutorTurn)
                .where(FreeCourseTutorTurn.course_id == cid)
            )

    assert dbwork(count) == 1


def test_csrf_owner_unknown_fields_and_required_assistance_confirmation(api):
    client, owner, headers = api()
    cid, manifest, _, _ = ready(owner)
    body = request(manifest)
    url = f"/api/free-courses/{cid}/tutor-turns"
    assert client.post(url, json=body).status_code == 403
    assert (
        client.post(
            url, json={**body, "acknowledge_assisted_practice": False}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(url, json={**body, "system_prompt": "bypass"}, headers=headers).status_code
        == 422
    )
    assert client.post(url, json={**body, "course_version": 1}, headers=headers).status_code == 409
    receipt = client.post(url, json=body, headers=headers).json()
    stranger, _, foreign_headers = api()
    assert stranger.get(url + "/" + receipt["turn_id"]).status_code == 404
    assert (
        stranger.get(f"/api/free-courses/{cid}/operations/{receipt['operation_id']}").status_code
        == 404
    )
    assert stranger.post(url, json=body, headers=foreign_headers).status_code == 404
    assert (
        stranger.get(url + "/" + str(uuid4())).json()
        == stranger.get(url + "/" + receipt["turn_id"]).json()
    )
    changed = client.post(url, json={**body, "message": "changed"}, headers=headers)
    assert changed.status_code == 409 and changed.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_catalog_only_read_and_cancel_but_never_new_tutor_send(api, monkeypatch):
    client, _, headers, cid, _, body, receipt = create(api)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    url = f"/api/free-courses/{cid}/tutor-turns"
    rejected = client.post(url, json=body, headers={**headers, "Idempotency-Key": str(uuid4())})
    assert rejected.status_code == 409 and rejected.json()["code"] == "FREE_COURSE_DISABLED"
    assert client.get(url + "/" + receipt["turn_id"]).status_code == 200
    op = f"/api/free-courses/{cid}/operations/{receipt['operation_id']}"
    cancelled = client.post(op + "/cancel", json={}, headers=headers)
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancel_requested"

    async def reconcile(sessions):
        return await TutorScheduler(sessions).reconcile()

    assert dbwork(reconcile) == 1
    assert client.get(url + "/" + receipt["turn_id"]).json()["status"] == "cancelled"
    assert client.post(op + "/cancel", json={}, headers=headers).json() == cancelled.json()
    assert [e["type"] for e in events(client.get(op + "/events"))] == [
        "queued",
        "cancel_requested",
        "done",
    ]


def test_ready_body_withdrawn_is_hidden_but_original_question_survives_http_replay(api):
    client, owner, headers, cid, manifest, body, receipt = create(api)
    complete()
    url = f"/api/free-courses/{cid}/tutor-turns"
    assert client.get(url + "/" + receipt["turn_id"]).json()["status"] == "ready"

    async def disable(sessions):
        return await applied(
            Maintenance(sessions, local_authority()), owner, draft(cid, manifest, index=0)
        )

    dbwork(disable)
    withdrawn = client.get(url + "/" + receipt["turn_id"]).json()
    assert withdrawn["status"] == "invalidated" and withdrawn["markdown"] is None
    assert withdrawn["anchor_refs"] == [] and withdrawn["message"] == body["message"]
    assert client.post(url, json=body, headers=headers).json() == receipt
    assert client.get(url + "/" + receipt["turn_id"]).json()["markdown"] is None


def test_active_generation_is_not_cancelled_or_parallelized_by_tutor_request(api):
    client, owner, headers = api()
    cid, manifest, _, _ = ready(owner)
    created = client.post("/api/free-courses", json={"goal": "另一个合成目标"}, headers=headers)
    assert created.status_code == 201
    blocked = client.post(
        f"/api/free-courses/{cid}/tutor-turns",
        json=request(manifest),
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "OPERATION_ACTIVE"
    current = client.get(
        f"/api/free-courses/{created.json()['course_id']}/operations/{created.json()['operation_id']}"
    )
    assert current.json()["state"] == "queued"
