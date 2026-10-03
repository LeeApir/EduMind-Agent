"""Only whole reviewed debate results are visible; failures preserve the classroom."""

import asyncio
import json
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_debate_candidate_generator import candidate

from app.api.classroom import provider_gateway
from app.api.debate import _debate_events
from app.api.knowledge_graph import knowledge_graph_repository
from app.core.database import create_database_engine
from app.main import app
from app.models.classroom import ClassroomOperation, DebateResult
from app.models.learning import GeneratedResource, LearningScene, LearningUnit, utc_now
from app.services.debate_publication import reserve_debate
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
    RetryPolicy,
    StructuredRequest,
    StructuredResult,
)

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


class FakeAdapter:
    def __init__(
        self, *, review: str = "pass", timeout: bool = False,
        generation_error: ProviderErrorCode | None = None,
    ) -> None:
        self.review = review
        self.timeout = timeout
        self.generation_error = generation_error
        self.calls: list[str] = []

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        schema = request.json_schema.get("properties")
        assert isinstance(schema, dict)
        if "schema_version" in schema:
            self.calls.append("generate")
            if self.generation_error is not None:
                raise ProviderError(self.generation_error)
            assert "array-vs-linked-list" in request.prompt.messages[-1].content
            return StructuredResult(value=candidate(), model_id="fake-generation")
        if "review_version" in schema:
            self.calls.append("review")
            if self.timeout:
                raise ProviderError(ProviderErrorCode.TIMEOUT)
            return StructuredResult(value={
                "review_version": "array-vs-linked-list-review-v1",
                "verdict": self.review,
                "issues": [] if self.review == "pass" else [
                    {"area": "fact", "severity": "severe", "message": "False complexity claim."},
                ],
            }, model_id="fake-review")
        raise AssertionError("Unexpected structured request")

    async def generate_text(self, request):  # type: ignore[no-untyped-def]
        raise AssertionError("Unexpected text request")

    def stream_text(self, request):  # type: ignore[no-untyped-def]
        raise AssertionError("Unexpected stream request")


@pytest.fixture(autouse=True)
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if TEST_DATABASE_URL is not None:
        monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    yield
    app.dependency_overrides.clear()


def use_adapter(adapter: FakeAdapter) -> None:
    app.dependency_overrides[provider_gateway] = lambda: ProviderGateway(
        adapter, retry_policy=RetryPolicy(max_attempts=1)
    )


def guest() -> tuple[TestClient, UUID, str]:
    client = TestClient(app, base_url="https://testserver")
    response = client.post("/api/auth/guest")
    assert response.status_code == 201
    return client, UUID(response.json()["user"]["id"]), response.json()["csrf_token"]


def headers(csrf: str, key: str, revision: int | None = None) -> dict[str, str]:
    value = {"X-CSRF-Token": csrf, "Origin": "https://testserver", "Idempotency-Key": key}
    if revision is not None:
        value["If-Match-Classroom-Revision"] = str(revision)
    return value


def seed_unit(owner_id: UUID) -> UUID:
    async def insert() -> UUID:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                unit = LearningUnit(
                    user_id=owner_id, title="数组与链表", status="ready",
                    knowledge_point_id="single-linked-list",
                )
                db.add(unit)
                await db.flush()
                scene = LearningScene(
                    learning_unit_id=unit.id, scene_key="intro", scene_order=1,
                    scene_type="first_learning", version=1,
                    generation_status="complete", review_status="passed",
                )
                db.add(scene)
                await db.flush()
                db.add(GeneratedResource(
                    user_id=owner_id, learning_unit_id=unit.id, scene_id=scene.id,
                    resource_type="explanation", content={"markdown": "数组与链表讲解"},
                    review_status="passed", published_at=utc_now(),
                    generation_metadata={"prompt_version": "learning-resources-v1"},
                ))
                await db.commit()
                return unit.id
        finally:
            await engine.dispose()

    return asyncio.run(insert())


