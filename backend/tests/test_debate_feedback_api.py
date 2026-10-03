"""Explicit perspective feedback is owner-scoped, idempotent, and style-only."""

import asyncio
import json
import os
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_debate_api import FakeAdapter, events, guest, headers, seed_unit, use_adapter

from app.agents.classroom_context import build_classroom_context
from app.agents.classroom_turn_schema import TURN_PROMPT_VERSION
from app.agents.profile_schema import empty_transient_profile
from app.agents.tutor_agent import TutorAgent
from app.core.database import create_database_engine
from app.models.learning_state import LearningEvidence, NodeMasteryRevision
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.owned_learning import latest_profile
from app.services.profile_updates import persist_profile_version, snapshot_profile
from app.services.provider_gateway import StructuredResult

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def prepare_profile(owner_id: UUID) -> None:
    async def insert() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine)
            async with sessions() as db:
                await persist_profile_version(
                    db, owner_id=owner_id, profile=empty_transient_profile("想理解数组与链表"),
                )
        finally:
            await engine.dispose()
    asyncio.run(insert())


def published_debate(*, with_profile: bool = True) -> tuple[object, UUID, UUID, str, str]:
    use_adapter(FakeAdapter())
    client, owner_id, csrf = guest()
    unit_id = seed_unit(owner_id)
    if with_profile:
        prepare_profile(owner_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    assert client.post(base, headers=headers(csrf, "feedback-create-01")).status_code == 201
    started = client.post(f"{base}/debate", json={
        "preset": "array-vs-linked-list", "question": "随机访问怎么选？",
    }, headers=headers(csrf, "feedback-debate-01", 1))
    assert started.status_code == 200
    result_id = next(data["result_id"] for name, data in events(started.text)
                     if name == "debate_ready")
    return client, owner_id, unit_id, csrf, result_id


def feedback_path(unit_id: UUID, result_id: str) -> str:
    return f"/api/learning-units/{unit_id}/classroom/debate/{result_id}/feedback"


def test_explicit_feedback_updates_profile_once_without_mastery_or_fact_changes() -> None:
    client, owner_id, unit_id, csrf, result_id = published_debate()
    path = feedback_path(unit_id, result_id)
    payload = {"perspective": "performance", "feedback": "helpful"}
    first = client.post(path, json=payload, headers=headers(csrf, "feedback-helpful-01"))
    assert first.status_code == 202
    assert first.json()["update_status"] == "updated"
    assert first.json()["profile_version"] == 2
    replay = client.post(path, json=payload, headers=headers(csrf, "feedback-helpful-01"))
    alternate_key = client.post(path, json=payload, headers=headers(csrf, "feedback-helpful-02"))
    assert replay.json() == first.json() == alternate_key.json()
    conflict = client.post(path, json={"perspective": "engineering", "feedback": "helpful"},
                           headers=headers(csrf, "feedback-helpful-01"))
    assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    invalid = client.post(path, json={"perspective": "hidden", "feedback": "helpful"},
                          headers=headers(csrf, "feedback-invalid-01"))
    assert invalid.status_code == 422

    async def inspect() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine)
            async with sessions() as db:
                profile = await latest_profile(db, owner_id)
                assert profile is not None and profile.version == 2
                assert profile.cognitive_style == {"preference_persona": "performance"}
                records = (profile.evidence or {})["cognitive_style"]
                assert records[-1]["source"] == "explicit_feedback"
                assert records[-1]["confidence"] == 0.9
                assert records[-1]["profile_version"] == 2
                facts = list((await db.scalars(select(LearningEvidence).where(
                    LearningEvidence.user_id == owner_id,
                    LearningEvidence.rule_version == "debate-perspective-feedback-v1",
                ))).all())
                assert len(facts) == 1
                assert facts[0].payload["debate_result_id"] == result_id
                assert facts[0].payload["debate_result_version"] == 1
                assert await db.scalar(select(func.count()).select_from(NodeMasteryRevision).where(
                    NodeMasteryRevision.user_id == owner_id,
                )) == 0
                context = build_classroom_context(
                    default_knowledge_graph_repository(), node_id="single-linked-list",
                    goal="继续解释", profile=snapshot_profile(profile),
                )
                assert context.payload()["known_profile"] == {"preference_persona": "performance"}
                assert "debate_result_id" not in context.serialized

                class CapturingGateway:
                    def __init__(self) -> None:
                        self.request = None

                    async def generate_structured(self, request, *, retry_safe=False):
                        self.request = request
                        return StructuredResult(value={
                            "turn_version": TURN_PROMPT_VERSION,
                            "utterances": [{"role": "tutor", "text": "按随机访问性能分析。"}],
                        }, model_id="test")

                gateway = CapturingGateway()
                next_turn = await TutorAgent(gateway).orchestrate(
                    mode="focus", enabled_roles=[], context=context,
                )
                assert next_turn.ok
                assert gateway.request is not None
                assert json.loads(gateway.request.prompt.messages[1].content)[
                    "known_profile"
                ] == {"preference_persona": "performance"}
                assert "绝不能改变算法事实" in gateway.request.prompt.messages[0].content
        finally:
            await engine.dispose()
    asyncio.run(inspect())


def test_manual_correction_wins_later_feedback_and_foreign_result_is_hidden() -> None:
    client, owner_id, unit_id, csrf, result_id = published_debate()
    path = feedback_path(unit_id, result_id)
    first = client.post(path, json={"perspective": "performance", "feedback": "helpful"},
                        headers=headers(csrf, "feedback-manual-01"))
    assert first.status_code == 202
    corrected = client.patch("/api/profile/me", json={
        "cognitive_style": {"preference_persona": "academic"},
    }, headers={**headers(csrf, "feedback-correct-01"), "If-Match-Profile-Version": "2"})
    assert corrected.status_code == 200
    assert corrected.json()["version"] == 3
    later = client.post(path, json={"perspective": "engineering", "feedback": "helpful"},
                        headers=headers(csrf, "feedback-manual-02"))
    assert later.status_code == 202
    assert later.json()["update_status"] == "unchanged"
    assert later.json()["profile_version"] == 4
    profile = client.get("/api/profile/me").json()
    assert profile["cognitive_style"]["preference_persona"] == "academic"
    assert profile["evidence"]["cognitive_style"][-1]["source"] == "explicit_feedback"
    foreign, _, foreign_csrf = guest()
    missing = foreign.post(path, json={"perspective": "academic", "feedback": "helpful"},
                           headers=headers(foreign_csrf, "feedback-foreign-01"))
    assert missing.status_code == 404
    no_csrf = client.post(path, json={"perspective": "academic", "feedback": "helpful"},
                          headers={"Idempotency-Key": "feedback-no-csrf-1"})
    assert no_csrf.status_code == 403


def test_evidence_waits_for_profile_and_same_request_replay_completes_merge() -> None:
    client, owner_id, unit_id, csrf, result_id = published_debate(with_profile=False)
    path = feedback_path(unit_id, result_id)
    payload = {"perspective": "academic", "feedback": "helpful"}
    pending = client.post(path, json=payload, headers=headers(csrf, "feedback-pending-01"))
    assert pending.status_code == 202
    assert pending.json()["update_status"] == "pending"
    evidence_id = pending.json()["evidence_id"]
    prepare_profile(owner_id)
    replay = client.post(path, json=payload, headers=headers(csrf, "feedback-pending-01"))
    assert replay.status_code == 202
    assert replay.json() == {
        "evidence_id": evidence_id, "profile_version": 2, "update_status": "updated",
    }
