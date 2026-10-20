"""Actual PG serializes shared permits and attempts; no gateway/network calls."""

import asyncio
import itertools
import os
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_hybrid_learning_publication import fresh_operation

from app.core.database import create_database_engine
from app.models.learning import LearningOperation, utc_now
from app.models.learning_budget import LearningCorrectionPermit, LearningGenerationAttempt
from app.services.learning_budget import (
    correction_cap,
    initialize_budget,
    reserve_attempt,
    reserve_correction,
)
from app.services.learning_contract import LearningContractError

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")


@pytest.mark.parametrize(
    "m,r,allocation",
    [(m, r, a) for m in (0, 1) for r in (0, 1) for a in itertools.product(range(3), repeat=3)],
)
def test_shared_allocations_and_output_bound(m, r, allocation):
    k = sum(allocation)
    allowed = k <= correction_cap(m, r)
    assert allowed == (9 + m + 2 * r + 2 * k <= 20)
    if allowed:
        out = 512 * m + 2048 * (1 + r) + 4096 * (3 + k) + 8192 * (5 + r + k)
        assert out <= 117248


async def running(db, *, count=2, tail=7):
    uid, oid = await fresh_operation(db)
    op = await db.get(LearningOperation, oid)
    initialize_budget(op)
    op.status = "running"
    op.generation_call_count = count
    op.generation_tail_remaining = tail
    await db.commit()
    return uid, oid, op.generation_deadline


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
def test_concurrent_actual_reservations_failures_keep_attempt_and_tail():
    async def run():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                uid, oid, deadline = await running(db, count=19, tail=1)

            async def reserve():
                async with f() as db:
                    try:
                        await reserve_attempt(
                            db, owner_id=uid, operation_id=oid, stage="unit_review"
                        )
                        return True
                    except LearningContractError:
                        await db.rollback()
                        return False

            # Only one protected baseline slot exists. Racing cannot consume it twice.
            assert sorted(await asyncio.gather(reserve(), reserve(), reserve())) == [
                False,
                False,
                True,
            ]
            async with f() as db:
                op = await db.get(LearningOperation, oid)
                assert op.generation_call_count == 20 and op.generation_tail_remaining == 0
                assert op.generation_deadline == deadline
                attempts = list(
                    (
                        await db.scalars(
                            select(LearningGenerationAttempt).where(
                                LearningGenerationAttempt.operation_id == oid
                            )
                        )
                    ).all()
                )
                assert [a.ordinal for a in attempts] == [20]
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await db.execute(
                            text("DELETE FROM learning_generation_attempts WHERE id=:id"),
                            dict(id=attempts[0].id),
                        )
        finally:
            await e.dispose()

    asyncio.run(run())


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
def test_pair_permits_protect_tail_consume_exactly_two_and_cannot_refund():
    async def run():
        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                uid, oid, deadline = await running(db)
                for role, times in [("explanation", 2), ("code", 2), ("exercise", 1)]:
                    for _ in range(times):
                        pid = await reserve_correction(
                            db, owner_id=uid, operation_id=oid, role=role
                        )
                        assert pid is not None
                        # Another grant cannot overlap a reserved unconsumed pair.
                        assert (
                            await reserve_correction(
                                db, owner_id=uid, operation_id=oid, role="exercise"
                            )
                            is None
                        )
                        await reserve_attempt(
                            db,
                            owner_id=uid,
                            operation_id=oid,
                            stage="resource_correction",
                            permit_id=pid,
                        )
                        await reserve_attempt(
                            db,
                            owner_id=uid,
                            operation_id=oid,
                            stage="resource_review",
                            permit_id=pid,
                        )
                assert (
                    await reserve_correction(db, owner_id=uid, operation_id=oid, role="exercise")
                    is None
                )
                op = await db.get(LearningOperation, oid, populate_existing=True)
                assert op.generation_call_count == 12 and op.generation_tail_remaining == 7
                # A failed request is already counted. It is not subtracted by rollback after send.
                await db.rollback()
            async with f() as db:
                op = await db.get(LearningOperation, oid)
                assert op.generation_call_count == 12 and op.generation_deadline == deadline
                permits = list(
                    (
                        await db.scalars(
                            select(LearningCorrectionPermit).where(
                                LearningCorrectionPermit.operation_id == oid
                            )
                        )
                    ).all()
                )
                assert len(permits) == 5 and all(p.used == 2 for p in permits)
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await db.execute(
                            text("UPDATE learning_correction_permits SET used=0 WHERE id=:id"),
                            dict(id=permits[0].id),
                        )
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await db.execute(
                            text("DELETE FROM learning_correction_permits WHERE id=:id"),
                            dict(id=permits[0].id),
                        )
        finally:
            await e.dispose()

    asyncio.run(run())


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
def test_goal_mapping_single_slot_deadline_and_expiry():
    async def run():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                op = await db.get(LearningOperation, oid)
                initialize_budget(op)
                deadline = op.generation_deadline
                await db.commit()
                seconds = await reserve_attempt(
                    db, owner_id=uid, operation_id=oid, stage="goal_mapping"
                )
                assert 0 < seconds <= 60
                with pytest.raises(LearningContractError, match="GOAL_MAPPING_LIMIT"):
                    await reserve_attempt(db, owner_id=uid, operation_id=oid, stage="goal_mapping")
                await db.rollback()
                op = await db.get(LearningOperation, oid)
                initialize_budget(op)
                assert (
                    op.generation_call_count == 1
                    and op.generation_mapping_count == 1
                    and op.generation_deadline == deadline
                )
                op.status = "running"
                op.generation_tail_remaining = 9
                op.generation_deadline = utc_now() - timedelta(seconds=1)
                await db.commit()
                with pytest.raises(LearningContractError, match="GENERATION_LIMIT"):
                    await reserve_attempt(
                        db, owner_id=uid, operation_id=oid, stage="plan_generation"
                    )
                await db.rollback()
        finally:
            await e.dispose()

    asyncio.run(run())


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
@pytest.mark.parametrize("mapping", [0, 1])
def test_rebuilt_plan_has_only_four_shared_pairs(mapping):
    async def run():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                uid, oid, _ = await running(db, count=4 + mapping, tail=7)
                op = await db.get(LearningOperation, oid)
                # Synthetic budget state after four plan/review attempts; not a real rebuilt plan.
                op.generation_mapping_count = mapping
                op.generation_rebuild_count = 1
                await db.commit()
                for role in ["explanation", "explanation", "code", "code"]:
                    pid = await reserve_correction(db, owner_id=uid, operation_id=oid, role=role)
                    assert pid is not None
                    await reserve_attempt(
                        db,
                        owner_id=uid,
                        operation_id=oid,
                        stage="resource_correction",
                        permit_id=pid,
                    )
                    await reserve_attempt(
                        db, owner_id=uid, operation_id=oid, stage="resource_review", permit_id=pid
                    )
                assert (
                    await reserve_correction(db, owner_id=uid, operation_id=oid, role="exercise")
                    is None
                )
                op = await db.get(LearningOperation, oid, populate_existing=True)
                assert op.generation_call_count + op.generation_tail_remaining == 19 + mapping
        finally:
            await e.dispose()

    asyncio.run(run())


