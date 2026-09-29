"""Current-scene reexplanation keeps reviewed history and request evidence."""

import asyncio
import json
import os
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.learning_resource_schema import LearningResourceType
from app.agents.learning_unit_generator import PendingLearningResource
from app.agents.review_agent import ReviewOutcome
from app.agents.review_schema import ReviewVerdict
from app.api.classroom import provider_gateway
from app.api.knowledge_graph import knowledge_graph_repository
from app.core.database import create_database_engine
from app.main import app
from app.models.classroom import ClassroomOperation, ClassroomSession
from app.models.learning import GeneratedResource, LearningScene, LearningUnit, utc_now
from app.models.learning_state import LearningEvidence, NodeMasteryRevision
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
    RetryPolicy,
    StructuredRequest,
    StructuredResult,
)
from app.services.scene_reexplanation import publish_reexplanation, reserve_reexplanation

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


class FakeAdapter:
    def __init__(self, *, review: str = "pass", provider_fails: bool = False) -> None:
        self.review = review
        self.provider_fails = provider_fails
        self.calls: list[str] = []

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        properties = request.json_schema.get("properties", {})
        assert isinstance(properties, dict)
        if "resource_type" in properties:
            self.calls.append("generate")
            if self.provider_fails:
                raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
            assert "Current-scene adjustment" in request.prompt.messages[-1].content
            return StructuredResult(value={
                "resource_type": "explanation", "prompt_version": "learning-resources-v1",
                "content": {"markdown": "新讲解：先保存后继，再修改指针。"},
            }, model_id="fake-generation")
        if "review_version" in properties:
            self.calls.append("review")
            if self.review == "unavailable":
                raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
            return StructuredResult(value={
                "review_version": "resource-review-v3",
                "verdict": self.review,
                "issues": [] if self.review == "pass" else [
                    {"area": "fact", "severity": "major", "message": "Incorrect."}
                ],
            }, model_id="fake-review")
        raise AssertionError("Unexpected Provider request")

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


def seed_unit(owner_id: UUID) -> tuple[UUID, UUID, UUID]:
    async def insert() -> tuple[UUID, UUID, UUID]:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                unit = LearningUnit(
                    user_id=owner_id, title="单链表插入", status="ready",
                    knowledge_point_id="linked-list-insertion",
                    learning_objectives={"goal": "理解插入指针顺序"},
                )
                db.add(unit)
                await db.flush()
                intro = LearningScene(
                    learning_unit_id=unit.id, scene_key="intro", scene_order=1,
                    scene_type="first_learning", version=1,
                    generation_status="complete", review_status="passed",
                    input_snapshot={"code_language": "Python"},
                )
                other = LearningScene(
                    learning_unit_id=unit.id, scene_key="followup", scene_order=2,
                    scene_type="first_learning", version=1,
                    generation_status="complete", review_status="passed",
                )
                db.add_all([intro, other])
                await db.flush()
                for scene in (intro, other):
                    db.add(GeneratedResource(
                        user_id=owner_id, learning_unit_id=unit.id, scene_id=scene.id,
                        resource_type="explanation", content={"markdown": "旧讲解"},
                        review_status="passed", published_at=utc_now(),
                        generation_metadata={"prompt_version": "learning-resources-v1"},
                    ))
                db.add(GeneratedResource(
                    user_id=owner_id, learning_unit_id=unit.id, scene_id=intro.id,
                    resource_type="code", content={
                        "language": "Python", "source": "print(1)", "expected_output": "1",
                        "key_steps": ["保存后继"], "display_only": True,
                    },
                    review_status="passed", published_at=utc_now(),
                    generation_metadata={"prompt_version": "learning-resources-v1"},
                ))
                await db.commit()
                return unit.id, intro.id, other.id
        finally:
            await engine.dispose()

    return asyncio.run(insert())


def guest() -> tuple[TestClient, UUID, str]:
    client = TestClient(app, base_url="https://testserver")
    response = client.post("/api/auth/guest")
    assert response.status_code == 201
    return client, UUID(response.json()["user"]["id"]), response.json()["csrf_token"]


def headers(csrf: str, key: str, revision: int | None = None) -> dict[str, str]:
    value = {"X-CSRF-Token": csrf, "Origin": "https://testserver",
             "Idempotency-Key": key}
    if revision is not None:
        value["If-Match-Classroom-Revision"] = str(revision)
    return value


