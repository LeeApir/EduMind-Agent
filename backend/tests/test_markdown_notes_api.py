"""Markdown downloads use reviewed owner versions and omit raw evidence."""

import asyncio
import os
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_debate_api import FakeAdapter, events, guest, headers, use_adapter

from app.core.database import create_database_engine
from app.main import app
from app.models.learning import GeneratedResource, LearningScene, LearningUnit
from app.models.learning_state import LearningEvidence

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def seed_notes(owner_id: UUID, foreign_id: UUID, *, reviewed: bool = True) -> UUID:
    async def insert() -> UUID:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                unit = LearningUnit(
                    user_id=owner_id, title="链表 / ../../<script>\n秘密", status="ready",
                    knowledge_point_id="single-linked-list",
                )
                db.add(unit)
                await db.flush()
                old = LearningScene(
                    learning_unit_id=unit.id, scene_key="intro", scene_order=1,
                    scene_type="first_learning", version=1,
                    generation_status="complete", review_status="passed",
                )
                current = LearningScene(
                    learning_unit_id=unit.id, scene_key="intro", scene_order=1,
                    scene_type="first_learning", version=2,
                    generation_status="complete", review_status="passed",
                )
                quiz = LearningScene(
                    learning_unit_id=unit.id, scene_key="quiz", scene_order=2,
                    scene_type="quiz", version=1,
                    generation_status="complete", review_status="passed",
                )
                rejected_scene = LearningScene(
                    learning_unit_id=unit.id, scene_key="hidden", scene_order=3,
                    scene_type="first_learning", version=1,
                    generation_status="complete", review_status="rejected",
                )
                db.add_all([old, current, quiz, rejected_scene])
                await db.flush()
                published_at = datetime(2026, 9, 29, 8, 0, tzinfo=timezone.utc)
                resources = [
                    GeneratedResource(
                        user_id=owner_id, learning_unit_id=unit.id, scene_id=old.id,
                        resource_type="explanation", content={"markdown": "OLD_APPROVED"},
                        version=1, review_status="passed", published_at=published_at,
                    ),
                    GeneratedResource(
                        user_id=owner_id, learning_unit_id=unit.id, scene_id=current.id,
                        resource_type="explanation",
                        content={
                            "markdown": "链表插入先定位。\n\n再改变指针。<script>unsafe</script>"
                            " [危险](javascript:alert(1))"
                        },
                        version=1, review_status="passed" if reviewed else "pending",
                        published_at=published_at if reviewed else None,
                        generation_metadata={"model_id": "model-v2", "content_version": 1},
                    ),
                    GeneratedResource(
                        user_id=owner_id, learning_unit_id=unit.id, scene_id=current.id,
                        resource_type="explanation", content={"markdown": "REJECTED_SECRET"},
                        version=2, review_status="rejected",
                    ),
                    GeneratedResource(
                        user_id=owner_id, learning_unit_id=unit.id, scene_id=rejected_scene.id,
                        resource_type="explanation", content={"markdown": "HIDDEN_SCENE_SECRET"},
                        version=1, review_status="rejected",
                    ),
                    GeneratedResource(
                        user_id=owner_id, learning_unit_id=unit.id, scene_id=quiz.id,
                        resource_type="exercise", content={"items": [
                            {"id": "q1", "question": "链表插入先做什么？",
                             "answer": "ANSWER_KEY_SECRET", "explanation": "先定位"},
                            {"id": "q2", "question": "链表怎么取值？", "answer": "遍历",
                             "explanation": "逐个遍历"},
                        ]},
                        version=1, review_status="passed", published_at=published_at,
                        generation_metadata={"model_id": "quiz-model", "content_version": 1},
                    ),
                ]
                db.add_all(resources)
                await db.flush()
                quiz_resource = resources[-1]
                db.add_all([
                    LearningEvidence(
                        user_id=owner_id, idempotency_key="notes-quiz-owner-001",
                        request_digest="a" * 64, evidence_type="quiz_attempt",
                        knowledge_node_id="single-linked-list", learning_unit_id=unit.id,
                        scene_id=quiz.id, resource_id=quiz_resource.id, resource_version=1,
                        schema_version=1, rule_version="quiz-exact-text-v1",
                        payload={"answers": [{"question_id": "q1", "answer": "RAW_ANSWER_SECRET"}],
                                 "question_results": [
                                     {"question_id": "q1", "correct": False},
                                     {"question_id": "q2", "correct": True},
                                 ]},
                        created_at=published_at,
                    ),
                    LearningEvidence(
                        user_id=foreign_id, idempotency_key="notes-quiz-foreign-001",
                        request_digest="b" * 64, evidence_type="quiz_attempt",
                        knowledge_node_id="single-linked-list", learning_unit_id=unit.id,
                        scene_id=quiz.id, resource_id=quiz_resource.id, resource_version=1,
                        schema_version=1, rule_version="quiz-exact-text-v1",
                        payload={"question_results": [{"question_id": "q2", "correct": False}]},
                    ),
                    LearningEvidence(
                        user_id=owner_id, idempotency_key="notes-quiz-wrong-version-001",
                        request_digest="d" * 64, evidence_type="quiz_attempt",
                        knowledge_node_id="single-linked-list", learning_unit_id=unit.id,
                        scene_id=quiz.id, resource_id=quiz_resource.id, resource_version=2,
                        schema_version=1, rule_version="quiz-exact-text-v1",
                        payload={"question_results": [{"question_id": "q2", "correct": False}]},
                    ),
                ])
                await db.commit()
                return unit.id
        finally:
            await engine.dispose()

    return asyncio.run(insert())