def test_deadline_rechecked_after_durable_reservation_before_network():
    from app.agents.shared_learning_plan import CallWindow
    from app.services.provider_gateway import StructuredRequest, TextRequest

    async def run():
        window = CallWindow()

        class Gateway:
            calls = 0

            async def generate_structured(self, request, *, retry_safe=False):
                self.calls += 1
                raise AssertionError("must not send after deadline")

        async def reserve(request, permit_id):
            window.deadline = 0

        window.reserve_request = reserve
        gateway = Gateway()
        with pytest.raises(LearningContractError, match="GENERATION_LIMIT"):
            await window.send(
                gateway, StructuredRequest(TextRequest(messages=()), {}, stage="plan_generation")
            )
        assert window.used == 1 and gateway.calls == 0

    asyncio.run(run())


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
def test_full_pipeline_pair_exhaustion_still_finishes_unit_audit_without_publication():
    from om_fixtures import material_fixture
    from test_hybrid_learning_publication import flow_inputs, sequence
    from test_hybrid_resource_review import ReviewGateway, answer

    from app.models.learning_review_case import LearningReviewCase
    from app.services.planned_learning_flow import run_planned_operation

    async def run():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                workspace, _ = material_fixture()
                original = sequence()
                values = [original[0]]
                for i, candidate in enumerate(workspace.candidates()):
                    values.extend([candidate.envelope, answer("revise")])
                    values.extend([candidate.envelope, answer("revise")])
                    if i < 2:
                        values.extend([candidate.envelope, answer("pass")])
                values.append(original[-1])
                gateway = ReviewGateway(values)
                result = await run_planned_operation(
                    db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=gateway
                )
                assert result["status"] == "awaiting_human"
                op = await db.get(LearningOperation, oid, populate_existing=True)
                assert op.generation_call_count == len(gateway.requests) == 19
                assert op.generation_tail_remaining == 0
                assert gateway.requests[-1].stage == "unit_review"
                case = await db.scalar(
                    select(LearningReviewCase).where(LearningReviewCase.operation_id == oid)
                )
                assert case.state == "pending"
                permits = list(
                    (
                        await db.scalars(
                            select(LearningCorrectionPermit).where(
                                LearningCorrectionPermit.operation_id == oid
                            )
                        )
                    ).all()
                )
                assert len(permits) == 5 and all(p.used == 2 for p in permits)
        finally:
            await e.dispose()

    asyncio.run(run())
