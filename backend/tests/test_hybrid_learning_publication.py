"""Actual PG atomic publication and blocked read boundaries with synthetic model data."""

import asyncio
import json
import os
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from om_fixtures import material_fixture
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_hybrid_resource_review import ReviewGateway, answer
from test_shared_learning_plan import DRAFT, inputs

from app.agents.hybrid_resource_review import UNIT_CHECKS
from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import GeneratedResource, LearningOperation, LearningUnit
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_publication import LearningPublication
from app.services.hybrid_learning_publication import (
    current_publication,
    publish_approved_case,
    publish_complete_unit,
)
from app.services.learning_contract import LearningContractError
from app.services.learning_review_cases import cancel_review_operation, decide_case
from app.services.owned_learning import published_resource, published_scenes
from app.services.planned_learning_flow import run_planned_operation

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="actual isolated PG required")


async def fresh_operation(db):
    user = User(is_guest=True)
    db.add(user)
    await db.flush()
    op = LearningOperation(
        user_id=user.id,
        idempotency_key=str(uuid4()),
        request_digest="0" * 64,
        goal="synthetic stack",
        preferred_language="C",
    )
    db.add(op)
    await db.commit()
    return user.id, op.id


def sequence(unit_verdict="pass"):
    w, _ = material_fixture()
    values = [DRAFT]
    for c in w.candidates():
        values.extend([c.envelope, answer()])
    a = answer(unit_verdict, "unit")
    a["coverage"]["checked"] = sorted(UNIT_CHECKS)
    return values + [a]


def flow_inputs():
    from app.agents.shared_learning_plan import PlanInputs

    i = inputs()
    return PlanInputs(
        i.metadata,
        i.references,
        i.node_ids,
        i.learner_evidence,
        material_fixture()[0].reference_context,
    )


