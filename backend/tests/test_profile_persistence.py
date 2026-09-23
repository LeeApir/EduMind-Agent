"""PostgreSQL persistence of profile events and immutable profile versions."""

import asyncio
import os
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.profile_events import ProfileEventSchemaError
from app.agents.profile_schema import merge_explicit_profile_values
from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import ProfileEvent, StudentProfile
from app.services.learning_operations import IdempotencyConflict
from app.services.profile_updates import (
    ProfileVersionConflict,
    persist_profile_version,
    record_profile_event,
)

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def event(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "hint_used",
        "knowledge_node_id": "linked-list",
        "action": "hint_level_1",
    }
    payload.update(overrides)
    return payload


def profile(version: int) -> dict[str, object]:
    return merge_explicit_profile_values(
        "想理解链表",
        {"learning_goals": {"current_topic": "链表"}},
        {
            "learning_goals": [
                {
                    "source": "initial_query",
                    "confidence": 0.9,
                    "observed_at": "2026-09-23T15:00:00+08:00",
                    "profile_version": version,
                }
            ]
        },
        profile_version=version,
    )


def test_events_are_idempotent_and_owner_scoped() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                user = User(is_guest=True)
                db.add(user)
                await db.flush()
                key = "idem-event-0001"
                first, created = await record_profile_event(
                    db, owner_id=user.id, idempotency_key=key, event=event()
                )
                assert created is True
                second, replayed = await record_profile_event(
                    db, owner_id=user.id, idempotency_key=key, event=event()
                )
                assert replayed is False
                assert second.id == first.id
                count = await db.scalar(
                    select(func.count())
                    .select_from(ProfileEvent)
                    .where(ProfileEvent.user_id == user.id)
                )
                assert count == 1
                with pytest.raises(IdempotencyConflict):
                    await record_profile_event(
                        db,
                        owner_id=user.id,
                        idempotency_key=key,
                        event=event(action="hint_level_2"),
                    )
                other = User(is_guest=True)
                db.add(other)
                await db.flush()
                third, created_other = await record_profile_event(
                    db, owner_id=other.id, idempotency_key=key, event=event()
                )
                assert created_other is True
                assert third.id != first.id
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_invalid_event_is_rejected_before_persistence() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                user = User(is_guest=True)
                db.add(user)
                await db.flush()
                with pytest.raises(ProfileEventSchemaError):
                    await record_profile_event(
                        db,
                        owner_id=user.id,
                        idempotency_key="bad-key-0001",
                        event=event(action="code"),
                    )
                count = await db.scalar(
                    select(func.count())
                    .select_from(ProfileEvent)
                    .where(ProfileEvent.user_id == user.id)
                )
                assert count == 0
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_profile_versions_are_immutable_and_survive_restart() -> None:
    assert TEST_DATABASE_URL is not None
    captured: list[UUID] = []

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                user = User(is_guest=True)
                db.add(user)
                await db.flush()
                captured.append(user.id)
                v1 = await persist_profile_version(db, owner_id=user.id, profile=profile(1))
                v2 = await persist_profile_version(db, owner_id=user.id, profile=profile(2))
                assert (v1.version, v2.version) == (1, 2)
                assert v1.id != v2.id
                # Version 1 is not overwritten by version 2.
                assert v1.learning_goals == {"current_topic": "链表"}
        finally:
            await engine.dispose()

        read_engine = create_database_engine(TEST_DATABASE_URL)
        try:
            read_sessions = async_sessionmaker(read_engine)
            async with read_sessions() as db:
                versions = (
                    await db.scalars(
                        select(StudentProfile)
                        .where(StudentProfile.user_id == captured[0])
                        .order_by(StudentProfile.version)
                    )
                ).all()
                assert [profile.version for profile in versions] == [1, 2]
                assert versions[-1].version == 2
        finally:
            await read_engine.dispose()

    asyncio.run(exercise())


def test_stale_or_skipping_version_is_rejected() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                user = User(is_guest=True)
                db.add(user)
                await db.flush()
                await persist_profile_version(db, owner_id=user.id, profile=profile(1))
                await persist_profile_version(db, owner_id=user.id, profile=profile(2))
                # A stale writer still claiming version 2 no longer matches latest 2.
                with pytest.raises(ProfileVersionConflict):
                    await persist_profile_version(db, owner_id=user.id, profile=profile(2))
                # Skipping ahead is also rejected.
                with pytest.raises(ProfileVersionConflict):
                    await persist_profile_version(db, owner_id=user.id, profile=profile(5))
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_duplicate_version_violates_database_constraint() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                user = User(is_guest=True)
                db.add(user)
                await db.flush()
                await persist_profile_version(db, owner_id=user.id, profile=profile(1))
                # Bypass the service to prove the (user_id, version) constraint holds.
                db.add(StudentProfile(user_id=user.id, version=1))
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
