"""Actual PG case/decision ownership, persistence, invalidation and races."""

import asyncio
import os
from uuid import uuid4

import pytest
from om_fixtures import material_fixture, plan_fixture
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_hybrid_resource_review import ReviewGateway, answer

from app.agents.hybrid_resource_review import UNIT_CHECKS, review_once
from app.agents.shared_learning_plan import CallWindow
from app.core.database import create_database_engine
from app.models.learning_review_case import LearningReviewCase, LearningReviewDecision
from app.services.learning_contract import LearningContractError
from app.services.learning_review_cases import create_review_case, decide_case
from app.services.learning_review_records import plan_binding, save_review
from app.services.teaching_actions import assemble_actions
from app.services.unit_material import unit_material

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="actual isolated PG required")


async def case_fixture(db, *, unit_verdict="needs_human"):
    user, unit, op, plan = await plan_fixture(db)
    w, _ = material_fixture()
    w.binding = plan_binding(plan, op.id)
    # Rebind all candidate dependency digests to the actual persisted plan.
    for c in w.candidates():
        n = w.stage(c.role, c.envelope)
        w.disposition(n.role, n.id, "pass")
    scenes = [
        {
            "role": c.role,
            "scene_key": c.role,
            "scene_id": str(uuid4()),
            "scene_version": 1,
            "resource_id": c.id,
            "resource_digest": c.content_digest,
            "dependency_digest": c.dependency_digest,
        }
        for c in w.candidates()
    ]
    material = unit_material(w, scenes, assemble_actions(w.candidates()))
    records = []
    for c in w.candidates():
        r = await review_once(
            ReviewGateway([answer()]),
            CallWindow(),
            binding=w.binding,
            input_snapshot=w.input_snapshot,
            target_digest=c.content_digest,
            payload={"reference_context": w.reference_context},
            candidates=(c,),
        )
        records.append(await save_review(db, r))
    a = answer(unit_verdict, "unit")
    a["coverage"]["checked"] = sorted(UNIT_CHECKS)

    r = await review_once(
        ReviewGateway([a]),
        CallWindow(),
        binding=w.binding,
        input_snapshot=w.input_snapshot,
        target_digest=material["unit_digest"],
        payload={"reference_context": w.reference_context},
        candidates=w.candidates(),
        scope="unit",
    )
    records.append(await save_review(db, r))
    case = await create_review_case(db, material, [r.id for r in records])
    return user, unit, op, plan, case


def decision_args(case):
    return dict(
        owner_id=case.user_id,
        case_id=case.id,
        expected_digest=case.case_digest,
        reviewer_id="synthetic-maintainer",
        identity_source="synthetic-test-only",
        verdict="approve",
        reason="Synthetic lifecycle check, not actual course signoff.",
        idempotency_key=str(uuid4()),
    )


def test_case_decision_replay_conflict_and_immutability():
    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                user, unit, op, plan, case = await case_fixture(db)
                await db.commit()
                args = decision_args(case)
                decision = await decide_case(db, **args)
                await db.commit()
                decision_id = decision.id
                assert case.state == "approved" and op.status == "awaiting_human"
                assert (await decide_case(db, **args)).id == decision.id
                await db.commit()
                with pytest.raises(LearningContractError):
                    await decide_case(db, **dict(args, reason="changed"))
                await db.rollback()
                for sql, id in [
                    (
                        "UPDATE learning_review_cases SET payload='{}'::jsonb WHERE id=:id",
                        args["case_id"],
                    ),
                    (
                        "UPDATE learning_review_decisions SET verdict='reject' WHERE id=:id",
                        decision_id,
                    ),
                ]:
                    with pytest.raises(DBAPIError):
                        async with db.begin_nested():
                            await db.execute(text(sql), {"id": id})
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(LearningReviewDecision)
                        .where(LearningReviewDecision.case_id == args["case_id"])
                    )
                    == 1
                )
        finally:
            await e.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize("reason", ["cancel", "policy", "new_plan"])
