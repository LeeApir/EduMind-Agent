"""Cross-user access control for persisted learning data."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.auth import token_hash
from app.core.database import create_database_engine
from app.main import app
from app.models.auth import GuestSessionRecord
from app.models.learning import GeneratedResource, LearningScene, LearningUnit, StudentProfile

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def test_owner_scoped_reads_hide_foreign_and_unpublished_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    with (
        TestClient(app, base_url="https://testserver") as alice,
        TestClient(app, base_url="https://testserver") as bob,
    ):
        alice_guest = alice.post("/api/auth/guest")
        bob_guest = bob.post("/api/auth/guest")
        assert alice_guest.status_code == bob_guest.status_code == 201
        alice_id = UUID(alice_guest.json()["user"]["id"])
        bob_id = UUID(bob_guest.json()["user"]["id"])

        async def seed() -> tuple[UUID, UUID, UUID, UUID]:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                factory = async_sessionmaker(engine, expire_on_commit=False)
                async with factory() as db:
                    db.add_all(
                        [
                            StudentProfile(
                                user_id=alice_id,
                                version=1,
                                learning_goals={"topic": "alice-private-topic"},
                            ),
                            StudentProfile(
                                user_id=bob_id,
                                version=1,
                                learning_goals={"topic": "bob-private-topic"},
                            ),
                        ]
                    )
                    unit = LearningUnit(
                        user_id=alice_id, title="alice-private-unit", status="ready"
                    )
                    draft = LearningUnit(user_id=alice_id, title="hidden-draft", status="draft")
                    db.add_all([unit, draft])
                    await db.flush()
                    scene = LearningScene(
                        learning_unit_id=unit.id,
                        scene_key="intro",
                        scene_order=1,
                        scene_type="explanation",
                        generation_status="complete",
                        review_status="passed",
                    )
                    db.add(scene)
                    await db.flush()
                    published = GeneratedResource(
                        user_id=alice_id,
                        learning_unit_id=unit.id,
                        scene_id=scene.id,
                        resource_type="explanation",
                        content={"markdown": "alice-private-resource"},
                        review_status="passed",
                        version=1,
                        published_at=datetime.now(timezone.utc),
                    )
                    candidate = GeneratedResource(
                        user_id=alice_id,
                        learning_unit_id=unit.id,
                        scene_id=scene.id,
                        resource_type="code",
                        content={"source": "unreviewed-private-code"},
                        review_status="pending",
                        version=1,
                    )
                    db.add_all([published, candidate])
                    await db.commit()
                    return unit.id, draft.id, published.id, candidate.id
            finally:
                await engine.dispose()

        unit_id, draft_id, published_id, candidate_id = asyncio.run(seed())
        alice_profile = alice.get("/api/profile/me")
        bob_profile = bob.get("/api/profile/me")
        assert alice_profile.status_code == bob_profile.status_code == 200
        assert alice_profile.json()["learning_goals"]["topic"] == "alice-private-topic"
        assert bob_profile.json()["learning_goals"]["topic"] == "bob-private-topic"
        assert "alice-private-topic" not in bob_profile.text

        visible_unit = alice.get(f"/api/learning-units/{unit_id}")
        visible_resource = alice.get(f"/api/resource/{published_id}")
        legacy_resource = alice.get(f"/api/resources/{published_id}")
        assert visible_unit.status_code == visible_resource.status_code == 200
        assert legacy_resource.json() == visible_resource.json()
        assert "alice-private-resource" in visible_unit.text
        assert "unreviewed-private-code" not in visible_unit.text
        assert visible_resource.json()["review_status"] == "passed"
        assert visible_unit.headers["cache-control"] == "no-store"

        missing_id = uuid4()
        missing_unit = bob.get(f"/api/learning-units/{missing_id}")
        foreign_unit = bob.get(f"/api/learning-units/{unit_id}")
        hidden_draft = alice.get(f"/api/learning-units/{draft_id}")
        assert (
            missing_unit.status_code == foreign_unit.status_code == hidden_draft.status_code == 404
        )
        assert missing_unit.json() == foreign_unit.json() == hidden_draft.json()

        missing_resource = bob.get(f"/api/resource/{missing_id}")
        foreign_resource = bob.get(f"/api/resource/{published_id}")
        unpublished_resource = alice.get(f"/api/resource/{candidate_id}")
        assert (
            missing_resource.status_code
            == foreign_resource.status_code
            == unpublished_resource.status_code
            == 404
        )
        assert missing_resource.json() == foreign_resource.json() == unpublished_resource.json()
        assert "alice-private-resource" not in foreign_resource.text

        with TestClient(app, base_url="https://testserver") as stranger:
            no_cookie = stranger.get(f"/api/resource/{published_id}")
            stranger.cookies.set("edumind_session", "invalid")
            invalid_cookie = stranger.get(f"/api/resource/{published_id}")
            stranger.cookies.clear()
            assert stranger.post("/api/auth/guest").status_code == 201
            absent_profile = stranger.get("/api/profile/me")
        assert no_cookie.status_code == invalid_cookie.status_code == 401
        assert no_cookie.json() == invalid_cookie.json()
        assert absent_profile.status_code == 404
        assert absent_profile.json() == missing_resource.json()

        async def expire_bob() -> None:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        update(GuestSessionRecord)
                        .where(
                            GuestSessionRecord.token_hash
                            == token_hash(bob_guest.cookies["edumind_session"])
                        )
                        .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                    )
            finally:
                await engine.dispose()

        asyncio.run(expire_bob())
        expired = bob.get(f"/api/resource/{published_id}")
        assert expired.status_code == 401
        assert "alice-private-resource" not in expired.text
