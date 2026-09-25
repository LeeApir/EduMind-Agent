"""Quiz API protects published answer keys and appends one owner-scoped fact."""

import asyncio
import os
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.learning_resource_schema import RESOURCE_PROMPT_VERSION
from app.core.database import create_database_engine
from app.main import app
from app.models.learning import GeneratedResource, LearningScene, LearningUnit
from app.models.learning_state import LearningEvidence
from app.services.learning_operations import IdempotencyConflict
from app.services.quiz_submissions import submit_quiz_attempt

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def quiz_content() -> dict[str, object]:
    return {
        "items": [
            {
                "id": "q1",
                "question": "头插法复杂度？",
                "answer": "O(1)",
                "explanation": "常数次指针修改。",
            },
            {
                "id": "q2",
                "question": "后继成员？",
                "answer": "next",
                "explanation": "next 指向后继。",
            },
        ]
    }


def seed_resources(owner_id: UUID) -> tuple[UUID, UUID]:
    assert TEST_DATABASE_URL is not None

    async def insert() -> tuple[UUID, UUID]:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                unit = LearningUnit(
                    user_id=owner_id,
                    knowledge_point_id="linked-list",
                    title="链表",
                    status="ready",
                )
                db.add(unit)
                await db.flush()
                scene = LearningScene(
                    learning_unit_id=unit.id,
                    scene_key="quiz",
                    scene_order=1,
                    scene_type="quiz",
                    generation_status="complete",
                    review_status="passed",
                )
                db.add(scene)
                await db.flush()
                published = GeneratedResource(
                    user_id=owner_id,
                    learning_unit_id=unit.id,
                    scene_id=scene.id,
                    resource_type="exercise",
                    content=quiz_content(),
                    review_status="passed",
                    published_at=datetime.now(timezone.utc),
                    generation_metadata={"prompt_version": RESOURCE_PROMPT_VERSION},
                    version=1,
                )
                draft = GeneratedResource(
                    user_id=owner_id,
                    learning_unit_id=unit.id,
                    scene_id=scene.id,
                    resource_type="exercise",
                    content=quiz_content(),
                    review_status="pending",
                    generation_metadata={"prompt_version": RESOURCE_PROMPT_VERSION},
                    version=2,
                )
                db.add_all([published, draft])
                await db.commit()
                return published.id, draft.id
        finally:
            await engine.dispose()

    return asyncio.run(insert())


def make_guest() -> tuple[TestClient, UUID, str]:
    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/auth/guest")
    assert created.status_code == 201
    return client, UUID(created.json()["user"]["id"]), created.json()["csrf_token"]


def submission(resource_id: UUID, answers: list[dict[str, object]]) -> dict[str, object]:
    return {"resource_id": str(resource_id), "resource_version": 1, "answers": answers}


def headers(csrf: str, key: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf, "Origin": "https://testserver", "Idempotency-Key": key}