def test_full_automatic_flow_is_atomic_and_budget_is_persistent(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                uid, oid = await fresh_operation(db)
                g = ReviewGateway(sequence())
                result = await run_planned_operation(
                    db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=g
                )
                assert result["status"] == "completed" and len(g.requests) == 8
                for index in (2, 4, 6, 7):
                    sent = json.loads(g.requests[index].prompt.messages[1].content)
                    assert (
                        sent["authoritative_teaching_goal"]["user_request"]
                        == inputs().metadata["goal"]
                    )
                    assert sent["authoritative_teaching_goal"]["status"] == "bound_original_request"
                    assert "facts" not in sent["reference_context"]
                plan = await db.get(
                    LearningPlanVersion, UUID(result["material"]["binding"]["plan_id"])
                )
                assert plan.input_snapshot["reference_context"] == flow_inputs().reference_context
                assert result["material"]["reference_context"] == flow_inputs().reference_context
                op = await db.get(LearningOperation, oid)
                unit = await db.get(LearningUnit, op.learning_unit_id)
                assert op.generation_call_count == 8 and op.status == "completed"
                assert len(await published_scenes(db, uid, unit.id)) == 3
                p = await current_publication(db, owner_id=uid, unit_id=unit.id)
                assert p.approval_source == "auto"
                assert await published_resource(
                    db, uid, UUID(result["material"]["scenes"][0]["resource_id"])
                )
                bad = deepcopy(result["material"])
                bad["scenes"][0]["scene_version"] = 999
                with pytest.raises(LearningContractError):
                    await publish_complete_unit(db, bad, [])
        finally:
            await e.dispose()

    asyncio.run(exercise())


def test_pending_case_blocks_all_formal_reads_and_approve_publishes_without_models(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                uid, oid = await fresh_operation(db)
                g = ReviewGateway(sequence("needs_human"))
                result = await run_planned_operation(
                    db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=g
                )
                assert result["status"] == "awaiting_human"
                op = await db.get(LearningOperation, oid)
                assert not await published_scenes(db, uid, op.learning_unit_id)
                resource = await db.scalar(
                    select(GeneratedResource).where(
                        GeneratedResource.learning_unit_id == op.learning_unit_id
                    )
                )
                assert resource.published_at is None and not await published_resource(
                    db, uid, resource.id
                )
                from app.models.learning_review_case import LearningReviewCase

                case = await db.get(LearningReviewCase, UUID(result["case_id"]))
                args = dict(
                    owner_id=uid,
                    case_id=case.id,
                    expected_digest=case.case_digest,
                    reviewer_id="synthetic",
                    identity_source="synthetic-test",
                    verdict="approve",
                    reason="Synthetic publication test only.",
                    idempotency_key=str(uuid4()),
                )
                await decide_case(db, **args)
                publication = await publish_approved_case(db, owner_id=uid, case_id=case.id)
                assert publication.approval_source == "human_assisted"
                await db.rollback()  # Crash before commit must not expose anything.
            async with f() as db:
                assert not await db.scalar(
                    select(func.count())
                    .select_from(LearningPublication)
                    .where(LearningPublication.operation_id == oid)
                )
                await decide_case(db, **args)
                publication = await publish_approved_case(db, owner_id=uid, case_id=args["case_id"])
                await db.commit()
                assert publication.approval_source == "human_assisted" and len(g.requests) == 8
                assert len(await published_scenes(db, uid, publication.learning_unit_id)) == 3
                assert (
                    await publish_approved_case(db, owner_id=uid, case_id=args["case_id"])
                ).id == publication.id
        finally:
            await e.dispose()

    asyncio.run(exercise())


def test_failure_and_cancel_keep_candidates_private():
    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                uid, oid = await fresh_operation(db)
                g = ReviewGateway(sequence("reject"))
                with pytest.raises(LearningContractError):
                    await run_planned_operation(
                        db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=g
                    )
                op = await db.get(LearningOperation, oid)
                assert op.status == "rejected"
                assert not await db.scalar(
                    select(func.count())
                    .select_from(LearningPublication)
                    .where(LearningPublication.operation_id == oid)
                )
                resources = (
                    await db.scalars(
                        select(GeneratedResource).where(
                            GeneratedResource.learning_unit_id == op.learning_unit_id
                        )
                    )
                ).all()
                assert all(r.published_at is None for r in resources)
        finally:
            await e.dispose()

    asyncio.run(exercise())


async def classroom_reexplanation(db, uid, unit_id, action):
    from app.models.classroom import ClassroomOperation, ClassroomSession
    from app.services.classroom import create_classroom

    await create_classroom(db, owner_id=uid, unit_id=unit_id, idempotency_key=str(uuid4()))
    session = await db.scalar(
        select(ClassroomSession).where(
            ClassroomSession.user_id == uid, ClassroomSession.learning_unit_id == unit_id
        )
    )
    parent = ClassroomOperation(
        user_id=uid,
        learning_unit_id=unit_id,
        kind="reexplanation",
        idempotency_key=str(uuid4()),
        request_digest="0" * 64,
        base_revision=session.revision,
        generation_id=session.generation_id,
        status="accepted",
        result_snapshot={
            "scene_key": "explanation",
            "base_scene_version": session.scene_version,
            "action": action,
        },
    )
    db.add(parent)
    await db.commit()
    return parent, session


@pytest.mark.parametrize("action", ["simpler", "another_example"])
def test_planned_reexplanation_rebinds_complete_unit_and_retains_old_snapshot(action, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    from app.services.planned_reexplanation import planned_materials, run_planned_reexplanation

    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                uid, oid = await fresh_operation(db)
                first = await run_planned_operation(
                    db,
                    owner_id=uid,
                    operation_id=oid,
                    inputs=flow_inputs(),
                    gateway=ReviewGateway(sequence()),
                )
                unit_id = UUID(first["learning_unit_id"])
                old = await current_publication(db, owner_id=uid, unit_id=unit_id)
                parent, session = await classroom_reexplanation(db, uid, unit_id, action)
                assert session.scene_key == "explanation" and session.publication_version == 1
                materials = await planned_materials(
                    db,
                    owner_id=uid,
                    unit_id=unit_id,
                    scene_key="intro",
                    base_version=1,
                    action=action,
                )
                assert materials["code_language"] == "C" and materials["reuse_content"]["code"]
                with pytest.raises(LearningContractError, match="REEXPLANATION_SCENE_UNSUPPORTED"):
                    await planned_materials(
                        db,
                        owner_id=uid,
                        unit_id=unit_id,
                        scene_key="code",
                        base_version=1,
                        action=action,
                    )
                values = sequence()
                if action == "simpler":
                    values = [values[1], values[2], values[4], values[6], values[7]]
                else:
                    values[0] = deepcopy(values[0])
                    values[0]["shared_example"]["input_description"] = "push(30),push(40),pop()"
                g = ReviewGateway(values)
                result = await run_planned_reexplanation(
                    db, owner_id=uid, classroom_operation_id=parent.id, gateway=g
                )
                assert result["status"] == "completed" and len(g.requests) == (
                    5 if action == "simpler" else 8
                )
                current = await current_publication(db, owner_id=uid, unit_id=unit_id)
                assert current.version == 2 and current.plan_id == (
                    old.plan_id if action == "simpler" else current.plan_id
                )
                if action == "another_example":
                    assert current.plan_id != old.plan_id
                assert {r.id for _, r in await published_scenes(db, uid, unit_id)} == {
                    UUID(s["resource_id"]) for s in result["material"]["scenes"]
                }
                assert await current_publication(db, owner_id=uid, unit_id=unit_id, version=1)
                assert await published_resource(
                    db, uid, UUID(first["material"]["scenes"][0]["resource_id"])
                )
                replay = await run_planned_reexplanation(
                    db, owner_id=uid, classroom_operation_id=parent.id, gateway=ReviewGateway([])
                )
                assert replay["status"] == "completed"
        finally:
            await e.dispose()

    asyncio.run(exercise())


def test_old_course_remains_usable_during_new_human_wait_and_cancel(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    from app.services.planned_reexplanation import run_planned_reexplanation

    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                uid, oid = await fresh_operation(db)
                first = await run_planned_operation(
                    db,
                    owner_id=uid,
                    operation_id=oid,
                    inputs=flow_inputs(),
                    gateway=ReviewGateway(sequence()),
                )
                unit_id = UUID(first["learning_unit_id"])
                parent, session = await classroom_reexplanation(db, uid, unit_id, "simpler")
                values = sequence("needs_human")
                values = [values[1], values[2], values[4], values[6], values[7]]
                result = await run_planned_reexplanation(
                    db,
                    owner_id=uid,
                    classroom_operation_id=parent.id,
                    gateway=ReviewGateway(values),
                )
                assert result["status"] == "awaiting_human"
                assert (await current_publication(db, owner_id=uid, unit_id=unit_id)).version == 1
                assert len(await published_scenes(db, uid, unit_id)) == 3
                await cancel_review_operation(
                    db, owner_id=uid, operation_id=UUID(result["operation_id"])
                )
                await db.commit()
                with pytest.raises(LearningContractError):
                    await publish_approved_case(db, owner_id=uid, case_id=UUID(result["case_id"]))
                assert (await current_publication(db, owner_id=uid, unit_id=unit_id)).version == 1
        finally:
            await e.dispose()

    asyncio.run(exercise())


def test_withdrawal_and_foreign_owner_block_resource_qualification(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    from app.services.hybrid_learning_publication import withdraw_publication

    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                uid, oid = await fresh_operation(db)
                result = await run_planned_operation(
                    db,
                    owner_id=uid,
                    operation_id=oid,
                    inputs=flow_inputs(),
                    gateway=ReviewGateway(sequence()),
                )
                unit_id = UUID(result["learning_unit_id"])
                p = await current_publication(db, owner_id=uid, unit_id=unit_id)
                rid = UUID(result["material"]["scenes"][0]["resource_id"])
                assert not await published_resource(db, uuid4(), rid)
                await withdraw_publication(
                    db, owner_id=uid, publication_id=p.id, reason_code="SEMANTIC_WITHDRAWN"
                )
                await db.commit()
                assert not await current_publication(db, owner_id=uid, unit_id=unit_id)
                assert not await published_resource(db, uid, rid)
                op = await db.get(LearningOperation, oid)
                assert op.status == "completed"
        finally:
            await e.dispose()

    asyncio.run(exercise())


def test_mode_change_during_reexplanation_prevents_late_publication(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    from app.services.classroom import set_classroom_mode
    from app.services.planned_reexplanation import run_planned_reexplanation

    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                uid, oid = await fresh_operation(db)
                first = await run_planned_operation(
                    db,
                    owner_id=uid,
                    operation_id=oid,
                    inputs=flow_inputs(),
                    gateway=ReviewGateway(sequence()),
                )
                unit_id = UUID(first["learning_unit_id"])
                parent, session = await classroom_reexplanation(db, uid, unit_id, "simpler")
                values = sequence()
                values = [values[1], values[2], values[4], values[6], values[7]]

                class ChangedGateway(ReviewGateway):
                    async def generate_structured(self, request, *, retry_safe=False):
                        assert not db.in_transaction(), "Model stage held a database transaction"
                        if len(self.values) == 1:
                            async with f() as other:
                                await set_classroom_mode(
                                    other,
                                    owner_id=uid,
                                    unit_id=unit_id,
                                    idempotency_key=str(uuid4()),
                                    mode="interactive",
                                    enabled_roles=[],
                                    expected_revision=1,
                                )
                        return await super().generate_structured(request, retry_safe=retry_safe)

                with pytest.raises(LearningContractError, match="CLASSROOM_VERSION_CONFLICT"):
                    await run_planned_reexplanation(
                        db,
                        owner_id=uid,
                        classroom_operation_id=parent.id,
                        gateway=ChangedGateway(values),
                    )
                assert (await current_publication(db, owner_id=uid, unit_id=unit_id)).version == 1
        finally:
            await e.dispose()

    asyncio.run(exercise())


def test_atomic_publication_racing_cancel_has_one_consistent_terminal(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    from app.models.learning_review_case import LearningReviewCase

    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                uid, oid = await fresh_operation(db)
                result = await run_planned_operation(
                    db,
                    owner_id=uid,
                    operation_id=oid,
                    inputs=flow_inputs(),
                    gateway=ReviewGateway(sequence("needs_human")),
                )
                case = await db.get(LearningReviewCase, UUID(result["case_id"]))
                cid = case.id
                cd = case.case_digest
                await db.commit()

            async def approve_publish():
                async with f() as db:
                    try:
                        await decide_case(
                            db,
                            owner_id=uid,
                            case_id=cid,
                            expected_digest=cd,
                            reviewer_id="synthetic",
                            identity_source="synthetic-test",
                            verdict="approve",
                            reason="Synthetic race verification only.",
                            idempotency_key=str(uuid4()),
                        )
                        await publish_approved_case(db, owner_id=uid, case_id=cid)
                        await db.commit()
                    except LearningContractError:
                        await db.rollback()

            async def cancel():
                async with f() as db:
                    await cancel_review_operation(db, owner_id=uid, operation_id=oid)
                    await db.commit()

            await asyncio.gather(approve_publish(), cancel())
            async with f() as db:
                op = await db.get(LearningOperation, oid)
                count = await db.scalar(
                    select(func.count())
                    .select_from(LearningPublication)
                    .where(LearningPublication.operation_id == oid)
                )
                assert (op.status, count) in [("completed", 1), ("canceled", 0)]
        finally:
            await e.dispose()

    asyncio.run(exercise())
