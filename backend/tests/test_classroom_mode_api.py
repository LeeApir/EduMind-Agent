"""Classroom creation and focus/interactive mode switching API regression tests."""

import asyncio
import os
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.main import app
from app.models.classroom import ClassroomOperation
from app.models.learning import GeneratedResource, LearningScene, LearningUnit, utc_now
from app.services.classroom import ClassroomVersionConflict, set_classroom_mode

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    yield TEST_DATABASE_URL


def seed_unit_with_intro(
    owner_id: UUID, *, with_scene: bool = True, published: bool = True
) -> UUID:
    async def insert() -> UUID:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                unit = LearningUnit(user_id=owner_id, title="链表", status="ready")
                db.add(unit)
                await db.flush()
                if with_scene:
                    scene = LearningScene(
                            learning_unit_id=unit.id, scene_key="intro", scene_order=1,
                            scene_type="first_learning", version=1,
                            generation_status="complete", review_status="passed",
                        )
                    db.add(scene)
                    await db.flush()
                    db.add(GeneratedResource(
                        user_id=owner_id, learning_unit_id=unit.id, scene_id=scene.id,
                        resource_type="explanation", content={"text": "链表"},
                        review_status="passed", published_at=utc_now() if published else None,
                    ))
                await db.commit()
                return unit.id
        finally:
            await engine.dispose()

    return asyncio.run(insert())


def make_guest() -> tuple[TestClient, UUID, str]:
    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/auth/guest")
    assert created.status_code == 201
    return client, UUID(created.json()["user"]["id"]), created.json()["csrf_token"]


def write_headers(
    csrf: str, *, key: str | None = None, revision: int | None = None
) -> dict[str, str]:
    headers = {"X-CSRF-Token": csrf, "Origin": "https://testserver"}
    if key is not None:
        headers["Idempotency-Key"] = key
    if revision is not None:
        headers["If-Match-Classroom-Revision"] = str(revision)
    return headers