def events(body: str) -> list[tuple[str, dict[str, object]]]:
    return [(frame.splitlines()[0].removeprefix("event: "),
             json.loads(frame.splitlines()[1].removeprefix("data: ")))
            for frame in body.split("\n\n") if frame]


def test_reexplanation_publishes_one_scene_and_replays_without_provider(database_url: None) -> None:
    adapter = FakeAdapter()
    use_adapter(adapter)
    client, owner_id, csrf = guest()
    unit_id, intro_id, other_id = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}"
    created = client.post(f"{base}/classroom", headers=headers(csrf, "create-reexplain-key-01"))
    assert created.status_code == 201
    path = f"{base}/classroom/scenes/intro/reexplanations"
    request = {"action": "simpler", "base_scene_version": 1}
    first = client.post(path, json=request, headers=headers(csrf, "reexplain-key-00001", 1))
    assert first.status_code == 200
    stream = events(first.text)
    assert [name for name, _ in stream][-3:] == ["review_pass", "scene_ready", "done"]
    ready = next(data for name, data in stream if name == "scene_ready")
    assert ready["scene_version"] == 2
    assert len(ready["resource_ids"]) == 2
    assert client.get(f"{base}/classroom").json()["scene_version"] == 2
    unit = client.get(base).json()
    versions = sorted(
        (scene["version"], scene["is_current"])
        for scene in unit["scenes"] if scene["scene_key"] == "intro"
    )
    assert versions == [(1, False), (2, True)]
    replay = client.post(path, json=request, headers=headers(csrf, "reexplain-key-00001", 1))
    assert events(replay.text)[-1] == ("done", {"status": "published"})
    assert adapter.calls == ["generate", "review"]
    assert client.get(f"/api/resource/{ready['resource_ids'][0]}").status_code == 200

    async def verify() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                scenes = list((await db.scalars(select(LearningScene).where(
                    LearningScene.learning_unit_id == unit_id
                ))).all())
                assert sorted((scene.scene_key, scene.version) for scene in scenes) == [
                    ("followup", 1), ("intro", 1), ("intro", 2)
                ]
                assert next(s for s in scenes if s.id == intro_id).review_status == "passed"
                assert next(s for s in scenes if s.id == other_id).version == 1
                assert await db.scalar(select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == owner_id,
                    LearningEvidence.evidence_type == "reexplanation_requested",
                )) == 1
                score = await db.scalar(select(NodeMasteryRevision.score).where(
                    NodeMasteryRevision.user_id == owner_id,
                    NodeMasteryRevision.knowledge_node_id == "linked-list-insertion",
                ).order_by(NodeMasteryRevision.revision.desc()).limit(1))
                assert score == 0.0
        finally:
            await engine.dispose()
    asyncio.run(verify())
    client.close()


def test_provider_failure_keeps_original_and_durable_request(database_url: None) -> None:
    adapter = FakeAdapter(provider_fails=True)
    use_adapter(adapter)
    client, owner_id, csrf = guest()
    unit_id, _, _ = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    client.post(base, headers=headers(csrf, "create-reexplain-key-05"))
    response = client.post(
        f"{base}/scenes/intro/reexplanations",
        json={"action": "simpler", "base_scene_version": 1},
        headers=headers(csrf, "reexplain-key-failed", 1),
    )
    frames = events(response.text)
    assert frames[-2:] == [
        ("error", {"code": "PROVIDER_UNAVAILABLE", "retryable": True}),
        ("done", {"status": "failed"}),
    ]
    operation_id = frames[0][1]["operation_id"]
    assert client.get(f"/api/classroom-operations/{operation_id}").json()["status"] == "failed"
    assert client.get(base).json()["scene_version"] == 1
    assert adapter.calls == ["generate"]
    client.close()


def test_review_unavailable_retracts_temporary_content(database_url: None) -> None:
    adapter = FakeAdapter(review="unavailable")
    use_adapter(adapter)
    client, owner_id, csrf = guest()
    unit_id, _, _ = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    client.post(base, headers=headers(csrf, "create-reexplain-key-06"))
    response = client.post(
        f"{base}/scenes/intro/reexplanations",
        json={"action": "simpler", "base_scene_version": 1},
        headers=headers(csrf, "reexplain-review-failure", 1),
    )
    frames = events(response.text)
    assert any(name == "token" for name, _ in frames)
    assert next(data for name, data in frames if name == "content_retracted")["code"] == (
        "REVIEW_UNAVAILABLE"
    )
    assert frames[-2:] == [
        ("error", {"code": "REVIEW_UNAVAILABLE", "retryable": True}),
        ("done", {"status": "failed"}),
    ]
    assert client.get(base).json()["scene_version"] == 1
    client.close()


