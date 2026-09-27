"""POST learning sessions persist a profile and stream only temporary first-screen text."""

import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.learning_sessions import provider_gateway
from app.core.database import create_database_engine
from app.main import app
from app.models.learning import LearningOperation, LearningUnit
from app.models.learning_state import LearningPathVersion
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
        self.review_contexts: list[dict[str, object]] = []

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
            self.review_contexts.append(
                json.loads(request.prompt.messages[-1].content)["reference_context"]
            )
            return StructuredResult(
                value={
                    "review_version": "resource-review-v3",
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
                        "question": "[填空题] int x=1; x=2; 最后x=____。仅填一个整数",
                        "answer": "2",
                        "explanation": "连接节点。",
                    },
                    {
                        "id": "q2",
                        "question": ("[判断题] 头指针可以用于开始遍历。"
                                     "仅填 T 或 F（T=正确，F=错误）"),
                        "answer": "T",
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
    client.headers["Idempotency-Key"] = "test-learning-operation-key"
    return client, created.json()["csrf_token"]


def event_data(event: str) -> dict[str, object]:
    return json.loads(event.split("data: ", 1)[1])


def validate_contract(name: str, value: object) -> None:
    specification = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml").read_text(encoding="utf-8")
    )
    Draft202012Validator(
        {"components": specification["components"], "$ref": f"#/components/schemas/{name}"}
    ).validate(value)


def test_session_publishes_only_reviewed_resources_after_temporary_tokens(
    database_url: str,
) -> None:
    adapter = FakeAdapter()
    client, csrf = create_authenticated_client(adapter)
    try:
        response = client.post(
            "/api/learning-sessions",
            json={"goal": "讲解单链表", "preferred_language": "c"},
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
        assert profile.json()["initial_query"] == "讲解单链表"
        formal = client.get(f"/api/learning-units/{unit_id}")
        assert formal.status_code == 200
        validate_contract("LearningUnit", formal.json())
        assert formal.json()["status"] == "ready"
        assert formal.json()["knowledge_node_id"] == "c-pointer"
        assert formal.json()["path_target_node_id"] == "single-linked-list"
        assert formal.json()["path_version"] == 1

        async def verify_binding() -> None:
            engine = create_database_engine(database_url)
            try:
                async with async_sessionmaker(engine)() as db:
                    unit = await db.get(LearningUnit, UUID(unit_id))
                    assert unit is not None and unit.outline is not None
                    snapshot = unit.outline["path_snapshot"]
                    assert isinstance(snapshot, dict)
                    assert snapshot["graph_version"] == "mvp-0.2.0"
                    assert unit.outline["review_context_version"] == "resource-review-context-v1"
                    assert unit.outline["review_profile_version"] == snapshot["profile_version"]
                    path = await db.get(LearningPathVersion, UUID(snapshot["id"]))
                    assert path is not None and path.version == snapshot["version"]
                    assert unit.knowledge_point_id == path.current_node_id
            finally:
                await engine.dispose()

        asyncio.run(verify_binding())
        assert len(adapter.review_contexts) == 3
        assert all(item == adapter.review_contexts[0] for item in adapter.review_contexts)
        reference = adapter.review_contexts[0]
        assert reference["profile_version"] == profile.json()["version"]
        assert reference["node"]["id"] == "c-pointer"
        assert reference["known_profile"] == {}
        assert "讲解单链表" not in json.dumps(reference, ensure_ascii=False)
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


def test_ambiguous_goal_returns_durable_clarification_without_generation(database_url: str) -> None:
    adapter = FakeAdapter()
    client, csrf = create_authenticated_client(adapter)
    try:
        write_headers = {"Origin": "https://testserver", "X-CSRF-Token": csrf}
        first = client.post(
            "/api/learning-sessions", json={"goal": "讲解链表"}, headers=write_headers
        )
        assert first.status_code == 422
        assert first.json()["code"] == "GOAL_CLARIFICATION_REQUIRED"
        validate_contract("GoalClarification", first.json())
        assert {node["id"] for node in first.json()["candidate_nodes"]} == {
            "linked-list-concept",
            "single-linked-list",
        }
        replay = client.post(
            "/api/learning-sessions", json={"goal": "讲解链表"}, headers=write_headers
        )
        assert replay.status_code == 422 and replay.json() == first.json()
        assert adapter.calls == []
        assert client.get("/api/profile/me").status_code == 404
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


def test_same_idempotency_key_reuses_published_operation(database_url: str) -> None:
    adapter = FakeAdapter()
    client, csrf = create_authenticated_client(adapter)
    try:
        headers = {"Origin": "https://testserver", "X-CSRF-Token": csrf}
        first = client.post("/api/learning-sessions", json={"goal": "讲解栈"}, headers=headers)
        first_events = [part for part in first.text.split("\n\n") if part]
        operation_id = event_data(first_events[-2])["operation_id"]
        calls_after_first = list(adapter.calls)
        second = client.post("/api/learning-sessions", json={"goal": "讲解栈"}, headers=headers)
        second_events = [part for part in second.text.split("\n\n") if part]
        assert event_data(second_events[0])["operation_id"] == operation_id
        assert event_data(second_events[-1])["status"] == "published"
        assert adapter.calls == calls_after_first
        recovered = client.get(f"/api/learning-operations/{operation_id}")
        assert recovered.status_code == 200
        assert recovered.json()["status"] == "published"
        assert recovered.json()["learning_unit_id"] is not None
    finally:
        client.close()
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "status", ["accepted", "preparing", "streaming_temporary", "temporary_complete", "reviewing",
               "regenerating", "failed", "canceled"]
)
def test_operation_read_and_same_key_replay_preserve_state_without_generation(
    database_url: str, status: str,
) -> None:
    from app.services.learning_operations import request_digest

    adapter = FakeAdapter()
    client, csrf = create_authenticated_client(adapter)
    try:
        guest = client.get("/api/auth/session")
        owner_id = UUID(guest.json()["user"]["id"])

        async def seed() -> str:
            engine = create_database_engine(database_url)
            try:
                async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                    operation = LearningOperation(
                        user_id=owner_id,
                        idempotency_key="test-learning-operation-key",
                        request_digest=request_digest(goal="讲解队列", preferred_language="c"),
                        goal="讲解队列",
                        preferred_language="c",
                        status=status,
                    )
                    db.add(operation)
                    await db.commit()
                    return str(operation.id)
            finally:
                await engine.dispose()

        operation_id = asyncio.run(seed())
        recovered = client.get(f"/api/learning-operations/{operation_id}")
        assert recovered.status_code == 200
        assert recovered.json()["status"] == status
        assert recovered.json()["error"] is None
        with TestClient(app, base_url="https://testserver") as other:
            assert other.post(
                "/api/auth/guest", headers={"Origin": "https://testserver"}
            ).status_code == 201
            assert other.get(f"/api/learning-operations/{operation_id}").status_code == 404
        replay = client.post(
            "/api/learning-sessions", json={"goal": "讲解队列"},
            headers={"Origin": "https://testserver", "X-CSRF-Token": csrf},
        )
        events = [part for part in replay.text.split("\n\n") if part]
        assert event_data(events[0])["operation_id"] == operation_id
        assert event_data(events[-1])["status"] == status
        assert adapter.calls == []
        assert client.get(f"/api/learning-operations/{operation_id}").json() == recovered.json()
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_failed_operation_replays_without_provider_and_new_key_creates_new_operation(
    database_url: str,
) -> None:
    adapter = FakeAdapter(fail_stream=True)
    client, csrf = create_authenticated_client(adapter)
    try:
        headers = {"Origin": "https://testserver", "X-CSRF-Token": csrf}
        first = client.post("/api/learning-sessions", json={"goal": "讲解栈"}, headers=headers)
        first_events = [part for part in first.text.split("\n\n") if part]
        operation_id = event_data(first_events[0])["operation_id"]
        calls = list(adapter.calls)
        persisted = client.get(f"/api/learning-operations/{operation_id}").json()
        assert persisted["status"] == "failed"
        assert persisted["error"]["retryable"] is True
        replay = client.post("/api/learning-sessions", json={"goal": "讲解栈"}, headers=headers)
        events = [part for part in replay.text.split("\n\n") if part]
        assert event_data(events[0])["operation_id"] == operation_id
        assert event_data(events[-1])["status"] == "failed"
        assert adapter.calls == calls
        new = client.post(
            "/api/learning-sessions", json={"goal": "讲解栈"},
            headers={**headers, "Idempotency-Key": "explicit-regeneration-new-key"},
        )
        new_events = [part for part in new.text.split("\n\n") if part]
        assert event_data(new_events[0])["operation_id"] != operation_id
        assert len(adapter.calls) > len(calls)
        assert client.get(f"/api/learning-operations/{operation_id}").json() == persisted
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_session_post_requires_authenticated_csrf_write_protection(database_url: str) -> None:
    with TestClient(app, base_url="https://testserver") as client:
        missing = client.post(
            "/api/learning-sessions",
            json={"goal": "链表"},
            headers={"Idempotency-Key": "test-learning-operation-key"},
        )
        created = client.post("/api/auth/guest")
        csrf = created.json()["csrf_token"]
        missing_csrf = client.post(
            "/api/learning-sessions",
            json={"goal": "链表"},
            headers={"Idempotency-Key": "test-learning-operation-key"},
        )
        foreign = client.post(
            "/api/learning-sessions",
            json={"goal": "链表"},
            headers={
                "Origin": "https://evil.example",
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "test-learning-operation-key",
            },
        )
    assert missing.status_code == 401
    assert missing_csrf.status_code == foreign.status_code == 403