def test_get_classroom_returns_not_found_before_create(database_url: str) -> None:
    client, user_id, _ = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    response = client.get(f"/api/learning-units/{unit_id}/classroom")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_create_default_focus_classroom_and_idempotent_replay(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    path = f"/api/learning-units/{unit_id}/classroom"
    headers = write_headers(csrf, key="create-key-00001")
    created = client.post(path, headers=headers)
    assert created.status_code == 201
    snapshot = created.json()
    assert snapshot["mode"] == "focus"
    assert snapshot["revision"] == 1
    assert snapshot["enabled_roles"] == []
    assert snapshot["scene_key"] == "intro"
    assert snapshot["scene_version"] == 1
    assert snapshot["scene_progress"] == 0
    assert snapshot["message_cursor"] == 0
    assert snapshot["paused"] is False
    assert "generation_id" not in snapshot
    assert "detour" not in snapshot
    assert client.get(path).json() == snapshot
    replayed = client.post(path, headers=headers)
    assert replayed.status_code == 200
    assert replayed.json() == snapshot
    again = client.post(path, headers=write_headers(csrf, key="create-key-00002"))
    assert again.status_code == 200
    assert again.json() == snapshot


def test_create_requires_csrf_and_matching_origin(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    path = f"/api/learning-units/{unit_id}/classroom"
    missing = client.post(path, headers={"Idempotency-Key": "create-key-00003"})
    assert missing.status_code == 403
    foreign = client.post(
        path,
        headers={
            "X-CSRF-Token": csrf, "Origin": "https://evil.example",
            "Idempotency-Key": "create-key-00004",
        },
    )
    assert foreign.status_code == 403
    assert foreign.json()["code"] == "CSRF_FAILED"


def test_legacy_operation_without_original_receipt_does_not_return_current_state(
    database_url: str,
) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    path = f"/api/learning-units/{unit_id}/classroom"
    key = "create-key-legacy"
    assert client.post(path, headers=write_headers(csrf, key=key)).status_code == 201

    async def remove_receipt() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                await db.execute(
                    update(ClassroomOperation)
                    .where(ClassroomOperation.user_id == user_id,
                           ClassroomOperation.idempotency_key == key)
                    .values(result_snapshot=None)
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(remove_receipt())
    replay = client.post(path, headers=write_headers(csrf, key=key))
    assert replay.status_code == 409
    assert replay.json()["code"] == "IDEMPOTENCY_RESULT_UNAVAILABLE"


def test_create_requires_published_intro_scene(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id, with_scene=False)
    response = client.post(
        f"/api/learning-units/{unit_id}/classroom",
        headers=write_headers(csrf, key="create-key-00005"),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    unpublished_id = seed_unit_with_intro(user_id, published=False)
    unpublished = client.post(
        f"/api/learning-units/{unpublished_id}/classroom",
        headers=write_headers(csrf, key="create-key-unpublished"),
    )
    assert unpublished.status_code == 404


def test_mode_switch_to_interactive_and_back_to_focus(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    path = f"/api/learning-units/{unit_id}/classroom"
    client.post(path, headers=write_headers(csrf, key="create-key-00006"))
    mode_path = f"{path}/mode"
    interactive = client.patch(
        mode_path,
        json={"mode": "interactive", "enabled_roles": ["beginner", "advanced"]},
        headers=write_headers(csrf, key="mode-switch-key-00001", revision=1),
    )
    assert interactive.status_code == 200
    assert interactive.json()["mode"] == "interactive"
    assert interactive.json()["enabled_roles"] == ["advanced", "beginner"]
    assert interactive.json()["revision"] == 2
    first_gen = interactive.json()["generation_id"]
    assert first_gen is not None
    back = client.patch(
        mode_path,
        json={"mode": "focus", "enabled_roles": []},
        headers=write_headers(csrf, key="mode-switch-key-00002", revision=2),
    )
    assert back.status_code == 200
    assert back.json()["mode"] == "focus"
    assert back.json()["enabled_roles"] == []
    assert back.json()["revision"] == 3
    assert back.json()["generation_id"] != first_gen
    assert client.get(path).json() == back.json()


def test_mode_switch_version_conflict(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    path = f"/api/learning-units/{unit_id}/classroom"
    client.post(path, headers=write_headers(csrf, key="create-key-00007"))
    first = client.patch(
        f"{path}/mode",
        json={"mode": "interactive", "enabled_roles": ["beginner"]},
        headers=write_headers(csrf, key="mode-switch-key-00003", revision=1),
    )
    assert first.status_code == 200
    stale = client.patch(
        f"{path}/mode",
        json={"mode": "focus", "enabled_roles": []},
        headers=write_headers(csrf, key="mode-switch-key-00004", revision=1),
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "CLASSROOM_VERSION_CONFLICT"
    assert "2" in stale.json()["message"]


def test_mode_switch_idempotent_replay_and_digest_conflict(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    path = f"/api/learning-units/{unit_id}/classroom"
    client.post(path, headers=write_headers(csrf, key="create-key-00008"))
    key = "mode-switch-key-00005"
    first = client.patch(
        f"{path}/mode",
        json={"mode": "interactive", "enabled_roles": ["beginner"]},
        headers=write_headers(csrf, key=key, revision=1),
    )
    assert first.status_code == 200
    assert first.json()["revision"] == 2
    replayed = client.patch(
        f"{path}/mode",
        json={"mode": "interactive", "enabled_roles": ["beginner"]},
        headers=write_headers(csrf, key=key, revision=1),
    )
    assert replayed.status_code == 200
    assert replayed.json() == first.json()
    conflict = client.patch(
        f"{path}/mode",
        json={"mode": "interactive", "enabled_roles": ["advanced"]},
        headers=write_headers(csrf, key=key, revision=2),
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    later = client.patch(
        f"{path}/mode",
        json={"mode": "focus", "enabled_roles": []},
        headers=write_headers(csrf, key="mode-switch-key-later", revision=2),
    )
    assert later.status_code == 200
    assert later.json()["revision"] == 3
    old_replay = client.patch(
        f"{path}/mode",
        json={"mode": "interactive", "enabled_roles": ["beginner"]},
        headers=write_headers(csrf, key=key, revision=1),
    )
    assert old_replay.json() == first.json()
    create_replay = client.post(path, headers=write_headers(csrf, key="create-key-00008"))
    assert create_replay.json()["revision"] == 1
    new_create = client.post(path, headers=write_headers(csrf, key="create-key-after-mode"))
    assert new_create.status_code == 200
    assert new_create.json()["revision"] == 3
    assert client.get(path).json()["revision"] == 3


def test_focus_requires_empty_roles(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    path = f"/api/learning-units/{unit_id}/classroom"
    client.post(path, headers=write_headers(csrf, key="create-key-00009"))
    invalid = client.patch(
        f"{path}/mode",
        json={"mode": "focus", "enabled_roles": ["beginner"]},
        headers=write_headers(csrf, key="mode-switch-key-00006", revision=1),
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"


def test_classroom_is_owner_scoped(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    path = f"/api/learning-units/{unit_id}/classroom"
    client.post(path, headers=write_headers(csrf, key="create-key-00010"))
    other, _, other_csrf = make_guest()
    assert other.get(path).status_code == 404
    assert other.post(
        path, headers=write_headers(other_csrf, key="create-key-00011")
    ).status_code == 404
    assert other.patch(
        f"{path}/mode",
        json={"mode": "interactive", "enabled_roles": []},
        headers=write_headers(other_csrf, key="mode-switch-key-00007", revision=1),
    ).status_code == 404


def test_concurrent_mode_switch_same_key_is_idempotent(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    client.post(
        f"/api/learning-units/{unit_id}/classroom",
        headers=write_headers(csrf, key="create-key-00012"),
    )

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            key = "mode-switch-key-00008"

            async def switch() -> tuple[bool, int]:
                async with sessions() as db:
                    session, created = await set_classroom_mode(
                        db, owner_id=user_id, unit_id=unit_id, idempotency_key=key,
                        mode="interactive", enabled_roles=["beginner"], expected_revision=1,
                    )
                    return created, int(session["revision"])

            results = await asyncio.gather(switch(), switch())
            assert sorted(results) == [(False, 2), (True, 2)]
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_concurrent_mode_switch_distinct_keys_single_winner(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    unit_id = seed_unit_with_intro(user_id)
    client.post(
        f"/api/learning-units/{unit_id}/classroom",
        headers=write_headers(csrf, key="create-key-00013"),
    )

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)

            async def switch(key: str) -> int:
                async with sessions() as db:
                    session, _ = await set_classroom_mode(
                        db, owner_id=user_id, unit_id=unit_id, idempotency_key=key,
                        mode="interactive", enabled_roles=["beginner"], expected_revision=1,
                    )
                    return int(session["revision"])

            results = await asyncio.gather(
                switch("mode-switch-key-00009"), switch("mode-switch-key-00010"),
                return_exceptions=True,
            )
            assert sum(isinstance(result, ClassroomVersionConflict) for result in results) == 1
            assert [result for result in results if isinstance(result, int)] == [2]
        finally:
            await engine.dispose()

    asyncio.run(exercise())