def test_competing_reservations_publish_only_one_scene(database_url: None) -> None:
    client, owner_id, csrf = guest()
    unit_id, _, _ = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    assert client.post(base, headers=headers(csrf, "create-reexplain-key-04")).status_code == 201

    async def race() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            graph = knowledge_graph_repository()
            ids = []
            for index in (1, 2):
                async with sessions() as db:
                    reservation = await reserve_reexplanation(
                        db, owner_id=owner_id, unit_id=unit_id, scene_key="intro",
                        idempotency_key=f"competing-reexplain-{index:04}",
                        action="simpler", base_scene_version=1,
                        expected_revision=1, graph=graph,
                    )
                    ids.append(reservation.operation.id)
            review = ReviewOutcome(
                PendingLearningResource(
                    resource_type=LearningResourceType.EXPLANATION,
                    content={"markdown": "审核通过的新讲解"},
                    prompt_version="learning-resources-v1", model_id="fake",
                    usage=None,
                ),
                ReviewVerdict.PASS, (), "fake-review", 0,
            )
            async with sessions() as db:
                first = await publish_reexplanation(
                    db, owner_id=owner_id, operation_id=ids[0], review=review,
                )
            async with sessions() as db:
                second = await publish_reexplanation(
                    db, owner_id=owner_id, operation_id=ids[1], review=review,
                )
            assert first.published is True
            assert second.published is False
            async with sessions() as db:
                statuses = list((await db.scalars(select(ClassroomOperation.status).where(
                    ClassroomOperation.id.in_(ids)
                ))).all())
                assert sorted(statuses) == ["published", "superseded"]
                session = await db.scalar(select(ClassroomSession).where(
                    ClassroomSession.learning_unit_id == unit_id
                ))
                assert session is not None
                assert session.scene_version == 2
                assert await db.scalar(select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == owner_id,
                    LearningEvidence.evidence_type == "reexplanation_requested",
                )) == 2
        finally:
            await engine.dispose()
    asyncio.run(race())
    client.close()


def test_rejected_review_preserves_current_scene_and_evidence(database_url: None) -> None:
    adapter = FakeAdapter(review="reject")
    use_adapter(adapter)
    client, owner_id, csrf = guest()
    unit_id, _, _ = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    client.post(base, headers=headers(csrf, "create-reexplain-key-02"))
    result = client.post(f"{base}/scenes/intro/reexplanations",
                         json={"action": "deeper", "base_scene_version": 1},
                         headers=headers(csrf, "reexplain-key-00002", 1))
    frames = events(result.text)
    assert "content_retracted" in [name for name, _ in frames]
    assert frames[-1] == ("done", {"status": "failed"})
    assert client.get(base).json()["scene_version"] == 1

    async def verify() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                assert await db.scalar(select(func.count()).select_from(LearningScene).where(
                    LearningScene.learning_unit_id == unit_id,
                    LearningScene.scene_key == "intro",
                )) == 1
                assert await db.scalar(select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == owner_id,
                    LearningEvidence.evidence_type == "reexplanation_requested",
                )) == 1
        finally:
            await engine.dispose()
    asyncio.run(verify())
    client.close()


def test_stale_version_and_foreign_owner_are_rejected(database_url: None) -> None:
    use_adapter(FakeAdapter())
    client, owner_id, csrf = guest()
    unit_id, _, _ = seed_unit(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    client.post(base, headers=headers(csrf, "create-reexplain-key-03"))
    path = f"{base}/scenes/intro/reexplanations"
    first = client.post(path, json={"action": "another_example", "base_scene_version": 1},
                        headers=headers(csrf, "reexplain-key-00003", 1))
    assert events(first.text)[-1] == ("done", {"status": "published"})
    stale = client.post(path, json={"action": "simpler", "base_scene_version": 1},
                        headers=headers(csrf, "reexplain-key-00004", 2))
    assert stale.status_code == 409
    assert stale.json()["code"] == "SCENE_VERSION_CONFLICT"
    foreign, _, foreign_csrf = guest()
    hidden = foreign.post(path, json={"action": "simpler", "base_scene_version": 2},
                          headers=headers(foreign_csrf, "reexplain-key-foreign", 2))
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "NOT_FOUND"
    foreign.close()
    client.close()
