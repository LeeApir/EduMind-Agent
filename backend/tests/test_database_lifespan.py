"""Lifespan pool ownership is independent of request/owner/session ownership."""

import asyncio
import json
import os
import re
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_learning_sessions import FakeAdapter

from app.api.learning_sessions import provider_gateway
from app.core import database
from app.main import app
from app.services.provider_gateway import ProviderGateway


def test_lifespan_reuses_one_factory_and_disposes_once(monkeypatch):
    engine = Mock(dispose=AsyncMock())
    factory = Mock()
    monkeypatch.setattr(database, "create_database_engine", lambda: engine)
    monkeypatch.setattr(database, "async_sessionmaker", lambda *args, **kwargs: factory)

    async def run():
        local = FastAPI()
        async with database.database_lifespan(local) as state:
            runtime = state["database_runtime"]
            assert runtime.session_factory() is factory
            assert runtime.session_factory() is factory
            engine.dispose.assert_not_awaited()
        engine.dispose.assert_awaited_once()
        async with database.database_lifespan(local) as next_state:
            assert next_state["database_runtime"] is not runtime

    asyncio.run(run())


def test_health_does_not_require_or_create_database(monkeypatch):
    monkeypatch.delenv("EDUMIND_DATABASE_URL", raising=False)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.app_state["database_runtime"].engine is None


@pytest.mark.skipif(not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="isolated PG required")
def test_pooled_routes_preserve_explicit_profile_correction_prerequisite_and_recovery(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    adapter = FakeAdapter()
    app.dependency_overrides[provider_gateway] = lambda: ProviderGateway(adapter)
    try:
        with TestClient(app, base_url="https://offline") as client:
            guest = client.post("/api/auth/guest")
            headers = {
                "Origin": "https://offline",
                "X-CSRF-Token": guest.json()["csrf_token"],
                "Idempotency-Key": str(uuid4()),
            }
            first = client.post(
                "/api/learning-sessions", json={"goal": "讲解单链表"}, headers=headers
            )
            assert first.status_code == 200
            calls = len(adapter.calls)
            client.post("/api/learning-sessions", json={"goal": "讲解单链表"}, headers=headers)
            assert len(adapter.calls) == calls
            correction = client.patch(
                "/api/profile/me",
                json={"engineering_preference": {"code_first": True}},
                headers={
                    **headers,
                    "Idempotency-Key": str(uuid4()),
                    "If-Match-Profile-Version": "1",
                },
            )
            assert correction.status_code == 200
            assert correction.json()["version"] == 2
            assert (
                correction.json()["evidence"]["engineering_preference"][-1]["source"]
                == "manual_correction"
            )
            second = client.post(
                "/api/learning-sessions",
                json={"goal": "讲解单链表"},
                headers={**headers, "Idempotency-Key": str(uuid4())},
            )
            assert second.status_code == 200
            profile = client.get("/api/profile/me").json()
            assert profile["engineering_preference"] == {"code_first": True}
            assert profile["version"] == 3
            path = client.get("/api/path/current?target_node_id=single-linked-list")
            assert path.status_code == 200
            assert path.json()["profile_version"] == 3
            assert path.json()["current_node_id"] == "c-pointer"
            assert path.json()["node_details"][0]["recommended_resource"] == "code"
            ready = re.search(r"event: scene_ready\ndata: ([^\n]+)", second.text)
            assert ready is not None
            unit_id = json.loads(ready[1])["learning_unit_id"]
            unit = client.get(f"/api/learning-units/{unit_id}").json()
            assert unit["knowledge_node_id"] == "c-pointer"
            assert unit["path_target_node_id"] == "single-linked-list"
            assert all(
                resource["review_status"] == "passed"
                for scene in unit["scenes"]
                for resource in scene["resources"]
            )
    finally:
        app.dependency_overrides.clear()
