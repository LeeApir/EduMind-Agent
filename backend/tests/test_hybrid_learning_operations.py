"""Actual owner-scoped HTTP/SSE contract; fake gateway, no real Provider."""

import asyncio
import json
import os
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_hybrid_learning_publication import sequence
from test_hybrid_resource_review import ReviewGateway

from app.api.knowledge_graph import knowledge_graph_repository
from app.api.learning_sessions import provider_gateway
from app.core.database import create_database_engine
from app.main import app
from app.models.learning_review_case import LearningReviewCase
from app.services.hybrid_learning_publication import publish_approved_case
from app.services.learning_review_cases import decide_case

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="actual isolated PG required")


def guest():
    client = TestClient(app, base_url="https://testserver")
    payload = client.post("/api/auth/guest").json()
    return client, payload["csrf_token"]


def headers(csrf, key):
    return {"X-CSRF-Token": csrf, "Origin": "https://testserver", "Idempotency-Key": key}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", URL)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    yield
    app.dependency_overrides.clear()


def api_gateway(verdict="pass"):
    values = deepcopy(sequence(verdict))

    # Use the actual graph reference ID, never the expected review label.
    class Gateway(ReviewGateway):
        async def generate_structured(self, request, *, retry_safe=False):
            if "reference_ids" in request.json_schema.get("properties", {}):
                data = json.loads(request.prompt.messages[-1].content)
                self.values[0]["reference_ids"] = list(data["references"])
            return await super().generate_structured(request, retry_safe=retry_safe)

    return Gateway(values)


def test_shared_plan_sse_pending_safe_get_replay_then_approved_exact_read(configured):
    g = api_gateway("needs_human")
    app.dependency_overrides[provider_gateway] = lambda: g
    client, csrf = guest()
    key = str(uuid4())
    response = client.post(
        "/api/learning-sessions",
        headers=headers(csrf, key),
        json={"goal": "学习栈", "preferred_language": "c", "generation_protocol": "shared-plan-v1"},
    )
    assert response.status_code == 200
    frames = [
        (x.splitlines()[0][7:], json.loads(x.splitlines()[1][6:]))
        for x in response.text.split("\n\n")
        if x.startswith("event:")
    ]
    assert any(e == "review_required" for e, _ in frames)
    assert not any(e == "scene_ready" for e, _ in frames)
    assert frames[-1][1]["status"] == "awaiting_human"
    oid = frames[0][1]["operation_id"]
    state = client.get("/api/learning-operations/" + oid)
    assert state.headers["cache-control"] == "no-store"
    value = state.json()
    assert value["phase"] == "awaiting_human" and value["review_summary"]["state"] == "pending"
    assert not {"case_id", "reviewer_id", "payload", "findings"} & set(value["review_summary"])
    assert client.get("/api/learning-units/" + value["learning_unit_id"]).status_code == 404
    repeat = client.post(
        "/api/learning-sessions",
        headers=headers(csrf, key),
        json={"goal": "学习栈", "preferred_language": "c", "generation_protocol": "shared-plan-v1"},
    )
    assert "awaiting_human" in repeat.text and len(g.requests) == 9
    changed_protocol = client.post(
        "/api/learning-sessions",
        headers=headers(csrf, key),
        json={"goal": "学习栈", "preferred_language": "c"},
    )
    assert changed_protocol.status_code == 409 and len(g.requests) == 9
    other, _ = guest()
    assert other.get("/api/learning-operations/" + oid).status_code == 404

    async def approve():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                from sqlalchemy import select

                case = await db.scalar(
                    select(LearningReviewCase).where(LearningReviewCase.operation_id == UUID(oid))
                )
                await decide_case(
                    db,
                    owner_id=case.user_id,
                    case_id=case.id,
                    expected_digest=case.case_digest,
                    reviewer_id="synthetic",
                    identity_source="synthetic-test",
                    verdict="approve",
                    reason="Synthetic HTTP journey only.",
                    idempotency_key=str(uuid4()),
                )
                await publish_approved_case(db, owner_id=case.user_id, case_id=case.id)
                await db.commit()
        finally:
            await e.dispose()

    asyncio.run(approve())
    assert client.get("/api/learning-operations/" + oid).json()["status"] == "completed"
    formal = client.get(
        "/api/learning-units/" + value["learning_unit_id"] + "?publication_version=1"
    )
    assert formal.status_code == 200 and formal.json()["approval_source"] == "human_assisted"
    assert len(formal.json()["scenes"]) == 3
    assert all(
        "answer" not in item
        for s in formal.json()["scenes"]
        for r in s["resources"]
        if r["type"] == "exercise"
        for item in r["content"]["items"]
    )
    assert (
        client.get(
            "/api/learning-units/" + value["learning_unit_id"] + "?publication_version=99"
        ).status_code
        == 404
    )


