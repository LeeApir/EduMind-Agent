"""The scorer trusts only owner-visible, reviewed exercise versions."""

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.learning_resource_schema import RESOURCE_PROMPT_VERSION
from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import GeneratedResource, LearningScene, LearningUnit
from app.services.quiz_scoring import (
    QUIZ_SCHEMA_VERSION,
    QUIZ_SCORING_RULE_VERSION,
    QuizScoringError,
    score_exercise_content,
    score_published_exercise,
)

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")


def content() -> dict[str, object]:
    return {
        "items": [
            {
                "id": "q1",
                "question": "头插法复杂度？",
                "answer": "O(1)",
                "explanation": "只更新常数个指针。",
            },
            {
                "id": "q2",
                "question": "存放后继的成员？",
                "answer": "next pointer",
                "explanation": "next 保存后继地址。",
            },
            {
                "id": "q3",
                "question": "空链表头指向什么？",
                "answer": "NULL",
                "explanation": "头指针为空。",
            },
        ]
    }


def score(value: object, *, quiz_content: object | None = None):
    return score_exercise_content(
        resource_id=uuid4(),
        resource_version=2,
        content=content() if quiz_content is None else quiz_content,
        answers=value,
    )


def test_exact_text_rule_is_deterministic_and_versioned() -> None:
    answers = [
        {"question_id": "q1", "answer": "ｏ（１）"},
        {"question_id": "q2", "answer": " Next   POINTER "},
        {"question_id": "q3", "answer": "wrong"},
    ]
    first = score(answers)
    second = score(answers)
    assert first.schema_version == QUIZ_SCHEMA_VERSION
    assert first.rule_version == QUIZ_SCORING_RULE_VERSION
    assert first.score == second.score == 2 / 3
    assert first.correct_count == 2
    assert [result.correct for result in first.question_results] == [True, True, False]
    assert first.question_results[-1].error_patterns == ("answer_mismatch",)
    assert first.question_results[0].explanation == "只更新常数个指针。"


def test_omitted_questions_count_as_wrong_without_partial_score_inflation() -> None:
    result = score([{"question_id": "q1", "answer": "O(1)"}])
    assert result.score == 1 / 3
    assert [item.error_patterns for item in result.question_results] == [
        (),
        ("blank_answer",),
        ("blank_answer",),
    ]


@pytest.mark.parametrize(
    "answers",
    [
        [],
        [{"question_id": "q0", "answer": "O(1)"}],
        [{"question_id": "q1", "answer": "O(1)", "correct": True}],
        [{"question_id": "q1", "answer": "O(1)", "answer_key": "O(1)"}],
        [{"question_id": "q1", "answer": 1}],
        [{"question_id": "q1", "answer": "O(1)"}] * 2,
    ],
)
def test_rejects_unknown_duplicate_and_client_supplied_grading_data(answers: object) -> None:
    with pytest.raises(QuizScoringError):
        score(answers)


def test_rejects_duplicate_ids_or_answer_key_changes_in_resource_content() -> None:
    invalid = content()
    items = invalid["items"]
    assert isinstance(items, list)
    items[1]["id"] = "q1"
    with pytest.raises(QuizScoringError):
        score([{"question_id": "q1", "answer": "O(1)"}], quiz_content=invalid)
    items[1]["id"] = "q2"
    items[0]["injected"] = "wrong answer"
    with pytest.raises(QuizScoringError):
        score([{"question_id": "q1", "answer": "O(1)"}], quiz_content=invalid)


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")
def test_only_owner_visible_published_exercise_version_can_be_scored() -> None:
    assert TEST_DATABASE_URL is not None

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                owner = User(is_guest=True)
                other = User(is_guest=True)
                db.add_all([owner, other])
                await db.flush()
                unit = LearningUnit(user_id=owner.id, title="链表", status="ready")
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
                    user_id=owner.id,
                    learning_unit_id=unit.id,
                    scene_id=scene.id,
                    resource_type="exercise",
                    content=content(),
                    review_status="passed",
                    published_at=datetime.now(timezone.utc),
                    generation_metadata={"prompt_version": RESOURCE_PROMPT_VERSION},
                    version=2,
                )
                draft = GeneratedResource(
                    user_id=owner.id,
                    learning_unit_id=unit.id,
                    scene_id=scene.id,
                    resource_type="exercise",
                    content=content(),
                    review_status="pending",
                    generation_metadata={"prompt_version": RESOURCE_PROMPT_VERSION},
                    version=3,
                )
                db.add_all([published, draft])
                await db.commit()

                answers = [{"question_id": "q1", "answer": "O(1)"}]
                result = await score_published_exercise(
                    db,
                    owner_id=owner.id,
                    resource_id=published.id,
                    resource_version=2,
                    answers=answers,
                )
                assert result.score == 1 / 3
                for owner_id, resource_id, version in [
                    (other.id, published.id, 2),
                    (owner.id, published.id, 1),
                    (owner.id, draft.id, 3),
                ]:
                    with pytest.raises(QuizScoringError):
                        await score_published_exercise(
                            db,
                            owner_id=owner_id,
                            resource_id=resource_id,
                            resource_version=version,
                            answers=answers,
                        )
        finally:
            await engine.dispose()

    asyncio.run(exercise())
