"""Profile read, history, correction, and event API regression tests."""

import asyncio
import os
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.main import app
from app.models.learning import StudentProfile

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    yield TEST_DATABASE_URL


def seed_profile(user_id: UUID, *, version: int) -> None:
    async def insert() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                db.add(
                    StudentProfile(
                        user_id=user_id,
                        version=version,
                        initial_query="我想理解链表",
                        learning_goals={"current_topic": "链表"},
                        evidence={
                            "learning_goals": [
                                {
                                    "source": "initial_query",
                                    "confidence": 0.9,
                                    "observed_at": "2026-09-23T15:00:00+08:00",
                                    "profile_version": version,
                                }
                            ]
                        },
                    )
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(insert())


def make_guest() -> tuple[TestClient, UUID, str]:
    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/auth/guest")
    assert created.status_code == 201
    return client, UUID(created.json()["user"]["id"]), created.json()["csrf_token"]


def write_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf, "Origin": "https://testserver"}


def test_reads_and_history_are_owner_scoped(database_url: str) -> None:
    client, user_id, _ = make_guest()
    seed_profile(user_id, version=1)
    seed_profile(user_id, version=2)
    seed_profile(user_id, version=3)

    me = client.get("/api/profile/me")
    assert me.status_code == 200
    assert me.json()["version"] == 3

    history = client.get("/api/profile/me/history")
    assert history.status_code == 200
    assert [item["version"] for item in history.json()["items"]] == [3, 2, 1]
    assert history.json()["next_before_version"] is None

    page = client.get("/api/profile/me/history", params={"limit": 2})
    assert [item["version"] for item in page.json()["items"]] == [3, 2]
    assert page.json()["next_before_version"] == 2

    older = client.get("/api/profile/me/history", params={"before_version": 2})
    assert [item["version"] for item in older.json()["items"]] == [1]
    assert older.json()["next_before_version"] is None

    foreign, foreign_id, _ = make_guest()
    seed_profile(foreign_id, version=1)
    assert foreign.get("/api/profile/me").json()["id"] != me.json()["id"]
    foreign_history = foreign.get("/api/profile/me/history")
    assert [item["version"] for item in foreign_history.json()["items"]] == [1]
    assert all(str(item["id"]) != str(me.json()["id"]) for item in foreign_history.json()["items"])


def test_missing_profile_returns_not_found(database_url: str) -> None:
    client, _, _ = make_guest()
    missing = client.get("/api/profile/me")
    assert missing.status_code == 404
    assert missing.json()["code"] == "NOT_FOUND"


def test_patch_applies_whitelisted_correction_with_manual_evidence(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    seed_profile(user_id, version=1)

    patched = client.patch(
        "/api/profile/me",
        json={"learning_goals": {"current_topic": "数组"}},
        headers={
            **write_headers(csrf),
            "Idempotency-Key": "correct-key-00001",
            "If-Match-Profile-Version": "1",
        },
    )
    assert patched.status_code == 200
    assert patched.json()["version"] == 2
    assert patched.json()["learning_goals"] == {"current_topic": "数组"}
    records = patched.json()["evidence"]["learning_goals"]
    assert records[-1]["source"] == "manual_correction"
    assert client.get("/api/profile/me").json()["version"] == 2


def test_patch_rejects_non_editable_and_empty_fields(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    seed_profile(user_id, version=1)
    headers = {
        **write_headers(csrf),
        "Idempotency-Key": "correct-key-00002",
        "If-Match-Profile-Version": "1",
    }
    non_editable = client.patch(
        "/api/profile/me", json={"knowledge_base": {"topic": "链表"}}, headers=headers
    )
    assert non_editable.status_code == 422
    assert non_editable.json()["code"] == "VALIDATION_ERROR"
    empty = client.patch("/api/profile/me", json={}, headers=headers)
    assert empty.status_code == 422
    assert empty.json()["code"] == "VALIDATION_ERROR"


def test_patch_requires_csrf_and_matching_origin(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    seed_profile(user_id, version=1)
    body = {"learning_goals": {"current_topic": "数组"}}
    missing = client.patch(
        "/api/profile/me",
        json=body,
        headers={"Idempotency-Key": "correct-key-00003", "If-Match-Profile-Version": "1"},
    )
    foreign = client.patch(
        "/api/profile/me",
        json=body,
        headers={
            "X-CSRF-Token": csrf,
            "Origin": "https://evil.example",
            "Idempotency-Key": "correct-key-00004",
            "If-Match-Profile-Version": "1",
        },
    )
    assert missing.status_code == 403
    assert foreign.status_code == 403
    assert missing.json()["code"] == "CSRF_FAILED"


def test_patch_version_conflict_and_idempotent_replay(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    seed_profile(user_id, version=1)

    stale = client.patch(
        "/api/profile/me",
        json={"learning_goals": {"current_topic": "数组"}},
        headers={
            **write_headers(csrf),
            "Idempotency-Key": "correct-key-00005",
            "If-Match-Profile-Version": "2",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "PROFILE_VERSION_CONFLICT"

    replay_key = "correct-key-00006"
    first = client.patch(
        "/api/profile/me",
        json={"learning_goals": {"current_topic": "数组"}},
        headers={
            **write_headers(csrf),
            "Idempotency-Key": replay_key,
            "If-Match-Profile-Version": "1",
        },
    )
    assert first.status_code == 200
    assert first.json()["version"] == 2
    replayed = client.patch(
        "/api/profile/me",
        json={"learning_goals": {"current_topic": "数组"}},
        headers={
            **write_headers(csrf),
            "Idempotency-Key": replay_key,
            "If-Match-Profile-Version": "1",
        },
    )
    assert replayed.status_code == 200
    assert replayed.json()["id"] == first.json()["id"]
    assert client.get("/api/profile/me").json()["version"] == 2
    conflicting = client.patch(
        "/api/profile/me",
        json={"learning_goals": {"current_topic": "图"}},
        headers={
            **write_headers(csrf),
            "Idempotency-Key": replay_key,
            "If-Match-Profile-Version": "2",
        },
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_record_event_returns_receipt_and_deduplicates(database_url: str) -> None:
    client, user_id, csrf = make_guest()
    key = "event-key-000001"
    body = {"event_type": "hint_used", "knowledge_node_id": "linked-list", "action": "hint_level_1"}
    first = client.post(
        "/api/profile/events", json=body, headers={**write_headers(csrf), "Idempotency-Key": key}
    )
    assert first.status_code == 202
    assert first.json()["event_type"] == "hint_used"
    assert first.json()["profile_update_status"] == "queued"
    replayed = client.post(
        "/api/profile/events", json=body, headers={**write_headers(csrf), "Idempotency-Key": key}
    )
    assert replayed.status_code == 202
    assert replayed.json()["evidence_id"] == first.json()["evidence_id"]
    invalid = client.post(
        "/api/profile/events",
        json={"event_type": "hint_used", "knowledge_node_id": "linked-list", "action": "code"},
        headers={**write_headers(csrf), "Idempotency-Key": "event-key-000002"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"
