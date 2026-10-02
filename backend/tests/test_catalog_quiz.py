"""Fixed quiz receipts remain useful without manufacturing independent mastery facts."""

import asyncio
import os
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from catalog_fixtures import approval_fixture, package_fixture
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import GeneratedResource
from app.models.learning_state import LearningEvidence, NodeMasteryCurrent, NodeMasteryRevision
from app.services.catalog_assessment import fixed_question_digest
from app.services.catalog_package import validate_package
from app.services.catalog_publication import publish_catalog, revoke_catalog
from app.services.catalog_sessions import create_catalog_session
from app.services.learning_operations import IdempotencyConflict
from app.services.mastery_updates import apply_mastery_evidence
from app.services.quiz_scoring import score_published_exercise
from app.services.quiz_submissions import (
    QuizResourceNotFound,
    latest_quiz_attempt,
    quiz_receipt,
    submit_quiz_attempt,
)


def test_semantic_quiz_identity_ignores_display_changes():
    content = package_fixture().nodes["array"]["exercise"]
    changed = deepcopy(content)
    for item in changed["items"]:
        item["id"] += "-new"
        item["explanation"] = "New feedback"
        item["question"] = "  " + item["question"].upper() + "  "
    changed["items"].reverse()
    assert fixed_question_digest(changed) == fixed_question_digest(content)
    changed["items"][0]["answer"] = "different"
    assert fixed_question_digest(changed) != fixed_question_digest(content)


@pytest.mark.skipif(not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="isolated DB required")
def test_real_receipts_partial_repeat_reopen_reduction_and_revocation(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")

    async def run():
        engine = create_database_engine(os.environ["EDUMIND_TEST_DATABASE_URL"])
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                package = package_fixture()
                package.manifest["package_id"] = "quiz-" + uuid4().hex
                package = validate_package(package.payload())
                release = await publish_catalog(db, package, approval=approval_fixture(package),
                                                trusted_digest=package.digest)
                owner, other = User(is_guest=True), User(is_guest=True)
                db.add_all([owner, other])
                await db.commit()
                owner_id, other_id, release_id = owner.id, other.id, release.id

                async def enroll(who):
                    receipt, _ = await create_catalog_session(db, owner_id=who,
                        release_id=release_id, node_id="array", idempotency_key=uuid4().hex)
                    return await db.scalar(select(GeneratedResource).where(
                        GeneratedResource.learning_unit_id == UUID(receipt["learning_unit_id"]),
                        GeneratedResource.resource_type == "exercise"))
                resource = await enroll(owner_id)
                answers = [{"question_id": item["id"], "answer": item["answer"]}
                           for item in package.nodes["array"]["exercise"]["items"]]

                async def submit(res, response, key=None):
                    return await submit_quiz_attempt(db, owner_id=owner_id,
                        resource_id=res.id, resource_version=1, answers=response,
                        idempotency_key=key or uuid4().hex)
                partial, _ = await submit(resource, answers[:1])
                assert partial.payload["catalog_assessment"]["reason"] == "incomplete"
                assert partial.payload["mastery_changes"] == []
                assert await db.get(NodeMasteryCurrent, (owner_id, "array")) is None
                key = uuid4().hex
                first, created = await submit(resource, answers, key)
                first_receipt = quiz_receipt(first)
                assert created and first_receipt["score"] == 1
                assert first_receipt["catalog_assessment"]["reason"] == "first_complete"
                current = await db.get(NodeMasteryCurrent, (owner_id, "array"))
                assert current.score == 0.55 and current.status == "learning"
                replay, created = await submit(resource, list(reversed(answers)), key)
                assert not created and quiz_receipt(replay) == first_receipt
                with pytest.raises(IdempotencyConflict):
                    await submit(resource, answers[:1], key)
                wrong = [{**item, "answer": "wrong"} for item in answers]
                repeated, _ = await submit(resource, wrong)
                assert repeated.payload["score"] == 0
                assert repeated.payload["catalog_assessment"]["reason"] == "repeat"
                assert repeated.payload["mastery_changes"] == []
                assert repeated.payload["path_replan_required"] is False
                assert all(not q["correct"] for q in repeated.payload["question_results"])
                reopened = await enroll(owner_id)
                reopened_attempt, _ = await submit(reopened, answers)
                assert reopened_attempt.payload["catalog_assessment"]["reason"] == "repeat"
                # Rebuilding on a later independent event must also exclude every practice record.
                feedback = LearningEvidence(user_id=owner_id, idempotency_key=uuid4().hex,
                    request_digest="a" * 64, evidence_type="explicit_feedback",
                    knowledge_node_id="array", schema_version=1, rule_version="test",
                    payload={"action": "liked_explanation"})
                db.add(feedback)
                await apply_mastery_evidence(db, feedback)
                await db.commit()
                await db.refresh(current)
                assert current.score == 0.55 and current.revision == 1
                assert await db.scalar(select(func.count()).select_from(NodeMasteryRevision).where(
                    NodeMasteryRevision.user_id == owner_id)) == 1
                latest = await latest_quiz_attempt(db, owner_id=owner_id,
                    resource_id=resource.id, resource_version=1)
                assert latest.id == repeated.id
                with pytest.raises(QuizResourceNotFound):
                    await submit_quiz_attempt(db, owner_id=other_id, resource_id=resource.id,
                        resource_version=1, answers=answers, idempotency_key=uuid4().hex)
                other_resource = await enroll(other_id)
                other_resource_id = other_resource.id
                await db.commit()

            async def race():
                async with sessions() as db:
                    record, _ = await submit_quiz_attempt(db, owner_id=other_id,
                        resource_id=other_resource_id, resource_version=1,
                        answers=answers, idempotency_key=uuid4().hex)
                    return record.payload["catalog_assessment"]["eligible_for_mastery"]
            assert sorted(await asyncio.gather(race(), race())) == [False, True]
            async with sessions() as db:
                current = await db.get(NodeMasteryCurrent, (other_id, "array"))
                assert current.score == 0.55 and current.revision == 1
                await revoke_catalog(db, release_id)
                await db.commit()
                with pytest.raises(QuizResourceNotFound):
                    await latest_quiz_attempt(db, owner_id=owner_id,
                        resource_id=resource.id, resource_version=1)
                with pytest.raises(QuizResourceNotFound):
                    await submit_quiz_attempt(db, owner_id=owner_id,
                        resource_id=resource.id, resource_version=1, answers=answers,
                        idempotency_key=key)
                with pytest.raises(ValueError):
                    await score_published_exercise(db, owner_id=owner_id,
                        resource_id=resource.id, resource_version=1, answers=answers)
        finally:
            await engine.dispose()
    asyncio.run(run())
