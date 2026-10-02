"""Versioned independence policy for fixed quizzes; original mastery math is unchanged."""

import unicodedata
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning_state import LearningEvidence
from app.services.catalog_package import content_digest

CATALOG_ASSESSMENT_VERSION = "catalog-first-complete-v1"


def fixed_question_digest(content: dict[str, object]) -> str:
    """Ignore display IDs, ordering and feedback text when identifying the same quiz."""
    def normalized(value: object) -> str:
        assert isinstance(value, str)
        return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    items = content["items"]
    assert isinstance(items, list)
    questions = [{"question": normalized(item["question"]),
                  "answer": normalized(item["answer"])} for item in items]
    return content_digest(sorted(questions, key=lambda q: (q["question"], q["answer"])))


async def fixed_quiz_qualification(
    db: AsyncSession, *, owner_id: UUID, node_id: str, content: dict[str, object],
    answers: list[dict[str, str]],
) -> dict[str, object]:
    """Caller holds the owner/node lock, preventing simultaneous independent attempts."""
    digest = fixed_question_digest(content)
    items = content["items"]
    assert isinstance(items, list)
    provided = {item["question_id"] for item in answers if item["answer"].strip()}
    complete = provided == {item["id"] for item in items}
    prior = await db.scalar(select(LearningEvidence.id).where(
        LearningEvidence.user_id == owner_id, LearningEvidence.knowledge_node_id == node_id,
        LearningEvidence.evidence_type == "quiz_attempt",
        LearningEvidence.payload["catalog_assessment"]["question_set_digest"].astext == digest,
        LearningEvidence.payload["catalog_assessment"]["eligible_for_mastery"].astext == "true",
    ).limit(1))
    eligible = complete and prior is None
    return {"version": CATALOG_ASSESSMENT_VERSION, "question_set_digest": digest,
            "eligible_for_mastery": eligible,
            "reason": "first_complete" if eligible else "repeat" if prior else "incomplete"}


def mastery_eligible(payload: dict[str, object]) -> bool:
    if "catalog_assessment" not in payload:
        return True  # Existing dynamic evidence keeps its original meaning.
    qualification = payload["catalog_assessment"]
    return (isinstance(qualification, dict)
            and qualification.get("version") == CATALOG_ASSESSMENT_VERSION
            and qualification.get("eligible_for_mastery") is True)
