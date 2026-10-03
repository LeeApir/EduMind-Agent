"""Learning controls are durable, owner-scoped, and never invent mastery."""

import asyncio
import os
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.knowledge_graph import knowledge_graph_repository
from app.core.database import create_database_engine
from app.main import app
from app.models.learning import (
    GeneratedResource,
    LearningScene,
    LearningUnit,
    ProfileEvent,
    utc_now,
)
from app.models.learning_state import (
    LearningEvidence,
    LearningPathCurrent,
    LearningPathVersion,
    NodeMasteryCurrent,
)
from app.services.classroom import ClassroomVersionConflict
from app.services.classroom_controls import apply_classroom_control

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


@pytest.fixture(autouse=True)
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if TEST_DATABASE_URL is not None:
        monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    yield
    app.dependency_overrides.clear()


def guest() -> tuple[TestClient, UUID, str]:
    client = TestClient(app, base_url="https://testserver")
    response = client.post("/api/auth/guest")
    assert response.status_code == 201
    return client, UUID(response.json()["user"]["id"]), response.json()["csrf_token"]


def headers(csrf: str, key: str, revision: int | None = None) -> dict[str, str]:
    value = {
        "Origin": "https://testserver", "X-CSRF-Token": csrf,
        "Idempotency-Key": key,
    }
    if revision is not None:
        value["If-Match-Classroom-Revision"] = str(revision)
    return value


def seed_unit(owner_id: UUID, *, path: bool = False) -> UUID:
    async def insert() -> UUID:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                unit = LearningUnit(
                    user_id=owner_id, title="链表插入", status="ready",
                    knowledge_point_id="linked-list-insertion",
                )
                db.add(unit)
                await db.flush()
                for order, key in ((1, "intro"), (2, "followup")):
                    scene = LearningScene(
                        learning_unit_id=unit.id, scene_key=key,
                        scene_order=order, scene_type="first_learning", version=1,
                        generation_status="complete", review_status="passed",
                    )
                    db.add(scene)
                    await db.flush()
                    for kind, content in (
                        ("explanation", {"markdown": "旧讲解"}),
                        ("code", {"language": "Python", "source": "print(1)",
                                  "expected_output": "1", "key_steps": ["保存后继"],
                                  "display_only": True}),
                    ):
                        db.add(GeneratedResource(
                            user_id=owner_id, learning_unit_id=unit.id,
                            scene_id=scene.id, resource_type=kind, content=content,
                            review_status="passed", published_at=utc_now(),
                        ))
                if path:
                    graph = knowledge_graph_repository()
                    version = LearningPathVersion(
                        user_id=owner_id, target_node_id="linked-list-insertion",
                        version=1, graph_version=graph.graph_version,
                        profile_version=1, mastery_revision_watermark=0,
                        planner_rule_version="path-v1", nodes=[],
                        current_node_id="linked-list-insertion",
                        prerequisite_node_ids=["c-pointer", "linked-list-traversal"],
                        next_node_id=None, reasons=[],
                    )
                    db.add(version)
                    await db.flush()
                    db.add(LearningPathCurrent(
                        user_id=owner_id, target_node_id="linked-list-insertion",
                        path_version_id=version.id, replan_required=False,
                    ))
                await db.commit()
                return unit.id
        finally:
            await engine.dispose()
    return asyncio.run(insert())


def create_classroom(client: TestClient, csrf: str, unit_id: UUID) -> str:
    base = f"/api/learning-units/{unit_id}/classroom"
    response = client.post(base, headers=headers(csrf, f"control-create-{unit_id}"))
    assert response.status_code == 201
    return base


def control(
    client: TestClient, base: str, csrf: str, key: str, revision: int,
    body: dict[str, object],
):
    return client.post(f"{base}/controls", json=body,
                       headers=headers(csrf, key, revision))


