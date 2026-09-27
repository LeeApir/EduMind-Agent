"""Versioned, deterministic scoring of owner-visible published exercises."""

import unicodedata
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.learning_resource_schema import RESOURCE_PROMPT_VERSION
from app.services.owned_learning import published_resource

QUIZ_SCHEMA_VERSION: Final = 1
QUIZ_SCORING_RULE_VERSION: Final = "quiz-exact-text-v1"


class QuizScoringError(ValueError):
    """Reject an invalid resource or submission without echoing answer keys."""

    def __init__(self) -> None:
        super().__init__("Quiz submission does not match a published exercise.")


@dataclass(frozen=True, slots=True)
class QuizQuestion:
    question_id: str
    prompt: str
    answer_key: str
    explanation: str


@dataclass(frozen=True, slots=True)
class QuizQuestionResult:
    question_id: str
    correct: bool
    explanation: str
    error_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QuizScore:
    resource_id: UUID
    resource_version: int
    schema_version: int
    rule_version: str
    correct_count: int
    question_count: int
    score: float
    question_results: tuple[QuizQuestionResult, ...]


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QuizScoringError
    return value.strip()


def _questions(content: object) -> tuple[QuizQuestion, ...]:
    if not isinstance(content, dict) or set(content) != {"items"}:
        raise QuizScoringError
    items = content["items"]
    if not isinstance(items, list) or not 2 <= len(items) <= 4:
        raise QuizScoringError
    questions: list[QuizQuestion] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "question", "answer", "explanation"}:
            raise QuizScoringError
        question_id = _text(item["id"])
        if len(question_id) > 128 or question_id in seen:
            raise QuizScoringError
        seen.add(question_id)
        questions.append(
            QuizQuestion(
                question_id=question_id,
                prompt=_text(item["question"]),
                answer_key=_text(item["answer"]),
                explanation=_text(item["explanation"]),
            )
        )
    return tuple(questions)


def _submitted_answers(answers: object, questions: tuple[QuizQuestion, ...]) -> dict[str, str]:
    if not isinstance(answers, list) or not 1 <= len(answers) <= 10:
        raise QuizScoringError
    allowed_ids = {question.question_id for question in questions}
    submitted: dict[str, str] = {}
    for item in answers:
        if not isinstance(item, dict) or set(item) != {"question_id", "answer"}:
            raise QuizScoringError
        question_id = _text(item["question_id"])
        answer = item["answer"]
        if (
            question_id not in allowed_ids
            or question_id in submitted
            or not isinstance(answer, str)
            or len(answer) > 500
        ):
            raise QuizScoringError
        submitted[question_id] = answer
    return submitted


def _canonical_answer(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def score_exercise_content(
    *, resource_id: UUID, resource_version: int, content: object, answers: object
) -> QuizScore:
    """Score all published v1 questions; omitted answers count as incorrect."""
    questions = _questions(content)
    submitted = _submitted_answers(answers, questions)
    results: list[QuizQuestionResult] = []
    for question in questions:
        answer = submitted.get(question.question_id, "")
        correct = bool(answer.strip()) and _canonical_answer(answer) == _canonical_answer(
            question.answer_key
        )
        if correct:
            patterns: tuple[str, ...] = ()
        elif not answer.strip():
            patterns = ("blank_answer",)
        else:
            patterns = ("answer_mismatch",)
        results.append(
            QuizQuestionResult(
                question_id=question.question_id,
                correct=correct,
                explanation=question.explanation,
                error_patterns=patterns,
            )
        )
    correct_count = sum(result.correct for result in results)
    return QuizScore(
        resource_id=resource_id,
        resource_version=resource_version,
        schema_version=QUIZ_SCHEMA_VERSION,
        rule_version=QUIZ_SCORING_RULE_VERSION,
        correct_count=correct_count,
        question_count=len(questions),
        score=correct_count / len(questions),
        question_results=tuple(results),
    )


async def score_published_exercise(
    db: AsyncSession,
    *,
    owner_id: UUID,
    resource_id: UUID,
    resource_version: int,
    answers: object,
) -> QuizScore:
    """Never use client-provided answer keys, scores, or unreviewed resources."""
    resource = await published_resource(db, owner_id, resource_id)
    if (
        resource is None
        or resource.resource_type != "exercise"
        or resource.version != resource_version
        or not isinstance(resource.generation_metadata, dict)
        or resource.generation_metadata.get("prompt_version") != RESOURCE_PROMPT_VERSION
    ):
        raise QuizScoringError
    return score_exercise_content(
        resource_id=resource.id,
        resource_version=resource.version,
        content=resource.content,
        answers=answers,
    )