def test_download_uses_current_reviewed_versions_owner_quiz_and_safe_headers() -> None:
    owner, owner_id, csrf = guest()
    foreign, foreign_id, _ = guest()
    unit_id = seed_notes(owner_id, foreign_id)
    path = f"/api/learning-units/{unit_id}/notes.md"
    response = owner.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="learning-notes-{unit_id}.md"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    body = response.content.decode("utf-8")
    assert body.startswith("# 学习笔记\n")
    assert "链表插入先定位" in body
    assert "## 知识点总结（已审核讲解摘录）" in body
    assert "链表插入先做什么？" in body
    assert "链表怎么取值？" not in body
    assert "model-v2" in body and "资源 v1" in body and "2026-09-29T08:00:00+00:00" in body
    assert "练习：场景 quiz v1，资源 v1；模型 quiz-model" in body
    assert "&lt;script&gt;" in body and "<script>" not in body
    assert "\\[危险\\](javascript:alert(1))" in body
    for secret in ("OLD_APPROVED", "REJECTED_SECRET", "HIDDEN_SCENE_SECRET",
                   "RAW_ANSWER_SECRET", "ANSWER_KEY_SECRET", "notes-quiz-owner-001"):
        assert secret not in body
    assert foreign.get(path).status_code == 404
    assert TestClient(app, base_url="https://testserver").get(path).status_code == 401
    missing = "/api/learning-units/00000000-0000-0000-0000-000000000000/notes.md"
    assert owner.get(missing).status_code == 404
    assert owner.post(path, headers=headers(csrf, "notes-post-key-001")).status_code == 405


def test_optional_reviewed_debate_is_included_without_new_provider_call() -> None:
    adapter = FakeAdapter()
    use_adapter(adapter)
    owner, owner_id, csrf = guest()
    foreign, foreign_id, _ = guest()
    unit_id = seed_notes(owner_id, foreign_id)
    base = f"/api/learning-units/{unit_id}/classroom"
    assert owner.post(base, headers=headers(csrf, "notes-create-class-001")).status_code == 201
    streamed = owner.post(f"{base}/debate", json={
        "preset": "array-vs-linked-list", "question": "随机访问怎么选？",
    }, headers=headers(csrf, "notes-debate-key-001", 1))
    assert streamed.status_code == 200
    assert any(name == "debate_ready" for name, _ in events(streamed.text))
    calls = list(adapter.calls)
    body = owner.get(f"/api/learning-units/{unit_id}/notes.md").text
    assert "## 已审核多视角总结" in body
    assert "fake-generation" in body
    assert adapter.calls == calls


def test_pending_new_scene_falls_back_to_last_reviewed_version() -> None:
    owner, owner_id, _ = guest()
    foreign, foreign_id, _ = guest()
    unit_id = seed_notes(owner_id, foreign_id, reviewed=False)
    response = owner.get(f"/api/learning-units/{unit_id}/notes.md")
    assert response.status_code == 200
    assert "OLD_APPROVED" in response.text


def test_latest_corrected_attempt_removes_wrong_question_and_empty_unit_is_hidden() -> None:
    owner, owner_id, _ = guest()
    foreign, foreign_id, _ = guest()
    unit_id = seed_notes(owner_id, foreign_id)

    async def correct_and_add_empty() -> UUID:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                from sqlalchemy import select

                exercise = await db.scalar(select(GeneratedResource).where(
                    GeneratedResource.learning_unit_id == unit_id,
                    GeneratedResource.resource_type == "exercise",
                    GeneratedResource.review_status == "passed",
                ))
                assert exercise is not None
                corrected_resource = GeneratedResource(
                    user_id=owner_id, learning_unit_id=unit_id, scene_id=exercise.scene_id,
                    resource_type="exercise", content=exercise.content, version=2,
                    review_status="passed",
                    published_at=datetime(2026, 9, 29, 8, 30, tzinfo=timezone.utc),
                )
                db.add(corrected_resource)
                await db.flush()
                db.add(LearningEvidence(
                    user_id=owner_id, idempotency_key="notes-quiz-corrected-001",
                    request_digest="c" * 64, evidence_type="quiz_attempt",
                    knowledge_node_id="single-linked-list", learning_unit_id=unit_id,
                    scene_id=exercise.scene_id, resource_id=corrected_resource.id,
                    resource_version=2,
                    schema_version=1, rule_version="quiz-exact-text-v1",
                    payload={"question_results": [{"question_id": "q1", "correct": True}]},
                    created_at=datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc),
                ))
                empty = LearningUnit(user_id=owner_id, title="空单元", status="ready")
                db.add(empty)
                await db.commit()
                return empty.id
        finally:
            await engine.dispose()

    empty_id = asyncio.run(correct_and_add_empty())
    body = owner.get(f"/api/learning-units/{unit_id}/notes.md").text
    assert "链表插入先做什么？" not in body
    assert "暂无错题记录。" in body
    assert owner.get(f"/api/learning-units/{empty_id}/notes.md").status_code == 404