def test_stale_case_invalidates_operation_without_reopening(reason, monkeypatch):
    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                user, unit, op, plan, case = await case_fixture(db)
                await db.commit()
                args = decision_args(case)
                if reason == "cancel":
                    op.status = "canceled"
                    await db.commit()
                if reason == "policy":
                    monkeypatch.setattr(
                        "app.services.learning_review_cases.active_policy_digest", lambda: "f" * 64
                    )
                if reason == "new_plan":
                    from test_learning_plan_persistence import PLAN, REFS

                    from app.services.learning_plans import save_plan
                    from app.services.learning_policy import POLICY

                    await save_plan(
                        db,
                        owner_id=user.id,
                        unit_id=unit.id,
                        operation_id=op.id,
                        plan=PLAN,
                        input_snapshot={},
                        references=REFS,
                        node_ids={"stack"},
                        policy_version="hybrid-review-v1",
                        policy=POLICY,
                    )
                    await db.commit()
                with pytest.raises(LearningContractError, match="REVIEW_CASE_INVALIDATED"):
                    await decide_case(db, **args)
                await db.refresh(op)
                await db.refresh(case)
                assert case.state == "invalidated"
                assert op.status == ("canceled" if reason == "cancel" else "failed")
        finally:
            await e.dispose()

    asyncio.run(exercise())


def test_current_reject_not_eligible_and_concurrent_replay():
    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                with pytest.raises(LearningContractError, match="REJECT_NOT_HUMAN_ELIGIBLE"):
                    await case_fixture(db, unit_verdict="reject")
                await db.rollback()
                user, unit, op, plan, case = await case_fixture(db)
                await db.commit()
                args = decision_args(case)

            async def act():
                async with f() as db:
                    row = await decide_case(db, **args)
                    await db.commit()
                    return row.id

            ids = await asyncio.gather(act(), act())
            assert ids[0] == ids[1]
            async with f() as db:
                with pytest.raises(LearningContractError):
                    await decide_case(db, **dict(args, owner_id=uuid4()))
        finally:
            await e.dispose()

    asyncio.run(exercise())


def test_cancel_racing_approval_cannot_leave_publishable_case():
    from app.models.learning import LearningOperation
    from app.services.learning_review_cases import cancel_review_operation

    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                user, unit, op, plan, case = await case_fixture(db)
                await db.commit()
                args = decision_args(case)
                oid = op.id
                uid = user.id
                cid = case.id

            async def approve():
                async with f() as db:
                    try:
                        await decide_case(db, **args)
                        await db.commit()
                    except LearningContractError:
                        await db.rollback()

            async def cancel():
                async with f() as db:
                    assert await cancel_review_operation(db, owner_id=uid, operation_id=oid)
                    await db.commit()

            await asyncio.gather(approve(), cancel())
            async with f() as db:
                assert (await db.get(LearningOperation, oid)).status == "canceled"
                assert (await db.get(LearningReviewCase, cid)).state == "invalidated"
        finally:
            await e.dispose()

    asyncio.run(exercise())


def test_real_v44_pending_case_invalidates_after_v45_policy_switch(monkeypatch):
    """Use actual prior prompt/policy, then current digest; never issue a model call."""
    import json
    from pathlib import Path

    from app.services.learning_policy import POLICY, active_policy_digest

    async def exercise():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        old = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "docs/acceptance/phase-1-review-remaining-r01/cases.json"
            ).read_text()
        )["assessment-gap:candidate"]
        old_instruction = json.loads(bytes.fromhex(old["wire_hex"]))["input"][0]["content"]
        try:
            async with f() as db:
                with monkeypatch.context() as patch:
                    patch.setitem(POLICY, "resource_review_prompt", "evidence-resource-review-v4.4")
                    patch.setattr(
                        "app.agents.hybrid_resource_review.REVIEW_V4_PROMPT",
                        "evidence-resource-review-v4.4",
                    )
                    patch.setattr("app.agents.hybrid_resource_review.INSTRUCTION", old_instruction)
                    user, unit, op, plan, case = await case_fixture(db)
                    old_digest = plan.policy_digest
                    await db.commit()
                    args = decision_args(case)
                assert old_digest != active_policy_digest()
                with pytest.raises(LearningContractError, match="REVIEW_CASE_INVALIDATED"):
                    await decide_case(db, **args)
                await db.refresh(case)
                await db.refresh(op)
                assert case.state == "invalidated" and op.status == "failed"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(LearningReviewDecision)
                        .where(LearningReviewDecision.case_id == case.id)
                    )
                    == 0
                )
                assert case.payload["material"]["binding"]["policy_digest"] == old_digest
        finally:
            await e.dispose()

    asyncio.run(exercise())
