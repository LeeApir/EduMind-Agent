"""Behavior summaries update immutable profiles without coupling evidence to Provider I/O."""

import asyncio
import os
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.profile_schema import merge_explicit_profile_values
from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import StudentProfile
from app.models.learning_state import LearningEvidence
from app.services.profile_behavior_updates import (
    learning_evidence_summary,
    update_profile_from_summary,
)
from app.services.profile_updates import persist_profile_version
from app.services.provider_gateway import ProviderError, ProviderErrorCode, StructuredResult

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


class StubGateway:
    def __init__(self, result: StructuredResult | ProviderError) -> None:
        self.result = result
        self.requests: list[object] = []

    async def generate_structured(
        self, request: object, *, retry_safe: bool = False
    ) -> StructuredResult:
        self.requests.append(request)
        if isinstance(self.result, ProviderError):
            raise self.result
        return self.result


def initial_profile() -> dict[str, object]:
    return merge_explicit_profile_values(
        "想理解链表",
        {"learning_goals": {"current_topic": "链表"}},
        {
            "learning_goals": [
                {
                    "source": "initial_query",
                    "confidence": 0.9,
                    "observed_at": "2026-09-25T12:00:00+00:00",
                    "profile_version": 1,
                }
            ]
        },
    )


async def seed(sessions: async_sessionmaker[AsyncSession], *, answer: str) -> tuple[UUID, UUID]:
    async with sessions() as db:
        owner = User(is_guest=True)
        db.add(owner)
        await db.flush()
        await persist_profile_version(db, owner_id=owner.id, profile=initial_profile())
        evidence = LearningEvidence(
            user_id=owner.id,
            idempotency_key=f"profile-behavior-{owner.id}",
            request_digest="a" * 64,
            evidence_type="quiz_attempt",
            knowledge_node_id="linked-list",
            schema_version=1,
            rule_version="quiz-scoring-v1",
            payload={
                "answers": [{"question_id": "q1", "answer": answer}],
                "question_results": [{"question_id": "q1", "error_patterns": ["pointer-link"]}],
                "score": 0.0,
            },
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(evidence)
        await db.commit()
        return owner.id, evidence.id


def test_quiz_behavior_creates_version_without_leaking_answers_or_unknown_fields() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            secret_answer = "raw answer never sent to provider"
            owner_id, evidence_id = await seed(sessions, answer=secret_answer)
            gateway = StubGateway(
                StructuredResult(
                    value={"updates": {"error_preferences": [{"topic": "pointer-link"}]}},
                    model_id="test",
                )
            )
            async with sessions() as db:
                evidence = await db.get(LearningEvidence, evidence_id)
                assert evidence is not None
                summary = learning_evidence_summary(evidence)
                assert summary == {
                    "event_type": "quiz_attempt",
                    "knowledge_node_id": "linked-list",
                    "score": 0.0,
                    "error_patterns": ["pointer-link"],
                }
                observed_at = evidence.created_at
            status = await update_profile_from_summary(
                sessions,
                owner_id=owner_id,
                evidence_id=evidence_id,
                observed_at=observed_at,
                summary=summary,
                gateway_factory=lambda: gateway,
            )
            assert status == "updated"
            assert secret_answer not in str(gateway.requests)
            async with sessions() as db:
                versions = (
                    await db.scalars(
                        select(StudentProfile)
                        .where(StudentProfile.user_id == owner_id)
                        .order_by(StudentProfile.version)
                    )
                ).all()
                assert [version.version for version in versions] == [1, 2]
                assert versions[0].error_preferences is None
                assert versions[1].error_preferences == [{"topic": "pointer-link"}]
                assert versions[1].professional_background is None
                assert versions[1].knowledge_base is None
                assert versions[1].cognitive_style is None
                assert versions[1].previous_profile_id == versions[0].id
                version_evidence = versions[1].evidence
                assert isinstance(version_evidence, dict)
                preference_evidence = version_evidence["error_preferences"]
                assert isinstance(preference_evidence, list)
                assert preference_evidence[0]["source"] == "learning_behavior"
            replay = await update_profile_from_summary(
                sessions,
                owner_id=owner_id,
                evidence_id=evidence_id,
                observed_at=observed_at,
                summary=summary,
                gateway_factory=lambda: pytest.fail("replay called provider"),
            )
            assert replay == "updated"
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_provider_failure_keeps_committed_evidence_and_original_profile() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            owner_id, evidence_id = await seed(sessions, answer="sensitive answer")
            async with sessions() as db:
                evidence = await db.get(LearningEvidence, evidence_id)
                assert evidence is not None
                summary = learning_evidence_summary(evidence)
                observed_at = evidence.created_at
            gateway = StubGateway(ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE))
            status = await update_profile_from_summary(
                sessions,
                owner_id=owner_id,
                evidence_id=evidence_id,
                observed_at=observed_at,
                summary=summary,
                gateway_factory=lambda: gateway,
            )
            assert status == "provider_failed"
            async with sessions() as db:
                assert await db.get(LearningEvidence, evidence_id) is not None
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(StudentProfile)
                        .where(StudentProfile.user_id == owner_id)
                    )
                    == 1
                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())
