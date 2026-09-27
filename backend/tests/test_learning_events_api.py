"""Owner-bound behavior commands create auditable evidence and mastery revisions."""

import asyncio
import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.main import app
from app.models.learning import LearningScene, LearningUnit
from app.models.learning_state import LearningEvidence, NodeMasteryCurrent
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.learning_events import record_learning_action

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")
NODE = "linked-list-concept"


def make_guest() -> tuple[TestClient, UUID, str]:
    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/auth/guest")
    assert created.status_code == 201
    return client, UUID(created.json()["user"]["id"]), created.json()["csrf_token"]


def seed_scene(owner_id: UUID, *, reviewed: bool = True) -> tuple[UUID, UUID]:
    assert TEST_DATABASE_URL is not None

    async def insert() -> tuple[UUID, UUID]:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                unit = LearningUnit(
                    user_id=owner_id,
                    knowledge_point_id=NODE,
                    title="单链表",
                    status="ready",
                )
                db.add(unit)
                await db.flush()
                scene = LearningScene(
                    learning_unit_id=unit.id,
                    scene_key="intro",
                    scene_order=1,
                    scene_type="first_learning",
                    generation_status="complete",
                    review_status="passed" if reviewed else "pending",
                )
                db.add(scene)
                await db.commit()
                return unit.id, scene.id
        finally:
            await engine.dispose()

    return asyncio.run(insert())


def body(unit_id: UUID, scene_id: UUID, kind: str, action: str) -> dict[str, str]:
    return {
        "event_type": kind,
        "knowledge_node_id": NODE,
        "learning_unit_id": str(unit_id),
        "scene_id": str(scene_id),
        "action": action,
    }


def headers(csrf: str, key: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf, "Origin": "https://testserver", "Idempotency-Key": key}


@pytest.mark.parametrize(
    ("kind", "action", "has_hint"),
    [
        ("hint_used", "hint_level_1", True),
        ("hint_used", "hint_level_2", True),
        ("reexplanation_requested", "simpler", False),
        ("explicit_feedback", "skip", False),
        ("explicit_feedback", "mark_known", False),
        ("explicit_feedback", "too_hard", False),
    ],
)
def test_whitelisted_action_is_owned_and_idempotent(
    monkeypatch: pytest.MonkeyPatch, kind: str, action: str, has_hint: bool
) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    client, owner_id, csrf = make_guest()
    unit_id, scene_id = seed_scene(owner_id)
    request = body(unit_id, scene_id, kind, action)
    key = f"learning-{kind}-{action}-key"
    first = client.post("/api/learning-events", json=request, headers=headers(csrf, key))
    assert first.status_code == 200
    data = first.json()
    assert data["event_type"] == kind
    assert data["action"] == action
    assert data["knowledge_node_id"] == NODE
    assert bool(data["hint_text"]) is has_hint
    if has_hint:
        assert "回顾学习目标" in data["hint_text"] or "检查常见误区" in data["hint_text"]
    assert data["mastery_changes"][0]["rule_version"] == "mastery-v1"
    assert data["mastery_changes"][0]["status"] != "mastered"

    replay = client.post("/api/learning-events", json=request, headers=headers(csrf, key))
    assert replay.status_code == 200
    assert replay.json() == data

    async def check() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine)
            async with sessions() as db:
                count = await db.scalar(
                    select(func.count())
                    .select_from(LearningEvidence)
                    .where(LearningEvidence.user_id == owner_id)
                )
                assert count == 1
                record = await db.get(LearningEvidence, UUID(data["evidence_id"]))
                assert record is not None
                assert record.learning_unit_id == unit_id
                assert record.scene_id == scene_id
                assert record.knowledge_node_id == NODE
                current = await db.get(NodeMasteryCurrent, (owner_id, NODE))
                assert current is not None
                assert current.status != "mastered"
        finally:
            await engine.dispose()

    asyncio.run(check())


def test_foreign_scene_wrong_node_unreviewed_and_invalid_actions_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    owner, owner_id, csrf = make_guest()
    other, _, other_csrf = make_guest()
    unit_id, scene_id = seed_scene(owner_id)
    draft_unit, draft_scene = seed_scene(owner_id, reviewed=False)
    key = "learning-invalid-key-0001"
    valid = body(unit_id, scene_id, "hint_used", "hint_level_1")

    foreign = other.post("/api/learning-events", json=valid, headers=headers(other_csrf, key))
    assert foreign.status_code == 404
    draft = owner.post(
        "/api/learning-events",
        json=body(draft_unit, draft_scene, "hint_used", "hint_level_1"),
        headers=headers(csrf, key),
    )
    assert draft.status_code == 404
    wrong_node = owner.post(
        "/api/learning-events",
        json={**valid, "knowledge_node_id": "array"},
        headers=headers(csrf, key),
    )
    assert wrong_node.status_code == 404
    for invalid in [
        {**valid, "action": "hint_level_3"},
        {**valid, "event_type": "explicit_feedback"},
        {**valid, "score": 1.0},
    ]:
        result = owner.post("/api/learning-events", json=invalid, headers=headers(csrf, key))
        assert result.status_code == 422

    accepted = owner.post("/api/learning-events", json=valid, headers=headers(csrf, key))
    assert accepted.status_code == 200
    conflict = owner.post(
        "/api/learning-events",
        json=body(unit_id, scene_id, "hint_used", "hint_level_2"),
        headers=headers(csrf, key),
    )
    assert conflict.status_code == 409


def test_learning_action_requires_csrf(monkeypatch: pytest.MonkeyPatch) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    client, owner_id, csrf = make_guest()
    unit_id, scene_id = seed_scene(owner_id)
    request = body(unit_id, scene_id, "explicit_feedback", "skip")
    missing = client.post(
        "/api/learning-events", json=request, headers={"Idempotency-Key": "learning-csrf-key-0001"}
    )
    assert missing.status_code == 403
    bad_origin = client.post(
        "/api/learning-events",
        json=request,
        headers={**headers(csrf, "learning-csrf-key-0001"), "Origin": "https://evil.example"},
    )
    assert bad_origin.status_code == 403


def test_projection_failure_rolls_back_learning_action(monkeypatch: pytest.MonkeyPatch) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    client, owner_id, _ = make_guest()
    unit_id, scene_id = seed_scene(owner_id)

    async def fail_projection(*_args: object, **_kwargs: object):
        raise RuntimeError("injected projection failure")

    monkeypatch.setattr("app.services.learning_events.apply_mastery_evidence", fail_projection)

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            with pytest.raises(RuntimeError, match="injected projection failure"):
                async with sessions() as db:
                    await record_learning_action(
                        db,
                        owner_id=owner_id,
                        idempotency_key="learning-rollback-key-0001",
                        event_type="explicit_feedback",
                        node_id=NODE,
                        unit_id=unit_id,
                        scene_id=scene_id,
                        action="skip",
                        repository=default_knowledge_graph_repository(),
                    )
            async with sessions() as db:
                count = await db.scalar(
                    select(func.count())
                    .select_from(LearningEvidence)
                    .where(LearningEvidence.user_id == owner_id)
                )
                current = await db.get(NodeMasteryCurrent, (owner_id, NODE))
                assert count == 0
                assert current is None
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    client.close()
