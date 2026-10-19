"""Exact published teaching node, old receipt replay, and path attribution in real PG."""

import asyncio
import os
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_hybrid_learning_publication import flow_inputs, fresh_operation, sequence
from test_hybrid_resource_review import ReviewGateway
from test_teaching_node_publication_binding import bound_inputs

from app.agents.profile_events import PROFILE_MERGE_RULE_VERSION
from app.core.database import create_database_engine
from app.models.learning import GeneratedResource, StudentProfile
from app.models.learning_state import LearningEvidence, NodeMasteryCurrent
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.learning_contract import LearningContractError
from app.services.path_versions import plan_or_replan_path
from app.services.planned_learning_flow import run_planned_operation
from app.services.quiz_scoring import score_exercise_content
from app.services.quiz_submissions import quiz_request_digest, submit_quiz_attempt
from app.services.shared_plan_inputs import shared_plan_inputs
from app.services.teaching_binding import select_teaching_context

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="actual isolated PG required")


@pytest.mark.parametrize("mode", ["target", "recommended"])
def test_evidence_uses_published_node_and_path_replanning_keeps_target(mode):
    async def run():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                db.add(
                    StudentProfile(
                        user_id=uid,
                        version=1,
                        merge_rule_version=PROFILE_MERGE_RULE_VERSION,
                        initial_query="synthetic stack",
                    )
                )
                await db.commit()
                graph = default_knowledge_graph_repository()
                path, _ = await plan_or_replan_path(
                    db,
                    owner_id=uid,
                    target_node_id="stack",
                    graph=graph,
                    trigger_reason="initial_plan",
                )
                context = select_teaching_context(
                    owner_id=uid,
                    target_node_id="stack",
                    original_request="synthetic stack",
                    mode=mode,
                    graph=graph,
                    path=path,
                )
                i = await shared_plan_inputs(
                    db,
                    owner_id=uid,
                    node_id=context["teaching_node_id"],
                    goal=context["segment_goal"],
                    language="c",
                    graph=graph,
                    teaching_context=context,
                )
                await db.commit()
                values = deepcopy(sequence())
                values[0]["reference_ids"] = list(i.references)
                result = await run_planned_operation(
                    db, owner_id=uid, operation_id=oid, inputs=i, gateway=ReviewGateway(values)
                )
                resource = await db.get(
                    GeneratedResource, UUID(result["material"]["candidates"][2]["resource_id"])
                )
                answers = [
                    {"question_id": q["id"], "answer": q["answer"]}
                    for q in resource.content["items"]
                ]
                record, created = await submit_quiz_attempt(
                    db,
                    owner_id=uid,
                    idempotency_key=str(uuid4()),
                    resource_id=resource.id,
                    resource_version=resource.version,
                    answers=answers,
                )
                assert created and record.knowledge_node_id == context["teaching_node_id"]
                assert record.payload["teaching_binding"]["publication_version"] == 1
                assert record.payload["teaching_binding"]["target_node_id"] == "stack"
                nodes = (
                    await db.scalars(
                        select(NodeMasteryCurrent.knowledge_node_id).where(
                            NodeMasteryCurrent.user_id == uid
                        )
                    )
                ).all()
                assert nodes == [context["teaching_node_id"]]
                if mode == "recommended":
                    assert context["teaching_node_id"] != "stack"
                new_path, _ = await plan_or_replan_path(
                    db,
                    owner_id=uid,
                    target_node_id="stack",
                    graph=graph,
                    trigger_reason="mastery_changed",
                )
                assert new_path.target_node_id == "stack"
                assert record.knowledge_node_id == context["teaching_node_id"]
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_old_planned_blocks_new_mastery_but_replays_existing_receipt():
    async def run():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                result = await run_planned_operation(
                    db,
                    owner_id=uid,
                    operation_id=oid,
                    inputs=flow_inputs(),
                    gateway=ReviewGateway(sequence()),
                )
                r = await db.get(
                    GeneratedResource, UUID(result["material"]["candidates"][2]["resource_id"])
                )
                answers = [
                    {"question_id": q["id"], "answer": q["answer"]} for q in r.content["items"]
                ]
                with pytest.raises(LearningContractError, match="TEACHING_BINDING_UNVERIFIED"):
                    await submit_quiz_attempt(
                        db,
                        owner_id=uid,
                        idempotency_key=str(uuid4()),
                        resource_id=r.id,
                        resource_version=r.version,
                        answers=answers,
                    )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(LearningEvidence)
                        .where(LearningEvidence.user_id == uid)
                    )
                    == 0
                )
                scored = score_exercise_content(
                    resource_id=str(r.id),
                    resource_version=r.version,
                    content=r.content,
                    answers=answers,
                )
                key = str(uuid4())
                historical = LearningEvidence(
                    user_id=uid,
                    idempotency_key=key,
                    request_digest=quiz_request_digest(
                        resource_id=r.id, resource_version=r.version, answers=answers
                    ),
                    evidence_type="quiz_attempt",
                    knowledge_node_id="stack",
                    resource_id=r.id,
                    resource_version=r.version,
                    schema_version=scored.schema_version,
                    rule_version=scored.rule_version,
                    payload={
                        "score": scored.score,
                        "question_results": [],
                        "question_count": 3,
                        "correct_count": 3,
                    },
                )
                db.add(historical)
                await db.commit()
                replay, created = await submit_quiz_attempt(
                    db,
                    owner_id=uid,
                    idempotency_key=key,
                    resource_id=r.id,
                    resource_version=r.version,
                    answers=answers,
                )
                assert not created and replay.id == historical.id
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(NodeMasteryCurrent)
                        .where(NodeMasteryCurrent.user_id == uid)
                    )
                    == 0
                )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_old_exact_quiz_keeps_original_publication_after_reexplanation():
    from test_hybrid_learning_publication import classroom_reexplanation

    from app.services.planned_reexplanation import run_planned_reexplanation

    async def run():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                result = await run_planned_operation(
                    db,
                    owner_id=uid,
                    operation_id=oid,
                    inputs=bound_inputs(uid),
                    gateway=ReviewGateway(sequence()),
                )
                unit_id = UUID(result["learning_unit_id"])
                r = await db.get(
                    GeneratedResource, UUID(result["material"]["candidates"][2]["resource_id"])
                )
                parent, _ = await classroom_reexplanation(db, uid, unit_id, "simpler")
                v = sequence()
                new = await run_planned_reexplanation(
                    db,
                    owner_id=uid,
                    classroom_operation_id=parent.id,
                    gateway=ReviewGateway([v[1], v[2], v[4], v[6], v[7]]),
                )
                assert new["status"] == "completed"
                answers = [
                    {"question_id": q["id"], "answer": q["answer"]} for q in r.content["items"]
                ]
                record, _ = await submit_quiz_attempt(
                    db,
                    owner_id=uid,
                    idempotency_key=str(uuid4()),
                    resource_id=r.id,
                    resource_version=r.version,
                    answers=answers,
                )
                assert record.knowledge_node_id == "stack"
                assert record.payload["teaching_binding"]["publication_version"] == 1
        finally:
            await engine.dispose()

    asyncio.run(run())