def test_catalog_mode_blocks_new_protocol_before_gateway(configured, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    g = api_gateway()
    app.dependency_overrides[provider_gateway] = lambda: g
    client, csrf = guest()
    response = client.post(
        "/api/learning-sessions",
        headers=headers(csrf, str(uuid4())),
        json={"goal": "学习栈", "generation_protocol": "shared-plan-v1"},
    )
    assert response.status_code == 409 and not g.requests


def test_sse_disconnect_cancels_durably_without_restarting(configured):
    from test_hybrid_learning_publication import fresh_operation

    from app.api.hybrid_learning import hybrid_events
    from app.models.learning import LearningOperation

    async def exercise():
        e = create_database_engine(URL)
        factory = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with factory() as db:
                uid, oid = await fresh_operation(db)
            g = api_gateway()
            stream = hybrid_events(
                operation_id=oid,
                owner_id=uid,
                goal="学习栈",
                language="c",
                gateway=g,
                graph=knowledge_graph_repository(),
                sessions=factory,
            )
            assert "agent_start" in await anext(stream)
            await stream.aclose()
            async with factory() as db:
                assert (await db.get(LearningOperation, oid)).status == "canceled"
            assert not g.requests
        finally:
            await e.dispose()

    asyncio.run(exercise())


def test_planned_reexplanation_http_wait_keeps_old_course_and_rejects_code_scene(configured):
    g = api_gateway()
    app.dependency_overrides[provider_gateway] = lambda: g
    client, csrf = guest()
    response = client.post(
        "/api/learning-sessions",
        headers=headers(csrf, str(uuid4())),
        json={"goal": "学习栈", "generation_protocol": "shared-plan-v1"},
    )
    frames = [
        json.loads(x.splitlines()[1][6:])
        for x in response.text.split("\n\n")
        if x.startswith("event: scene_ready")
    ]
    unit_id = frames[0]["learning_unit_id"]
    base = "/api/learning-units/" + unit_id
    created = client.post(base + "/classroom", headers=headers(csrf, str(uuid4())))
    assert created.status_code == 201 and created.json()["scene_key"] == "explanation"
    values = sequence("needs_human")
    g2 = ReviewGateway([values[1], values[2], values[4], values[6], values[7]])
    app.dependency_overrides[provider_gateway] = lambda: g2
    from app.api.classroom import provider_gateway as classroom_gateway

    app.dependency_overrides[classroom_gateway] = lambda: g2
    h = {**headers(csrf, str(uuid4())), "If-Match-Classroom-Revision": "1"}
    bad = client.post(
        base + "/classroom/scenes/code/reexplanations",
        headers=h,
        json={"action": "simpler", "base_scene_version": 1},
    )
    assert bad.status_code == 409 and bad.json()["code"] == "REEXPLANATION_SCENE_UNSUPPORTED"
    assert not g2.requests
    h["Idempotency-Key"] = str(uuid4())
    pending = client.post(
        base + "/classroom/scenes/intro/reexplanations",
        headers=h,
        json={"action": "simpler", "base_scene_version": 1},
    )
    assert pending.status_code == 200 and "awaiting_human" in pending.text
    assert "event: scene_ready" not in pending.text and len(g2.requests) == 6
    old = client.get(base + "?publication_version=1")
    assert old.status_code == 200 and old.json()["publication_version"] == 1


@pytest.mark.parametrize("protocol", ["shared-plan-v1", "legacy-v1"])
def test_goal_clarification_has_choices_persists_reason_and_clears_phase(configured, protocol):
    class ForbiddenGateway:
        async def generate_structured(self, *args, **kwargs):
            pytest.fail("explicit ambiguity must not call a Provider")

    app.dependency_overrides[provider_gateway] = lambda: ForbiddenGateway()
    client, csrf = guest()
    body = {"goal": "学习数组和队列", "preferred_language": "c"}
    if protocol == "shared-plan-v1":
        body["generation_protocol"] = protocol
    response = client.post("/api/learning-sessions", headers=headers(csrf, str(uuid4())), json=body)
    if protocol == "shared-plan-v1":
        assert response.status_code == 200
        frames = [
            json.loads(part.split("data: ")[1])
            for part in response.text.split("\n\n")
            if part.startswith("event: error")
        ]
        detail = frames[0]
        state = client.get("/api/learning-operations/" + detail["operation_id"]).json()
        assert state["status"] == "failed"
        assert state["phase"] is None
        assert state["error"]["reason"] == "ambiguous_aliases"
    else:
        assert response.status_code == 422
        detail = response.json()
    assert detail["code"] == "GOAL_CLARIFICATION_REQUIRED"
    assert detail["reason"] == "ambiguous_aliases"
    assert {node["id"] for node in detail["candidate_nodes"]} == {"array", "queue"}
    assert "并列" in detail["message"]
