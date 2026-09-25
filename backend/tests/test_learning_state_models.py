"""PostgreSQL constraints for MVP 0.2 evidence, mastery, and path versions."""

import asyncio
import os
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def evidence(owner_id: UUID, key: str) -> LearningEvidence:
    return LearningEvidence(
        user_id=owner_id,
        idempotency_key=key,
        request_digest="a" * 64,
        evidence_type="quiz_attempt",
        knowledge_node_id="linked-list",
        schema_version=1,
        rule_version="quiz-exact-text-v1",
        payload={"question_results": [{"question_id": "q1", "correct": True}]},
    )


def mastery(
    owner_id: UUID,
    evidence_id: UUID,
    *,
    revision: int = 1,
    score: float = 0.5,
    status: str = "learning",
) -> NodeMasteryRevision:
    return NodeMasteryRevision(
        user_id=owner_id,
        knowledge_node_id="linked-list",
        revision=revision,
        previous_score=0.0,
        score=score,
        status=status,
        rule_version="mastery-v1",
        evidence_id=evidence_id,
        evidence_summary=["quiz 1/2"],
    )


def path(owner_id: UUID, *, version: int = 1) -> LearningPathVersion:
    return LearningPathVersion(
        user_id=owner_id,
        target_node_id="linked-list",
        version=version,
        graph_version="graph-v1",
        profile_version=1,
        mastery_revision_watermark=1,
        planner_rule_version="path-v1",
        nodes=["array", "linked-list"],
        current_node_id="linked-list",
        prerequisite_node_ids=["array"],
        next_node_id=None,
        reasons=[{"kind": "prerequisite", "summary": "先学数组"}],
    )


def test_evidence_idempotency_is_owner_scoped_and_payload_survives_restart() -> None:
    assert TEST_DATABASE_URL is not None
    captured: list[UUID] = []

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                alice, bob = User(is_guest=True), User(is_guest=True)
                db.add_all([alice, bob])
                await db.flush()
                first = evidence(alice.id, "quiz-key-0001")
                other = evidence(bob.id, "quiz-key-0001")
                db.add_all([first, other])
                await db.commit()
                assert first.id != other.id
                captured.extend([alice.id, first.id])
                other_id = other.id
                db.add(evidence(alice.id, "quiz-key-0001"))
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
                cross_owner = evidence(captured[0], "quiz-key-0003")
                cross_owner.corrects_evidence_id = other_id
                db.add(cross_owner)
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
        finally:
            await engine.dispose()

        read_engine = create_database_engine(TEST_DATABASE_URL)
        try:
            read_sessions = async_sessionmaker(read_engine)
            async with read_sessions() as db:
                records = (
                    await db.scalars(
                        select(LearningEvidence).where(LearningEvidence.user_id == captured[0])
                    )
                ).all()
                assert [record.id for record in records] == [captured[1]]
                assert records[0].payload["question_results"] == [
                    {"question_id": "q1", "correct": True}
                ]
        finally:
            await read_engine.dispose()

    asyncio.run(exercise())


def test_mastery_revision_and_current_projection_enforce_score_status_and_version() -> None:
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
                fact = evidence(owner_id, "quiz-key-0002")
                db.add(fact)
                await db.flush()
                fact_id = fact.id
                first = mastery(owner_id, fact_id)
                db.add(first)
                await db.flush()
                current = NodeMasteryCurrent(
                    user_id=owner_id,
                    knowledge_node_id="linked-list",
                    revision_id=first.id,
                    revision=1,
                    score=0.5,
                    status="learning",
                    rule_version="mastery-v1",
                )
                db.add(current)
                await db.commit()

                invalid_revisions = [
                    mastery(owner_id, fact_id, revision=1),
                    mastery(owner_id, fact_id, revision=2, score=-0.1),
                    mastery(owner_id, fact_id, revision=2, score=1.1),
                    mastery(owner_id, fact_id, revision=2, status="guessed"),
                    mastery(owner_id, fact_id, revision=0),
                ]
                for invalid in invalid_revisions:
                    db.add(invalid)
                    with pytest.raises(IntegrityError):
                        await db.commit()
                    await db.rollback()

                current = await db.get(NodeMasteryCurrent, (owner_id, "linked-list"))
                assert current is not None
                current.score = 1.2
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
                stored = await db.get(NodeMasteryCurrent, (owner_id, "linked-list"))
                assert stored is not None and stored.score == 0.5
                foreign_owner = User(is_guest=True)
                db.add(foreign_owner)
                await db.flush()
                foreign_id = foreign_owner.id
                foreign_fact = evidence(foreign_id, "quiz-key-0004")
                db.add(foreign_fact)
                await db.flush()
                foreign_fact_id = foreign_fact.id
                await db.commit()
                db.add(mastery(owner_id, foreign_fact_id, revision=2))
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
                foreign_revision = mastery(foreign_id, foreign_fact_id)
                db.add(foreign_revision)
                await db.commit()
                current = await db.get(NodeMasteryCurrent, (owner_id, "linked-list"))
                assert current is not None
                current.revision_id = foreign_revision.id
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_path_version_unique_per_owner_target_and_current_pointer_survives_restart() -> None:
    assert TEST_DATABASE_URL is not None
    captured: list[UUID] = []

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                owner = User(is_guest=True)
                db.add(owner)
                await db.flush()
                owner_id = owner.id
                first = path(owner_id)
                db.add(first)
                await db.flush()
                db.add(
                    LearningPathCurrent(
                        user_id=owner_id,
                        target_node_id="linked-list",
                        path_version_id=first.id,
                        replan_required=True,
                    )
                )
                await db.commit()
                captured.extend([owner_id, first.id])

                db.add(path(owner_id))
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
                db.add(path(owner_id, version=0))
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
                foreign_owner = User(is_guest=True)
                db.add(foreign_owner)
                await db.flush()
                foreign_path = path(foreign_owner.id)
                db.add(foreign_path)
                await db.commit()
                current = await db.get(LearningPathCurrent, (owner_id, "linked-list"))
                assert current is not None
                current.path_version_id = foreign_path.id
                with pytest.raises(IntegrityError):
                    await db.commit()
                await db.rollback()
        finally:
            await engine.dispose()

        read_engine = create_database_engine(TEST_DATABASE_URL)
        try:
            read_sessions = async_sessionmaker(read_engine)
            async with read_sessions() as db:
                current = await db.get(LearningPathCurrent, (captured[0], "linked-list"))
                assert current is not None
                assert current.path_version_id == captured[1]
                assert current.replan_required is True
                version = await db.get(LearningPathVersion, current.path_version_id)
                assert version is not None
                assert version.nodes == ["array", "linked-list"]
                assert version.graph_version == "graph-v1"
        finally:
            await read_engine.dispose()

    asyncio.run(exercise())
