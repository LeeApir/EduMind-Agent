"""A transient profile is persisted under the authenticated anonymous owner only."""

import asyncio
import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.profile_agent import ProfileAgent
from app.agents.profile_events import PROFILE_MERGE_RULE_VERSION
from app.agents.profile_schema import empty_transient_profile
from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import StudentProfile
from app.services.owned_learning import latest_profile
from app.services.profile_updates import correct_profile
from app.services.provider_gateway import StructuredRequest, StructuredResult
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


def test_concurrent_initial_profiles_rebase_after_provider_without_lost_versions() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                owner = User(is_guest=True)
                db.add(owner)
                await db.commit()
                owner_id = owner.id
            barrier = asyncio.Event()
            calls = 0

            class BarrierGateway:
                async def generate_structured(
                    self, request: StructuredRequest, *, retry_safe: bool = False
                ) -> StructuredResult:
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        barrier.set()
                    await asyncio.wait_for(barrier.wait(), timeout=5)
                    return StructuredResult(
                        value=profile(request.prompt.messages[-1].content, 1), model_id="test"
                    )

            async def create(query: str) -> int:
                async with sessions() as db:
                    result = await create_transient_profile(
                        db,
                        owner_id=owner_id,
                        initial_query=query,
                        profile_agent=ProfileAgent(BarrierGateway()),
                    )
                    await db.commit()
                    return result.profile.version

            assert sorted(await asyncio.gather(create("学习数组"), create("学习队列"))) == [1, 2]
            async with sessions() as db:
                latest = await latest_profile(db, owner_id)
                assert latest is not None and latest.version == 2
                assert latest.previous_profile_id is not None
                assert latest.evidence["learning_goals"][-1]["profile_version"] == 2
        finally:
            await engine.dispose()

    asyncio.run(exercise())


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
            assert alice_first.profile.merge_rule_version == PROFILE_MERGE_RULE_VERSION
            assert alice_first.profile.previous_profile_id is None
            assert alice_second.profile.merge_rule_version == PROFILE_MERGE_RULE_VERSION
            assert alice_second.profile.previous_profile_id == alice_first.profile.id
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


def test_new_learning_keeps_manual_correction_and_old_snapshot() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                owner = User(is_guest=True)
                db.add(owner)
                await db.flush()
                owner_id = owner.id
                agent = ProfileAgent(
                    SequencedGateway(
                        [profile("学习链表", 1), profile("再看队列", 3), {"invalid": "profile"}]
                    )
                )
                first = await create_transient_profile(
                    db, owner_id=owner_id, initial_query="学习链表", profile_agent=agent
                )
                await db.commit()
                corrected, created = await correct_profile(
                    db,
                    owner_id=owner_id,
                    idempotency_key="review-correction-0001",
                    corrections={"learning_goals": {"current_topic": "数组"}},
                    expected_version=1,
                    observed_at="2026-09-25T18:48:26+08:00",
                )
                assert created is True
                second = await create_transient_profile(
                    db, owner_id=owner_id, initial_query="再看队列", profile_agent=agent
                )
                await db.commit()
                degraded = await create_transient_profile(
                    db, owner_id=owner_id, initial_query="Provider 失败", profile_agent=agent
                )
                await db.commit()

                assert [first.profile.version, corrected.version, second.profile.version] == [
                    1,
                    2,
                    3,
                ]
                assert second.profile.learning_goals == {"current_topic": "数组"}
                assert (
                    second.profile.evidence["learning_goals"][-2]["source"] == "manual_correction"
                )
                assert degraded.degraded is True
                assert degraded.profile.version == 4
                assert degraded.profile.learning_goals == {"current_topic": "数组"}
                assert (
                    degraded.profile.evidence["learning_goals"]
                    == second.profile.evidence["learning_goals"]
                )

            async with sessions() as db:
                rows = (
                    await db.scalars(
                        select(StudentProfile)
                        .where(StudentProfile.user_id == owner_id)
                        .order_by(StudentProfile.version)
                    )
                ).all()
                assert [row.version for row in rows] == [1, 2, 3, 4]
                assert [row.previous_profile_id for row in rows] == [
                    None,
                    rows[0].id,
                    rows[1].id,
                    rows[2].id,
                ]
                assert all(row.merge_rule_version == PROFILE_MERGE_RULE_VERSION for row in rows)
                assert rows[0].learning_goals == {"current_topic": "学习链表"}
                assert rows[1].learning_goals == {"current_topic": "数组"}
                assert rows[-1].learning_goals == {"current_topic": "数组"}
        finally:
            await engine.dispose()

    asyncio.run(exercise())
