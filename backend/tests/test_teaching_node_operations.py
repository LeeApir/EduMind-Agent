"""Actual HTTP/PG teaching selection and legacy replay; gateway is scripted."""

import asyncio
import hashlib
import json
import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_hybrid_learning_operations import api_gateway, guest, headers
from test_hybrid_learning_operations import configured as configured

from app.api.learning_sessions import provider_gateway
from app.core.database import create_database_engine
from app.main import app
from app.models.learning import LearningOperation

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="actual isolated PG required")


def frames(response):
    return [
        (x.splitlines()[0][7:], json.loads(x.splitlines()[1][6:]))
        for x in response.text.split("\n\n")
        if x.startswith("event:")
    ]


@pytest.mark.parametrize("mode", [None, "target", "recommended"])
@pytest.mark.usefixtures("configured")
def test_selection_sse_and_reads_bind_exact_publication(mode):
    g = api_gateway()
    app.dependency_overrides[provider_gateway] = lambda: g
    client, csrf = guest()
    key = str(uuid4())
    body = {"goal": "学习栈", "generation_protocol": "shared-plan-v1"}
    if mode is not None:
        body["teaching_mode"] = mode
    response = client.post("/api/learning-sessions", headers=headers(csrf, key), json=body)
    assert response.status_code == 200
    events = frames(response)
    selected = next(v for n, v in events if n == "teaching_selected")
    c = selected["teaching_context"]
    assert c["target_node_id"] == "stack"
    assert c["teaching_mode"] == (mode or "target")
    assert c["teaching_node_id"] == (c["recommended_node_id"] if mode == "recommended" else "stack")
    assert [n for n, _ in events].index("teaching_selected") < [n for n, _ in events].index(
        "scene_ready"
    )
    ready = next(v for n, v in events if n == "scene_ready")
    oid = selected["operation_id"]
    state = client.get("/api/learning-operations/" + oid).json()
    assert state["teaching_context"] == c and state["binding_status"] == "bound"
    unit = client.get(
        f"/api/learning-units/{ready['learning_unit_id']}?publication_version=1"
    ).json()
    assert unit["teaching_context"] == c and unit["binding_status"] == "bound"
    assert unit["knowledge_node_id"] == c["teaching_node_id"]
    assert unit["path_target_node_id"] == "stack"

    # A later path recommendation cannot rewrite the frozen published selection.
    async def change_current_advice():
        from app.models.learning_state import LearningPathVersion

        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                path = await db.get(LearningPathVersion, UUID(c["path_version_id"]))
                path.current_node_id = "stack"
                await db.commit()
        finally:
            await e.dispose()

    asyncio.run(change_current_advice())
    old = client.get(f"/api/learning-units/{ready['learning_unit_id']}?publication_version=1")
    assert old.json()["teaching_context"] == c
    calls = len(g.requests)
    repeat = client.post("/api/learning-sessions", headers=headers(csrf, key), json=body)
    assert repeat.status_code == 200 and len(g.requests) == calls
    changed = {**body, "teaching_mode": "target" if mode == "recommended" else "recommended"}
    assert (
        client.post("/api/learning-sessions", headers=headers(csrf, key), json=changed).status_code
        == 409
    )
    assert len(g.requests) == calls


@pytest.mark.usefixtures("configured")
def test_legacy_recommended_is_rejected_without_call():
    g = api_gateway()
    app.dependency_overrides[provider_gateway] = lambda: g
    client, csrf = guest()
    response = client.post(
        "/api/learning-sessions",
        headers=headers(csrf, str(uuid4())),
        json={"goal": "学习栈", "teaching_mode": "recommended"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "TEACHING_SELECTION_UNAVAILABLE"
    assert not g.requests


@pytest.mark.usefixtures("configured")
def test_old_shared_key_only_omitted_mode_replays_without_call():
    g = api_gateway()
    app.dependency_overrides[provider_gateway] = lambda: g
    client = TestClient(app, base_url="https://testserver")
    auth = client.post("/api/auth/guest").json()
    key = str(uuid4())
    body = {"goal": "学习栈", "preferred_language": "c", "generation_protocol": "shared-plan-v1"}
    old_digest = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    async def seed():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                op = LearningOperation(
                    user_id=UUID(auth["user"]["id"]),
                    idempotency_key=key,
                    request_digest=old_digest,
                    goal=body["goal"],
                    preferred_language="c",
                    status="failed",
                )
                db.add(op)
                await db.commit()
                return str(op.id)
        finally:
            await e.dispose()

    oid = asyncio.run(seed())
    h = headers(auth["csrf_token"], key)
    assert client.post("/api/learning-sessions", headers=h, json=body).status_code == 200
    state = client.get("/api/learning-operations/" + oid).json()
    assert state["teaching_context"] is None and state["binding_status"] == "legacy_unverified"
    assert state["status"] == "failed"
    assert (
        client.post(
            "/api/learning-sessions", headers=h, json={**body, "teaching_mode": "target"}
        ).status_code
        == 409
    )
    assert not g.requests