def events(body: str) -> list[tuple[str, dict[str, object]]]:
    return [(frame.splitlines()[0].removeprefix("event: "),
             json.loads(frame.splitlines()[1].removeprefix("data: ")))
            for frame in body.split("\n\n") if frame]


def test_reviewed_result_publishes_once_and_exit_restores_original_point() -> None:
    adapter = FakeAdapter()
    use_adapter(adapter)
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    assert client.post(base, headers=headers(csrf, "create-debate-key-01")).status_code == 201
    request = {"preset": "array-vs-linked-list", "question": "频繁随机访问时选哪种？"}
    path = f"{base}/debate"
    response = client.post(path, json=request, headers=headers(csrf, "debate-request-key-01", 1))
    assert response.status_code == 200
    frames = events(response.text)
    assert [name for name, _ in frames][-3:] == ["review_pass", "debate_ready", "done"]
    result_id = next(data["result_id"] for name, data in frames if name == "debate_ready")
    result = client.get(f"{path}/{result_id}")
    assert result.status_code == 200
    payload = result.json()
    spec = json.loads((Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml").read_text())
    Draft202012Validator({**spec, "$ref": "#/components/schemas/DebateResult"}).validate(payload)
    assert set(payload["perspectives"]) == {"performance", "engineering", "academic"}
    assert payload["review_model_id"] == "fake-review"
    assert payload["generation_model_id"] == "fake-generation"
    assert payload["question_conditions"]["stated"] == ["需要频繁随机访问"]
    assert payload["status"] == "published"
    snapshot = client.get(base).json()
    assert snapshot["scene_key"] == "array-vs-linked-list"
    assert snapshot["detour"]["scene_key"] == "intro"
    assert snapshot["detour"]["result_id"] == result_id
    assert snapshot["message_cursor"] == 0

    replay = client.post(path, json=request, headers=headers(csrf, "debate-request-key-01", 1))
    assert events(replay.text)[-1] == ("done", {"status": "published"})
    assert adapter.calls == ["generate", "review"]
    exit_path = f"{path}/{result_id}/exit"
    exited = client.post(exit_path, headers=headers(csrf, "debate-exit-key-001", 2))
    assert exited.status_code == 200
    assert exited.json()["scene_key"] == "intro"
    assert exited.json()["revision"] == 3
    assert exited.json()["message_cursor"] == 0
    assert "detour" not in exited.json()
    replay_exit = client.post(exit_path, headers=headers(csrf, "debate-exit-key-001", 2))
    assert replay_exit.json() == exited.json()
    other, _, other_csrf = guest()
    assert other.get(f"{path}/{result_id}").status_code == 404
    foreign_exit = other.post(exit_path, headers=headers(other_csrf, "debate-other-key-01", 3))
    assert foreign_exit.status_code == 404


@pytest.mark.parametrize("review,timeout,code", [
    ("reject", False, "REVIEW_REJECTED"),
    ("pass", True, "REVIEW_UNAVAILABLE"),
])
def test_rejected_or_unavailable_review_keeps_original_classroom(
    review: str, timeout: bool, code: str
) -> None:
    adapter = FakeAdapter(review=review, timeout=timeout)
    use_adapter(adapter)
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    client.post(base, headers=headers(csrf, "create-debate-key-02"))
    response = client.post(f"{base}/debate", json={
        "preset": "array-vs-linked-list", "question": "数组与链表如何选？",
    }, headers=headers(csrf, "debate-failure-key-1", 1))
    frames = events(response.text)
    assert ("error", {"code": code, "retryable": timeout}) in frames
    assert frames[-1] == ("done", {"status": "failed"})
    snapshot = client.get(base).json()
    assert snapshot["scene_key"] == "intro" and snapshot["revision"] == 1
    assert "detour" not in snapshot

    async def verify() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine)
            async with sessions() as db:
                assert await db.scalar(select(func.count()).select_from(DebateResult).where(
                    DebateResult.user_id == owner_id,
                    DebateResult.learning_unit_id == unit_id,
                )) == 0
                operation = await db.scalar(select(ClassroomOperation).where(
                    ClassroomOperation.user_id == owner_id,
                    ClassroomOperation.idempotency_key == "debate-failure-key-1",
                ))
                assert operation is not None and operation.status == "failed"
        finally:
            await engine.dispose()

    asyncio.run(verify())


@pytest.mark.parametrize("error,code,retryable", [
    (ProviderErrorCode.INVALID_OUTPUT, "DEBATE_INVALID_OUTPUT", False),
    (ProviderErrorCode.TIMEOUT, "PROVIDER_UNAVAILABLE", True),
])
def test_generation_failure_remains_unpublished(
    error: ProviderErrorCode, code: str, retryable: bool
) -> None:
    adapter = FakeAdapter(generation_error=error)
    use_adapter(adapter)
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    assert client.post(base, headers=headers(csrf, "create-debate-key-03")).status_code == 201
    request = {"preset": "array-vs-linked-list", "question": "哪种更适合？"}
    response = client.post(f"{base}/debate", json=request,
                           headers=headers(csrf, "debate-error-key-01", 1))
    assert ("error", {"code": code, "retryable": retryable}) in events(response.text)
    assert client.get(base).json()["scene_key"] == "intro"
    replay = client.post(f"{base}/debate", json=request,
                         headers=headers(csrf, "debate-error-key-01", 1))
    assert events(replay.text)[-1] == ("done", {"status": "failed"})
    assert adapter.calls == ["generate"]


def test_revision_and_active_operation_gate_publication() -> None:
    adapter = FakeAdapter()
    use_adapter(adapter)
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    assert client.post(base, headers=headers(csrf, "create-debate-key-04")).status_code == 201
    request = {"preset": "array-vs-linked-list", "question": "随机访问哪个好？"}
    path = f"{base}/debate"
    stale = client.post(path, json=request, headers=headers(csrf, "debate-stale-key-1", 2))
    assert stale.status_code == 409
    assert stale.json()["code"] == "CLASSROOM_VERSION_CONFLICT"
    assert adapter.calls == []
    created = client.post(path, json=request, headers=headers(csrf, "debate-good-key-01", 1))
    assert created.status_code == 200
    result_id = next(data["result_id"] for name, data in events(created.text)
                     if name == "debate_ready")
    active = client.post(path, json=request, headers=headers(csrf, "debate-active-key-1", 2))
    assert active.status_code == 409
    assert active.json()["code"] == "DEBATE_ALREADY_ACTIVE"
    assert adapter.calls == ["generate", "review"]
    assert client.get(f"{path}/{result_id}").status_code == 200


def test_disconnected_stream_releases_operation_without_changing_classroom() -> None:
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    assert client.post(base, headers=headers(csrf, "create-debate-key-05")).status_code == 201

    async def disconnect() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                reservation = await reserve_debate(
                    db, owner_id=owner_id, unit_id=unit_id,
                    preset="array-vs-linked-list", question="如何选择？",
                    idempotency_key="debate-disconnect-1", expected_revision=1,
                )
            stream = _debate_events(
                reservation=reservation, profile=None, profile_version=None,
                graph=knowledge_graph_repository(),
                gateway=ProviderGateway(FakeAdapter(), retry_policy=RetryPolicy(max_attempts=1)),
                owner_id=owner_id, sessions=sessions,
            )
            assert (await anext(stream)).startswith("event: agent_start")
            await stream.aclose()
            async with sessions() as db:
                operation = await db.get(ClassroomOperation, reservation.operation.id)
                assert operation is not None and operation.status == "failed"
                assert operation.error is not None
                assert operation.error["code"] == "DEBATE_INTERRUPTED"
        finally:
            await engine.dispose()

    asyncio.run(disconnect())
    assert client.get(base).json()["scene_key"] == "intro"