def test_pause_resume_cas_replay_and_owner_isolation(database_url: None) -> None:
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id)
    base = create_classroom(client, csrf, unit_id)
    paused = control(client, base, csrf, "control-pause-key-01", 1, {"action": "pause"})
    assert paused.status_code == 200
    receipt = paused.json()
    assert receipt["paused"] is True
    assert receipt["revision"] == 2
    assert receipt["message_cursor"] == 0
    generation = receipt["generation_id"]
    replay = control(client, base, csrf, "control-pause-key-01", 1, {"action": "pause"})
    assert replay.json() == receipt
    bad_key = control(client, base, csrf, "control-pause-key-01", 2, {"action": "resume"})
    assert bad_key.status_code == 409
    assert bad_key.json()["code"] == "IDEMPOTENCY_CONFLICT"
    stale = control(client, base, csrf, "control-pause-key-02", 1, {"action": "resume"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "CLASSROOM_VERSION_CONFLICT"
    resumed = control(client, base, csrf, "control-resume-key-01", 2, {"action": "resume"})
    assert resumed.status_code == 200
    assert resumed.json()["paused"] is False
    assert resumed.json()["revision"] == 3
    assert resumed.json()["generation_id"] != generation
    assert control(client, base, csrf, "control-pause-key-01", 1,
                   {"action": "pause"}).json() == receipt
    foreign, _, foreign_csrf = guest()
    denied = control(foreign, base, foreign_csrf, "control-foreign-key", 3,
                     {"action": "pause"})
    assert denied.status_code == 404
    foreign.close()
    client.close()


def test_skip_advances_to_next_reviewed_scene_without_mastery_gain(database_url: None) -> None:
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id)
    base = create_classroom(client, csrf, unit_id)
    skipped = control(client, base, csrf, "control-skip-key-01", 1, {"action": "skip"})
    assert skipped.status_code == 200
    assert skipped.json()["scene_key"] == "followup"
    assert skipped.json()["scene_progress"] == 1
    assert skipped.json()["revision"] == 2
    assert client.get(base).json() == skipped.json()

    async def verify() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                assert await db.scalar(select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == owner_id,
                    LearningEvidence.evidence_type == "explicit_feedback",
                )) == 1
                score = await db.scalar(select(NodeMasteryCurrent.score).where(
                    NodeMasteryCurrent.user_id == owner_id,
                    NodeMasteryCurrent.knowledge_node_id == "linked-list-insertion",
                ))
                assert score == 0.0
        finally:
            await engine.dispose()
    asyncio.run(verify())
    client.close()


def test_select_resource_requires_current_publication_and_records_event(database_url: None) -> None:
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id)
    base = create_classroom(client, csrf, unit_id)
    selected = control(client, base, csrf, "control-select-code-01", 1,
                       {"action": "select_resource", "resource_type": "code"})
    assert selected.status_code == 200
    assert selected.json()["scene_key"] == "intro"
    unavailable = control(client, base, csrf, "control-select-animation-01", 2,
                          {"action": "select_resource", "resource_type": "animation"})
    assert unavailable.status_code == 422
    assert client.get(base).json()["revision"] == 2
    invalid = control(client, base, csrf, "control-select-invalid-01", 2,
                      {"action": "select_resource", "resource_type": "code",
                       "target_node_id": "c-pointer"})
    assert invalid.status_code == 422

    async def verify() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                events = list((await db.scalars(select(ProfileEvent).where(
                    ProfileEvent.user_id == owner_id,
                    ProfileEvent.event_type == "resource_selected",
                ))).all())
                assert len(events) == 1
                assert events[0].action == "code"
                assert events[0].schema_version == 2
                assert await db.scalar(select(func.count()).select_from(LearningEvidence).where(
                    LearningEvidence.user_id == owner_id,
                )) == 0
        finally:
            await engine.dispose()
    asyncio.run(verify())
    client.close()


def test_prerequisite_uses_current_path_and_restores_return_point(database_url: None) -> None:
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id, path=True)
    base = create_classroom(client, csrf, unit_id)
    invalid = control(client, base, csrf, "control-prereq-invalid", 1,
                      {"action": "prerequisite", "target_node_id": "array"})
    assert invalid.status_code == 422
    entered = control(client, base, csrf, "control-prereq-valid-01", 1,
                      {"action": "prerequisite", "target_node_id": "c-pointer"})
    assert entered.status_code == 200
    assert entered.json()["paused"] is True
    assert entered.json()["detour"]["target_node_id"] == "c-pointer"
    assert entered.json()["detour"]["scene_key"] == "intro"
    assert entered.json()["detour"]["path_version_id"]
    denied = control(client, base, csrf, "control-prereq-nested-01", 2,
                     {"action": "prerequisite", "target_node_id": "c-pointer"})
    assert denied.status_code == 409
    resumed = control(client, base, csrf, "control-prereq-resume-01", 2,
                      {"action": "resume"})
    assert resumed.status_code == 200
    assert resumed.json()["paused"] is False
    assert "detour" not in resumed.json()
    assert resumed.json()["scene_key"] == "intro"
    client.close()


def test_competing_controls_serialize_on_owner_and_cas(database_url: None) -> None:
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id)
    base = create_classroom(client, csrf, unit_id)

    async def compete() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            graph = knowledge_graph_repository()

            async def issue(key: str) -> str:
                async with sessions() as db:
                    try:
                        await apply_classroom_control(
                            db, owner_id=owner_id, unit_id=unit_id,
                            idempotency_key=key, expected_revision=1,
                            action="pause", resource_type=None, target_node_id=None,
                            graph=graph,
                        )
                    except ClassroomVersionConflict:
                        return "conflict"
                    return "published"

            assert sorted(await asyncio.gather(
                issue("control-race-key-01"), issue("control-race-key-02")
            )) == ["conflict", "published"]
        finally:
            await engine.dispose()
    asyncio.run(compete())
    assert client.get(base).json()["revision"] == 2
    client.close()
