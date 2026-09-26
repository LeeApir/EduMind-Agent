"""PostgreSQL path snapshots survive replay, input updates, and process restart."""

import asyncio
import os
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.profile_schema import apply_manual_correction, empty_transient_profile
from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning_state import (
    LearningEvidence,
    LearningPathCurrent,
    LearningPathVersion,
    NodeMasteryCurrent,
    NodeMasteryRevision,
)
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.owned_learning import latest_profile
from app.services.path_versions import current_path_version, plan_or_replan_path
from app.services.profile_updates import persist_profile_version, snapshot_profile

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


async def add_mastered_pointer(sessions: async_sessionmaker[AsyncSession], owner_id: UUID) -> None:
    async with sessions() as db:
        evidence = LearningEvidence(
            user_id=owner_id,
            idempotency_key="path-mastery-evidence-1",
            request_digest="a" * 64,
            evidence_type="quiz_attempt",
            knowledge_node_id="c-pointer",
            schema_version=1,
            rule_version="quiz-scoring-v1",
            payload={"score": 1.0},
        )
        db.add(evidence)
        await db.flush()
        revision = NodeMasteryRevision(
            user_id=owner_id,
            knowledge_node_id="c-pointer",
            revision=1,
            previous_score=0.0,
            score=0.9,
            status="mastered",
            rule_version="mastery-v1",
            evidence_id=evidence.id,
            evidence_summary=["quiz_score=1.0000;wrong_streak=0"],
        )
        db.add(revision)
        await db.flush()
        db.add(
            NodeMasteryCurrent(
                user_id=owner_id,
                knowledge_node_id="c-pointer",
                revision_id=revision.id,
                revision=1,
                score=0.9,
                status="mastered",
                rule_version="mastery-v1",
            )
        )
        await db.commit()


def test_path_versions_are_idempotent_historic_and_restart_safe() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        graph = default_knowledge_graph_repository()
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                owner = User(is_guest=True)
                db.add(owner)
                await db.flush()
                owner_id = owner.id
                await persist_profile_version(
                    db, owner_id=owner_id, profile=empty_transient_profile("想学习单链表")
                )
            async with sessions() as db:
                initial, created = await plan_or_replan_path(
                    db,
                    owner_id=owner_id,
                    target_node_id="single-linked-list",
                    graph=graph,
                    trigger_reason="initial_plan",
                )
                assert created is True
                assert initial.version == 1
                assert initial.profile_version == 1
                assert initial.mastery_revision_watermark == 0
                assert initial.current_node_id == "c-pointer"
                assert [node["node_id"] for node in initial.nodes][-1] == "single-linked-list"
                initial_id = initial.id
            async with sessions() as db:
                replay, created = await plan_or_replan_path(
                    db,
                    owner_id=owner_id,
                    target_node_id="single-linked-list",
                    graph=graph,
                    trigger_reason="learner_request",
                )
                assert created is False
                assert replay.id == initial_id

            async def concurrent_replay() -> tuple[UUID, bool]:
                async with sessions() as db:
                    version, created = await plan_or_replan_path(
                        db,
                        owner_id=owner_id,
                        target_node_id="single-linked-list",
                        graph=graph,
                        trigger_reason="learner_request",
                    )
                    return version.id, created

            assert await asyncio.gather(concurrent_replay(), concurrent_replay()) == [
                (initial_id, False),
                (initial_id, False),
            ]

            await add_mastered_pointer(sessions, owner_id)
            async with sessions() as db:
                revised, created = await plan_or_replan_path(
                    db,
                    owner_id=owner_id,
                    target_node_id="single-linked-list",
                    graph=graph,
                    trigger_reason="mastery_changed",
                )
                assert created is True
                assert revised.version == 2
                assert revised.previous_path_id == initial_id
                assert revised.mastery_revision_watermark == 1
                assert "c-pointer" not in [node["node_id"] for node in revised.nodes]
                assert "c-pointer" in revised.reasons[0]["removed_node_ids"]
                revised_id = revised.id

            async with sessions() as db:
                latest = await latest_profile(db, owner_id)
                assert latest is not None
                corrected = apply_manual_correction(
                    snapshot_profile(latest),
                    {"engineering_preference": {"code_first": True}},
                    observed_at="2026-09-25T23:45:00+08:00",
                )
                await persist_profile_version(db, owner_id=owner_id, profile=corrected)
            async with sessions() as db:
                pointer = await db.get(LearningPathCurrent, (owner_id, "single-linked-list"))
                assert pointer is not None and pointer.replan_required is True
                third, created = await plan_or_replan_path(
                    db,
                    owner_id=owner_id,
                    target_node_id="single-linked-list",
                    graph=graph,
                    trigger_reason="profile_changed",
                )
                assert created is True
                assert third.version == 3
                assert third.profile_version == 2
                assert any(node["recommended_resource"] == "code" for node in third.nodes)
                third_id = third.id
        finally:
            await engine.dispose()

        restarted = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(restarted, expire_on_commit=False)
            async with sessions() as db:
                old = await db.get(LearningPathVersion, initial_id)
                assert old is not None and old.version == 1
                assert old.current_node_id == "c-pointer"
                previous = await db.get(LearningPathVersion, revised_id)
                assert previous is not None and previous.version == 2
                current = await current_path_version(
                    db, owner_id=owner_id, target_node_id="single-linked-list"
                )
                assert current is not None and current.id == third_id
                replay, created = await plan_or_replan_path(
                    db,
                    owner_id=owner_id,
                    target_node_id="single-linked-list",
                    graph=graph,
                    trigger_reason="learner_request",
                )
                assert created is False and replay.id == third_id
        finally:
            await restarted.dispose()

    asyncio.run(exercise())
