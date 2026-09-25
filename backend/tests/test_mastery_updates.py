"""Evidence, mastery revision, and path staleness share one transaction."""

import asyncio
import os
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning_state import (
    LearningEvidence,
    LearningPathCurrent,
    LearningPathVersion,
    NodeMasteryCurrent,
    NodeMasteryRevision,
)
from app.services.mastery_updates import apply_mastery_evidence, lock_mastery_node

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def fact(owner_id: UUID, key: str, kind: str, payload: dict[str, object]) -> LearningEvidence:
    return LearningEvidence(
        user_id=owner_id,
        idempotency_key=key,
        request_digest="c" * 64,
        evidence_type=kind,
        knowledge_node_id="linked-list",
        schema_version=1,
        rule_version="test-event-v1",
        payload=payload,
    )


async def add_fact(db, record: LearningEvidence):
    await lock_mastery_node(db, owner_id=record.user_id, node_id=record.knowledge_node_id)
    db.add(record)
    await db.flush()
    return await apply_mastery_evidence(db, record)


def test_rollback_discards_evidence_and_mastery_together() -> None:
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
                record = fact(owner_id, "mastery-rollback-0001", "quiz_attempt", {"score": 1.0})
                change, stale = await add_fact(db, record)
                assert change is not None and change["score"] == 0.55
                assert stale is False
                await db.rollback()
            async with sessions() as db:
                evidence_count = await db.scalar(
                    select(func.count())
                    .select_from(LearningEvidence)
                    .where(LearningEvidence.user_id == owner_id)
                )
                revision_count = await db.scalar(
                    select(func.count())
                    .select_from(NodeMasteryRevision)
                    .where(NodeMasteryRevision.user_id == owner_id)
                )
                current = await db.get(NodeMasteryCurrent, (owner_id, "linked-list"))
                assert (evidence_count, revision_count, current) == (0, 0, None)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_no_score_change_keeps_revision_but_marks_existing_path_stale() -> None:
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
                version = LearningPathVersion(
                    user_id=owner_id,
                    target_node_id="linked-list",
                    version=1,
                    graph_version="graph-v1",
                    profile_version=1,
                    mastery_revision_watermark=0,
                    planner_rule_version="path-v1",
                    nodes=["linked-list"],
                    current_node_id="linked-list",
                    prerequisite_node_ids=[],
                    next_node_id=None,
                    reasons=[{"kind": "goal", "summary": "学习链表"}],
                )
                db.add(version)
                await db.flush()
                path_current = LearningPathCurrent(
                    user_id=owner_id,
                    target_node_id="linked-list",
                    path_version_id=version.id,
                    replan_required=False,
                )
                db.add(path_current)
                await db.commit()

                skip = fact(owner_id, "mastery-skip-0001", "explicit_feedback", {"action": "skip"})
                first_change, first_stale = await add_fact(db, skip)
                assert first_change is not None
                assert first_change["status"] == "weak"
                assert first_change["score"] == 0.0
                assert first_stale is True
                await db.commit()

                path_current.replan_required = False
                await db.commit()
                known = fact(
                    owner_id,
                    "mastery-known-0001",
                    "explicit_feedback",
                    {"action": "mark_known"},
                )
                second_change, second_stale = await add_fact(db, known)
                assert second_change is None
                assert second_stale is True
                await db.commit()

            async with sessions() as db:
                current = await db.get(NodeMasteryCurrent, (owner_id, "linked-list"))
                path = await db.get(LearningPathCurrent, (owner_id, "linked-list"))
                assert current is not None and path is not None
                assert current.revision == 1
                assert current.status == "weak"
                assert path.replan_required is True
                revision_count = await db.scalar(
                    select(func.count())
                    .select_from(NodeMasteryRevision)
                    .where(NodeMasteryRevision.user_id == owner_id)
                )
                assert revision_count == 1
        finally:
            await engine.dispose()

    asyncio.run(exercise())
