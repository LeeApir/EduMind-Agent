"""POST learning sessions persist a profile and stream only temporary first-screen text."""

import json
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
    def __init__(self, *, fail_stream: bool = False, reject_review: bool = False) -> None:
        self.fail_stream = fail_stream
        self.reject_review = reject_review
        self.calls: list[str] = []

    async def generate_text(self, request: TextRequest) -> TextResult:
        raise AssertionError(f"unexpected non-stream request: {request}")

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        properties = request.json_schema["properties"]
        assert isinstance(properties, dict)
        if "profile_version" in properties:
            self.calls.append("profile")
            return StructuredResult(
                value=profile_value(request.prompt.messages[-1].content), model_id="test"
            )
        if "review_version" in properties:
            self.calls.append("review")
            return StructuredResult(
                value={
                    "review_version": "resource-review-v1",
                    "verdict": "reject" if self.reject_review else "pass",
                    "issues": (
                        [{"area": "fact", "severity": "major", "message": "Needs correction."}]
                        if self.reject_review
                        else []
                    ),
                },
                model_id="review-test",
            )
        resource_type = properties["resource_type"]
        assert isinstance(resource_type, dict)
        kind = resource_type["const"]
        self.calls.append(f"resource:{kind}")
        content: dict[str, object]
        if kind == "explanation":
            content = {"markdown": "# 链表\n节点通过 next 指针连接。"}
        elif kind == "code":
            content = {
                "language": "c",
                "source": "int main(void) { return 0; }",
                "expected_output": "程序结束。",
                "key_steps": ["定义节点"],
                "display_only": True,
            }
        else:
            content = {
                "items": [
                    {
                        "id": "q1",
                        "question": "next 是什么？",
                        "answer": "后继指针",
                        "explanation": "连接节点。",
                    },
                    {
                        "id": "q2",
                        "question": "头节点作用？",
                        "answer": "起点",
                        "explanation": "从它遍历。",
                    },
                ]
            }
        return StructuredResult(
            value={
                "resource_type": kind,
                "prompt_version": "learning-resources-v1",
                "content": content,
            },
            model_id="generation-test",
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


def event_data(event: str) -> dict[str, object]:
    return json.loads(event.split("data: ", 1)[1])


def test_session_publishes_only_reviewed_resources_after_temporary_tokens(
    database_url: str,
) -> None:
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
            "event: stage_changed",
            "event: review_pass",
            "event: scene_ready",
            "event: done",
        ]
        assert '"temporary": true' in events[1]
        ready = event_data(events[-2])
        unit_id = ready["learning_unit_id"]
        resource_ids = ready["resource_ids"]
        assert isinstance(unit_id, str)
        assert isinstance(resource_ids, list)
        assert len(resource_ids) == 3
        assert '"status": "published"' in events[-1]
        profile = client.get("/api/profile/me")
        assert profile.status_code == 200
        assert profile.json()["initial_query"] == "讲解链表"
        formal = client.get(f"/api/learning-units/{unit_id}")
        assert formal.status_code == 200
        assert formal.json()["status"] == "ready"
        assert len(formal.json()["scenes"][0]["resources"]) == 3
        for resource_id in resource_ids:
            resource = client.get(f"/api/resource/{resource_id}")
            assert resource.status_code == 200
            assert resource.json()["review_status"] == "passed"
        assert adapter.calls == [
            "profile",
            "stream",
            "resource:explanation",
            "resource:code",
            "resource:exercise",
            "review",
            "review",
            "review",
        ]
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


def test_rejected_review_never_emits_readable_scene_or_resource(database_url: str) -> None:
    client, csrf = create_authenticated_client(FakeAdapter(reject_review=True))
    try:
        response = client.post(
            "/api/learning-sessions",
            json={"goal": "讲解队列", "preferred_language": "c"},
            headers={"Origin": "https://testserver", "X-CSRF-Token": csrf},
        )
        events = [part for part in response.text.split("\n\n") if part]
        assert [event.split("\n", 1)[0] for event in events] == [
            "event: agent_start",
            "event: token",
            "event: token",
            "event: stage_changed",
            "event: review_reject",
            "event: done",
        ]
        assert "scene_ready" not in response.text
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
