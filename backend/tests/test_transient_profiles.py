"""A transient profile is persisted under the authenticated anonymous owner only."""

import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.profile_agent import ProfileAgent
from app.agents.profile_schema import empty_transient_profile
from app.core.database import create_database_engine
from app.models.auth import User
from app.services.owned_learning import latest_profile
from app.services.provider_gateway import StructuredResult
from app.services.transient_profiles import create_transient_profile

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


class SequencedGateway:
    def __init__(self, profiles: list[dict[str, object]]) -> None:
        self._profiles = profiles

    async def generate_structured(
        self, request: object, *, retry_safe: bool = False
    ) -> StructuredResult:
        assert retry_safe is True
        return StructuredResult(value=self._profiles.pop(0), model_id="test")


def profile(query: str, version: int) -> dict[str, object]:
    value = empty_transient_profile(query)
    value["profile_version"] = version
    value["learning_goals"] = {"current_topic": query}
    value["evidence"] = {
        "learning_goals": [
            {
                "source": "initial_query",
                "confidence": 1.0,
                "observed_at": "2026-09-17T14:30:00+00:00",
                "profile_version": version,
            }
        ]
    }
    return value


def test_transient_profiles_increment_per_owner_and_hide_other_anonymous_session() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                alice = User(is_guest=True)
                bob = User(is_guest=True)
                db.add_all([alice, bob])
                await db.flush()
                alice_id, bob_id = alice.id, bob.id
                await db.commit()

            gateway = SequencedGateway(
                [profile("学习链表", 1), {"invalid": "profile"}, profile("再看链表", 2)]
            )
            agent = ProfileAgent(gateway)
            async with sessions() as db:
                alice_first = await create_transient_profile(
                    db, owner_id=alice_id, initial_query="学习链表", profile_agent=agent
                )
                bob_first = await create_transient_profile(
                    db, owner_id=bob_id, initial_query="学习队列", profile_agent=agent
                )
                alice_second = await create_transient_profile(
                    db, owner_id=alice_id, initial_query="再看链表", profile_agent=agent
                )
                await db.commit()

            assert alice_first.profile.version == 1
            assert alice_second.profile.version == 2
            assert bob_first.profile.version == 1
            assert bob_first.degraded is True
            async with sessions() as db:
                alice_profile = await latest_profile(db, alice_id)
                bob_profile = await latest_profile(db, bob_id)
                assert alice_profile is not None and bob_profile is not None
                assert alice_profile.initial_query == "再看链表"
                assert bob_profile.initial_query == "学习队列"
                assert bob_profile.learning_goals is None
                assert bob_profile.user_id != alice_profile.user_id
                assert "再看链表" not in str(bob_profile.learning_goals)
        finally:
            await engine.dispose()

    asyncio.run(exercise())
