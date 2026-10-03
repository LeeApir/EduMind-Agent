"""PostgreSQL classroom session isolation, message cursor, and restart recovery."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.classroom import (
    ClassroomMessage,
    ClassroomRoleContext,
    ClassroomSession,
)
from app.models.learning import LearningUnit

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


async def _owner_unit(sessions: async_sessionmaker) -> tuple[User, LearningUnit]:
    async with sessions() as db:
        user = User(is_guest=True)
        db.add(user)
        await db.flush()
        unit = LearningUnit(user_id=user.id, title="链表", status="ready")
        db.add(unit)
        await db.commit()
        return user, unit


def test_one_current_session_per_owner_unit_and_owner_isolation() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            user, unit = await _owner_unit(sessions)
            other, other_unit = await _owner_unit(sessions)

            async with sessions() as db:
                session = ClassroomSession(
                    user_id=user.id, learning_unit_id=unit.id, scene_key="intro",
                )
                db.add(session)
                await db.commit()
                session_id = session.id
                assert session.mode == "focus" and session.revision == 1
                assert session.message_cursor == 0 and session.scene_progress == 0
                assert session.enabled_roles == []

            # a second current classroom for the same owner + unit is rejected
            with pytest.raises(IntegrityError):
                async with sessions() as db:
                    db.add(ClassroomSession(
                        user_id=user.id, learning_unit_id=unit.id, scene_key="intro",
                    ))
                    await db.commit()

            # a different owner gets an independent classroom for their own unit
            async with sessions() as db:
                other_session = ClassroomSession(
                    user_id=other.id, learning_unit_id=other_unit.id, scene_key="intro",
                )
                db.add(other_session)
                await db.commit()
                other_session_id = other_session.id

            # a classroom cannot point at another owner's learning unit
            with pytest.raises(IntegrityError):
                async with sessions() as db:
                    db.add(ClassroomSession(
                        user_id=user.id, learning_unit_id=other_unit.id, scene_key="intro",
                    ))
                    await db.commit()

            # mode is constrained to focus/interactive
            with pytest.raises(IntegrityError):
                async with sessions() as db:
                    await db.execute(
                        update(ClassroomSession).where(ClassroomSession.id == session_id)
                        .values(mode="debate")
                    )
                    await db.commit()

            assert session_id != other_session_id
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_message_cursor_is_monotonic_and_owner_scoped() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            user, unit = await _owner_unit(sessions)
            other, _ = await _owner_unit(sessions)

            async with sessions() as db:
                session = ClassroomSession(
                    user_id=user.id, learning_unit_id=unit.id, scene_key="intro",
                )
                db.add(session)
                await db.commit()
                session_id = session.id

            async with sessions() as db:
                db.add(ClassroomMessage(
                    session_id=session_id, user_id=user.id, message_cursor=1,
                    role="tutor", session_revision=1, scene_key="intro", scene_version=1,
                    text="先讲指针",
                ))
                await db.commit()
            async with sessions() as db:
                db.add(ClassroomMessage(
                    session_id=session_id, user_id=user.id, message_cursor=2,
                    role="student", session_revision=1, scene_key="intro", scene_version=1,
                    text="继续",
                ))
                await db.commit()
                session.message_cursor = 2
                await db.commit()

            # duplicate cursor within a session is rejected
            with pytest.raises(IntegrityError):
                async with sessions() as db:
                    db.add(ClassroomMessage(
                        session_id=session_id, user_id=user.id, message_cursor=2,
                        role="tutor", session_revision=1, scene_key="intro", scene_version=1,
                        text="重复游标",
                    ))
                    await db.commit()

            # a message must belong to the same owner as its session
            with pytest.raises(IntegrityError):
                async with sessions() as db:
                    db.add(ClassroomMessage(
                        session_id=session_id, user_id=other.id, message_cursor=3,
                        role="tutor", session_revision=1, scene_key="intro", scene_version=1,
                        text="越权",
                    ))
                    await db.commit()

            async with sessions() as db:
                cursors = (await db.execute(
                    select(ClassroomMessage.message_cursor).where(
                        ClassroomMessage.session_id == session_id,
                    ).order_by(ClassroomMessage.message_cursor)
                )).scalars().all()
                assert cursors == [1, 2]
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_role_context_separates_classroom_and_perspective() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            user, unit = await _owner_unit(sessions)

            async with sessions() as db:
                db.add(ClassroomRoleContext(
                    user_id=user.id, learning_unit_id=unit.id, context_kind="classroom",
                    role="tutor", scene_key="intro", scene_version=1,
                    summary={"focus": "指针"}, message_refs=[uuid4().hex],
                ))
                db.add(ClassroomRoleContext(
                    user_id=user.id, learning_unit_id=unit.id, context_kind="perspective",
                    role="performance", scene_key="intro", scene_version=1,
                ))
                await db.commit()

            # a perspective role cannot masquerade as a classroom role and vice versa
            with pytest.raises(IntegrityError):
                async with sessions() as db:
                    db.add(ClassroomRoleContext(
                        user_id=user.id, learning_unit_id=unit.id, context_kind="classroom",
                        role="performance", scene_key="intro", scene_version=2,
                    ))
                    await db.commit()
            with pytest.raises(IntegrityError):
                async with sessions() as db:
                    db.add(ClassroomRoleContext(
                        user_id=user.id, learning_unit_id=unit.id, context_kind="perspective",
                        role="tutor", scene_key="intro", scene_version=2,
                    ))
                    await db.commit()

            # the same role + scene + version is one context; a new scene version is a new one
            with pytest.raises(IntegrityError):
                async with sessions() as db:
                    db.add(ClassroomRoleContext(
                        user_id=user.id, learning_unit_id=unit.id, context_kind="classroom",
                        role="tutor", scene_key="intro", scene_version=1,
                    ))
                    await db.commit()
            async with sessions() as db:
                db.add(ClassroomRoleContext(
                    user_id=user.id, learning_unit_id=unit.id, context_kind="classroom",
                    role="tutor", scene_key="intro", scene_version=2,
                ))
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_restart_recovery_preserves_session_and_committed_messages() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            user, unit = await _owner_unit(sessions)
            async with sessions() as db:
                session = ClassroomSession(
                    user_id=user.id, learning_unit_id=unit.id,
                    scene_key="intro", scene_version=1, revision=3, message_cursor=2,
                    mode="interactive", enabled_roles=["beginner"], paused=True,
                )
                db.add(session)
                await db.flush()
                session_id = session.id
                db.add(ClassroomMessage(
                    session_id=session_id, user_id=user.id, message_cursor=1,
                    role="tutor", session_revision=3, scene_key="intro", scene_version=1,
                    text="已审核讲解", visible=True,
                ))
                db.add(ClassroomMessage(
                    session_id=session_id, user_id=user.id, message_cursor=2,
                    role="beginner", session_revision=3, scene_key="intro", scene_version=1,
                    text="同学补充", visible=True,
                ))
                await db.commit()
        finally:
            await engine.dispose()

        restarted = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(restarted, expire_on_commit=False)
            async with sessions() as db:
                restored = await db.scalar(select(ClassroomSession).where(
                    ClassroomSession.user_id == user.id,
                    ClassroomSession.learning_unit_id == unit.id,
                ))
                assert restored is not None and restored.id == session_id
                assert restored.mode == "interactive"
                assert restored.revision == 3 and restored.message_cursor == 2
                assert restored.enabled_roles == ["beginner"]
                assert restored.paused is True
                messages = (await db.execute(
                    select(ClassroomMessage).where(
                        ClassroomMessage.session_id == session_id,
                    ).order_by(ClassroomMessage.message_cursor)
                )).scalars().all()
                assert [m.message_cursor for m in messages] == [1, 2]
                assert [m.role for m in messages] == ["tutor", "beginner"]
        finally:
            await restarted.dispose()

    asyncio.run(exercise())
