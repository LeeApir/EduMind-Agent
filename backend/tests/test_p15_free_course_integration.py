"""One durable PG + real ASGI HTTP closed loop; explicit synthetic transport only."""

import json
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from test_free_course_api import api as _api
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate  # noqa: F401
from test_free_course_evidence import qualify
from test_free_course_planning import candidate
from test_free_course_scheduler import GOAL, PROOF, FakeAdapter
from test_free_scene_generation import response

from app.main import app
from app.services.free_course_scheduler import Reply, Scheduler

api = _api


def test_http_goal_progressive_read_restore_qualified_answer_atomic_revision_revocation(api):
    client, owner, headers = api()
    other, _, _ = api()
    created = client.post("/api/free-courses", json={"goal": GOAL}, headers=headers)
    assert created.status_code == 201, created.text
    cid = UUID(created.json()["course_id"])
    oid = created.json()["operation_id"]
    root = f"/api/free-courses/{cid}"
    assert client.get(root).json()["head"] is None
    assert client.get(root + f"/operations/{oid}").json()["state"] == "queued"
    plan = candidate(2, GOAL)
    for item in plan["plan"]["scenes"]:
        item["forms"] = ["text", "exercise"]
    adapter = FakeAdapter(
        [
            Reply("complete_response", PROOF, plan, 100, 100),
            *[
                Reply("complete_response", PROOF, response(["text", "exercise"]), 100, 100)
                for _ in range(2)
            ],
        ]
    )

    async def claim(sessions):
        return await Scheduler(sessions, graph_version="mvp-0.2.0").claim()

    lease = dbwork(claim)
    assert lease and lease.course == cid

    async def tick(sessions):
        # A fresh service and fresh engine/session pool for every durable dispatch.
        await Scheduler(sessions, graph_version="mvp-0.2.0").run_once(lease, adapter)

    dbwork(tick)  # plan only
    planned = client.get(root).json()["head"]
    assert planned["version"] == 1 and all(s["scene_version_id"] is None for s in planned["scenes"])
    dbwork(tick)  # first full scene readable before the rest
    first = client.get(root).json()["head"]
    assert first["version"] == 2
    assert first["scenes"][0]["scene_version_id"] and first["scenes"][1]["scene_version_id"] is None
    sid = first["scenes"][0]["scene_id"]
    visible = client.get(root + f"/versions/2/scenes/{sid}")
    assert (
        visible.status_code == 200
        and "answer_key" not in visible.text
        and "solution" not in visible.text
    )
    dbwork(tick)
    dbwork(tick)  # finish/release slot
    manifest = client.get(root).json()["head"]
    assert manifest["version"] == 3 and manifest["complete"] is True
    scene = client.get(root + f"/versions/3/scenes/{sid}").json()
    exercise = next(b for b in scene["blocks"] if b["kind"] == "exercise")
    body = dict(
        course_version=3,
        scene_id=sid,
        scene_version_id=scene["scene_version_id"],
        exercise_id=exercise["exercise_id"],
        exercise_version_id=exercise["exercise_version_id"],
        answers=[dict(question_id="q0", answer="0"), dict(question_id="q1", answer="1")],
    )

    async def qualify_fixture(sessions):
        # Trusted LOCAL synthetic attestation, never a public HTTP privilege or real quality label.
        await qualify(sessions, owner, cid, body)

    dbwork(qualify_fixture)
    submitted = client.post(root + "/attempts", json=body, headers=headers)
    assert submitted.status_code == 201, submitted.text
    aid = submitted.json()["attempt_id"]
    assert client.post(root + "/attempts", json=body, headers=headers).json() == submitted.json()
    assert client.get(root + "/attempts/" + aid).json()["mastery_effect"] == "admitted"
    assert client.get("/api/mastery/nodes/array/revisions").json()["items"][0]["score"] == 0.55
    assert (
        other.get(root).status_code == 404
        and other.get(root + "/attempts/" + aid).status_code == 404
    )
    # Re-created HTTP client restores exact old version from PG with the original owner session.
    with TestClient(app, base_url="https://testserver", cookies=client.cookies) as restored:
        assert restored.get(root + f"/versions/2/scenes/{sid}").json() == visible.json()
        assert restored.get(root + "/attempts/" + aid).json()["answers"] == body["answers"]
    stream = root + f"/operations/{oid}/events"
    events = [
        json.loads(line[6:])
        for line in client.get(stream).text.splitlines()
        if line.startswith("data: ")
    ]
    assert (
        events[-1]["type"] == "done" and sum(e["type"] == "first_scene_ready" for e in events) == 1
    )
    middle = events[len(events) // 2]["seq"]
    replay = [
        json.loads(line[6:])
        for line in client.get(stream, headers={"Last-Event-ID": str(middle)}).text.splitlines()
        if line.startswith("data: ")
    ]
    assert replay == [e for e in events if e["seq"] > middle]
    assert client.get(stream, params={"after": events[-1]["seq"]}).status_code == 204
    impact = client.get(
        root + "/impact", params={"kind": "revise_scene", "base_version": 3, "scene_id": sid}
    )
    assert impact.status_code == 200
    operation = client.post(
        root + "/operations",
        json=dict(
            kind="revise_scene",
            expected_head_version=3,
            scene_id=sid,
            instruction="核对准确题干条件，替换受影响场景",
            impact_digest=impact.json()["impact_digest"],
        ),
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert operation.status_code == 202, operation.text
    changed = response(["text", "exercise"])
    changed["blocks"][1]["items"][0]["answer_key"] = "changed"
    adapter.replies = [
        Reply("complete_response", PROOF, changed, 100, 100),
        Reply("complete_response", PROOF, response(["text", "exercise"]), 100, 100),
    ]
    lease = dbwork(claim)
    assert lease and str(lease.fence.operation_id) == operation.json()["operation_id"]
    dbwork(tick)
    assert (
        client.get(root).json()["head"] == manifest
    )  # staged content cannot replace the visible head
    assert client.get(root + "/attempts/" + aid).json()["mastery_effect"] == "admitted"
    dbwork(tick)
    dbwork(tick)
    assert client.get(root).json()["head"]["version"] == 4
    old = client.get(root + "/attempts/" + aid).json()
    assert old["answers"] == body["answers"] and old["mastery_effect"] == "revoked"
    assert old["comparison_score"] is None and not old["question_results"]
    history = client.get("/api/mastery/nodes/array/revisions").json()["items"]
    assert len(history) == 2 and [r["score"] for r in history] == [0, 0.55]
    assert (
        history[0]["source"]["reference"]["attempt_id"] == aid
        and history[0]["recomputed_from_revision"] == 1
    )
    stale = client.post(
        root + "/attempts", json=body, headers={**headers, "Idempotency-Key": str(uuid4())}
    )
    assert stale.status_code == 409 and stale.json()["code"] == "STALE_COURSE_VERSION"
    assert client.get(root + f"/versions/999/scenes/{sid}").status_code == 404
    assert (
        client.get(root + "/records", params={"kind": "attempt"}).json()["items"][0]["record_id"]
        == aid
    )
    assert len(adapter.calls) == 5 and not adapter.replies
