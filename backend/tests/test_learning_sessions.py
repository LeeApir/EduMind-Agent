"""POST learning sessions persist a profile and stream only temporary first-screen text."""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.learning_sessions import provider_gateway
from app.main import app
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
    StructuredRequest,
    StructuredResult,
    TextDelta,
    TextRequest,
    TextResult,
)

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def profile_value(goal: str) -> dict[str, object]:
    return {
        "profile_version": 1,
        "initial_query": goal,
        "professional_background": None,
        "knowledge_base": None,
        "cognitive_style": None,
        "learning_goals": {"current_topic": "链表"},
        "error_preferences": None,
        "engineering_preference": None,
        "evidence": {
            "learning_goals": [
                {
                    "source": "initial_query",
                    "confidence": 0.9,
                    "observed_at": "2026-09-17T15:10:00+00:00",
                    "profile_version": 1,
                }
            ]
        },
    }


class FakeAdapter:
    def __init__(self, *, fail_stream: bool = False) -> None:
        self.fail_stream = fail_stream
        self.calls: list[str] = []

    async def generate_text(self, request: TextRequest) -> TextResult:
        raise AssertionError(f"unexpected non-stream request: {request}")

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        self.calls.append("profile")
        return StructuredResult(
            value=profile_value(request.prompt.messages[-1].content), model_id="test"
        )

    async def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]:
        self.calls.append("stream")
        assert "temporary" in request.messages[0].content
        if self.fail_stream:
            raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
        yield TextDelta("链表由节点组成。")
        yield TextDelta("先理解 next 指针。")


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    yield TEST_DATABASE_URL


def create_authenticated_client(adapter: FakeAdapter) -> tuple[TestClient, str]:
    gateway = ProviderGateway(adapter)
    app.dependency_overrides[provider_gateway] = lambda: gateway
    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/auth/guest", headers={"Origin": "https://testserver"})
    assert created.status_code == 201
    return client, created.json()["csrf_token"]


def test_session_event_order_persists_profile_and_keeps_tokens_temporary(database_url: str) -> None:
    adapter = FakeAdapter()
    client, csrf = create_authenticated_client(adapter)
    try:
        response = client.post(
            "/api/learning-sessions",
            json={"goal": "讲解链表", "preferred_language": "c"},
            headers={"Origin": "https://testserver", "X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = [part for part in response.text.split("\n\n") if part]
        assert [event.split("\n", 1)[0] for event in events] == [
            "event: agent_start",
            "event: token",
            "event: token",
            "event: done",
        ]
        assert '"temporary": true' in events[1]
        assert "scene_ready" not in response.text
        assert '"status": "temporary_complete"' in events[-1]
        profile = client.get("/api/profile/me")
        assert profile.status_code == 200
        assert profile.json()["initial_query"] == "讲解链表"
        assert adapter.calls == ["profile", "stream"]
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_provider_failure_emits_error_then_failed_done(database_url: str) -> None:
    client, csrf = create_authenticated_client(FakeAdapter(fail_stream=True))
    try:
        response = client.post(
            "/api/learning-sessions",
            json={"goal": "讲解栈"},
            headers={"Origin": "https://testserver", "X-CSRF-Token": csrf},
        )
        events = [part for part in response.text.split("\n\n") if part]
        assert [event.split("\n", 1)[0] for event in events] == [
            "event: agent_start",
            "event: error",
            "event: done",
        ]
        assert '"code": "PROVIDER_UNAVAILABLE"' in events[1]
        assert '"status": "failed"' in events[-1]
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_session_post_requires_authenticated_csrf_write_protection(database_url: str) -> None:
    with TestClient(app, base_url="https://testserver") as client:
        missing = client.post("/api/learning-sessions", json={"goal": "链表"})
        created = client.post("/api/auth/guest")
        csrf = created.json()["csrf_token"]
        missing_csrf = client.post("/api/learning-sessions", json={"goal": "链表"})
        foreign = client.post(
            "/api/learning-sessions",
            json={"goal": "链表"},
            headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf},
        )
    assert missing.status_code == 401
    assert missing_csrf.status_code == foreign.status_code == 403