def test_submission_scores_server_answer_key_and_replay_does_not_append_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    client, owner_id, csrf = make_guest()
    resource_id, _ = seed_resources(owner_id)
    request = submission(
        resource_id,
        [{"question_id": "q2", "answer": "wrong"}, {"question_id": "q1", "answer": "o(1)"}],
    )
    key = "quiz-submit-key-0001"
    first = client.post("/api/quiz-submissions", json=request, headers=headers(csrf, key))
    assert first.status_code == 200
    body = first.json()
    assert body["resource_id"] == str(resource_id)
    assert body["score"] == 0.5
    assert body["correct_count"] == 1
    assert body["scoring_rule_version"] == "quiz-exact-text-v1"
    assert [result["correct"] for result in body["question_results"]] == [True, False]
    assert body["question_results"][1]["error_patterns"] == ["answer_mismatch"]
    assert body["mastery_changes"] == []
    assert body["path_replan_required"] is False

    request["answers"] = list(reversed(request["answers"]))
    replay = client.post("/api/quiz-submissions", json=request, headers=headers(csrf, key))
    assert replay.status_code == 200
    assert replay.json() == body

    async def count_and_read() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine)
            async with sessions() as db:
                count = await db.scalar(
                    select(func.count())
                    .select_from(LearningEvidence)
                    .where(LearningEvidence.user_id == owner_id)
                )
                assert count == 1
                record = await db.get(LearningEvidence, UUID(body["evidence_id"]))
                assert record is not None
                assert record.payload["score"] == 0.5
                assert record.payload["answers"] == [
                    {"question_id": "q1", "answer": "o(1)"},
                    {"question_id": "q2", "answer": "wrong"},
                ]
                assert "answer_key" not in str(record.payload)
        finally:
            await engine.dispose()

    asyncio.run(count_and_read())
    conflicting = client.post(
        "/api/quiz-submissions",
        json=submission(resource_id, [{"question_id": "q1", "answer": "wrong"}]),
        headers=headers(csrf, key),
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_foreign_draft_wrong_version_and_tampered_answers_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    owner, owner_id, csrf = make_guest()
    foreign, _, foreign_csrf = make_guest()
    resource_id, draft_id = seed_resources(owner_id)
    answer = [{"question_id": "q1", "answer": "O(1)"}]
    key = "quiz-submit-key-0002"

    foreign_result = foreign.post(
        "/api/quiz-submissions",
        json=submission(resource_id, answer),
        headers=headers(foreign_csrf, key),
    )
    assert foreign_result.status_code == 404
    draft_result = owner.post(
        "/api/quiz-submissions",
        json={**submission(draft_id, answer), "resource_version": 2},
        headers=headers(csrf, key),
    )
    assert draft_result.status_code == 404
    wrong_version = owner.post(
        "/api/quiz-submissions",
        json={**submission(resource_id, answer), "resource_version": 2},
        headers=headers(csrf, key),
    )
    assert wrong_version.status_code == 422
    assert wrong_version.json()["code"] == "QUIZ_SUBMISSION_INVALID"

    for invalid_answers in [
        [{"question_id": "unknown", "answer": "O(1)"}],
        [answer[0], answer[0]],
        [{"question_id": "q1", "answer": "O(1)", "correct": True}],
        [{"question_id": "q1", "answer": "O(1)", "answer_key": "O(1)"}],
    ]:
        invalid = owner.post(
            "/api/quiz-submissions",
            json=submission(resource_id, invalid_answers),
            headers=headers(csrf, key),
        )
        assert invalid.status_code == 422


def test_quiz_submission_requires_csrf_and_same_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    client, owner_id, csrf = make_guest()
    resource_id, _ = seed_resources(owner_id)
    body = submission(resource_id, [{"question_id": "q1", "answer": "O(1)"}])
    key = "quiz-submit-key-0003"
    missing = client.post("/api/quiz-submissions", json=body, headers={"Idempotency-Key": key})
    assert missing.status_code == 403
    foreign = client.post(
        "/api/quiz-submissions",
        json=body,
        headers={"Idempotency-Key": key, "X-CSRF-Token": csrf, "Origin": "https://evil.example"},
    )
    assert foreign.status_code == 403


@pytest.mark.parametrize("second_answer", ["O(1)", "wrong"])
def test_concurrent_same_key_replays_or_conflicts(
    second_answer: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    client, owner_id, _ = make_guest()
    resource_id, _ = seed_resources(owner_id)

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            barrier = asyncio.Barrier(2)

            class LookupBarrierSession(AsyncSession):
                waited = False

                async def scalar(self, statement: object, *args: object, **kwargs: object):
                    result = await super().scalar(statement, *args, **kwargs)
                    if not self.waited:
                        self.waited = True
                        await barrier.wait()
                    return result

            racing = async_sessionmaker(engine, class_=LookupBarrierSession, expire_on_commit=False)

            async def submit(answer: str):
                async with racing() as db:
                    return await submit_quiz_attempt(
                        db,
                        owner_id=owner_id,
                        idempotency_key="quiz-concurrent-key-0001",
                        resource_id=resource_id,
                        resource_version=1,
                        answers=[{"question_id": "q1", "answer": answer}],
                    )

            results = await asyncio.wait_for(
                asyncio.gather(submit("O(1)"), submit(second_answer), return_exceptions=True),
                timeout=10,
            )
            if second_answer == "O(1)":
                assert all(isinstance(result, tuple) for result in results)
                assert results[0][0].id == results[1][0].id
                assert sorted(result[1] for result in results) == [False, True]
            else:
                assert sum(isinstance(result, IdempotencyConflict) for result in results) == 1
                assert sum(isinstance(result, tuple) for result in results) == 1
            async with sessions() as db:
                count = await db.scalar(
                    select(func.count())
                    .select_from(LearningEvidence)
                    .where(LearningEvidence.user_id == owner_id)
                )
                assert count == 1
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    client.close()
