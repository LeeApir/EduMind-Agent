"""Synthetic verifier injection exercises mechanics only, never semantic repair quality."""

import asyncio
import json
import os
from copy import deepcopy
from types import MappingProxyType

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_hybrid_learning_publication import flow_inputs, fresh_operation, sequence
from test_hybrid_resource_review import ReviewGateway
from test_plan_check_flow import model_answer
from test_shared_learning_plan import DRAFT

from app.core.database import create_database_engine
from app.models.learning import LearningOperation
from app.models.learning_plan import LearningPlanVersion
from app.models.plan_check import PlanCheck, PlanRebuildEvent
from app.services import plan_verifiers
from app.services.learning_contract import LearningContractError
from app.services.learning_policy import POLICY
from app.services.planned_learning_flow import run_planned_operation
from app.services.provider_gateway import StructuredResult, TransportAudit

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="actual isolated PG required")


class SyntheticVerifier:
    version = "test-v1"

    def verify(self, plan, record):
        return plan_verifiers.VerifiedDefect(
            tuple(f["finding_id"] for f in record["model_result"]["findings"]),
            tuple(f["target_anchor"] for f in record["model_result"]["findings"]),
            {"synthetic": True, "not_a_semantic_proof": True},
        )


@pytest.fixture
def registered(monkeypatch):
    # In-memory test-only approval. No production setting, registry file or policy changed.
    monkeypatch.setattr(
        plan_verifiers,
        "APPROVED_PLAN_VERIFIERS",
        MappingProxyType({"synthetic-test": SyntheticVerifier()}),
    )
    monkeypatch.setitem(POLICY, "approved_plan_verifiers", ["synthetic-test"])
    monkeypatch.setitem(POLICY, "approved_plan_verifier_versions", {"synthetic-test": "test-v1"})


class RebuildGateway(ReviewGateway):
    def __init__(self, recheck="pass", bad_rebuild=False):
        super().__init__(sequence())
        self.recheck = recheck
        self.bad_rebuild = bad_rebuild

    async def generate_structured(self, request, *, retry_safe=False):
        if request.stage in ("plan_check", "plan_recheck", "plan_rebuild"):
            self.requests.append(request)
            if request.stage == "plan_rebuild":
                value = deepcopy(DRAFT)
                value["shared_example"]["input_description"] += " Synthetic rebuilt version."
                if self.bad_rebuild:
                    value["reference_ids"] = ["not_a_bound_reference"]
            elif request.stage == "plan_recheck" and self.recheck == "pass":
                value = model_answer()
            else:
                payload = json.loads(request.prompt.messages[-1].content)
                aid = next(
                    a["anchor_id"] for a in payload["anchor_catalog"] if a["source_kind"] == "plan"
                )
                value = model_answer("issue")
                value["unresolved"] = []
                value["findings"] = [
                    dict(
                        finding_id="f1",
                        category="plan_internal_conflict",
                        severity="major",
                        target_anchor=aid,
                        evidence_anchors=[aid],
                        condition_or_counterexample="Synthetic protocol premise only.",
                        impact="Synthetic correction mechanics test, not semantic proof.",
                        suggested_action="consider_rebuild",
                    )
                ]
            return StructuredResult(
                value, "synthetic", transport_audit=TransportAudit("1" * 64, "2" * 64, "3" * 64)
            )
        return await super().generate_structured(request, retry_safe=retry_safe)


def test_empty_production_registry_does_not_rebuild():
    assert (
        dict(plan_verifiers.APPROVED_PLAN_VERIFIERS) == {}
        and POLICY["approved_plan_verifiers"] == []
    )

    async def run():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                g = RebuildGateway()
                with pytest.raises(LearningContractError, match="PLAN_REVIEW_REQUIRED"):
                    await run_planned_operation(
                        db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=g
                    )
                op = await db.get(LearningOperation, oid, populate_existing=True)
                assert op.generation_rebuild_count == 0 and len(g.requests) == 2
                assert (
                    await db.scalars(
                        select(PlanRebuildEvent).where(PlanRebuildEvent.operation_id == oid)
                    )
                ).all() == []
        finally:
            await e.dispose()

    asyncio.run(run())


@pytest.mark.parametrize("recheck,bad", [("pass", False), ("issue", False), ("pass", True)])
def test_one_rebuilt_version_recheck_and_failure_stop(registered, recheck, bad):
    async def run():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                g = RebuildGateway(recheck, bad)
                if bad:
                    with pytest.raises(LearningContractError):
                        await run_planned_operation(
                            db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=g
                        )
                elif recheck != "pass":
                    with pytest.raises(LearningContractError, match="PLAN_REVIEW_REQUIRED"):
                        await run_planned_operation(
                            db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=g
                        )
                else:
                    result = await run_planned_operation(
                        db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=g
                    )
                    assert result["status"] == "completed"
                op = await db.get(LearningOperation, oid, populate_existing=True)
                plans = (
                    await db.scalars(
                        select(LearningPlanVersion)
                        .where(LearningPlanVersion.learning_unit_id == op.learning_unit_id)
                        .order_by(LearningPlanVersion.version)
                    )
                ).all()
                events = (
                    await db.scalars(
                        select(PlanRebuildEvent)
                        .where(PlanRebuildEvent.operation_id == oid)
                        .order_by(PlanRebuildEvent.created_at)
                    )
                ).all()
                assert op.generation_rebuild_count == 1
                assert [ev.event_type for ev in events] == [
                    "reserved",
                    "failed" if bad else "completed",
                ]
                assert sum(r.stage == "plan_rebuild" for r in g.requests) == 1
                assert [p.version for p in plans] == ([1] if bad else [1, 2])
                if not bad:
                    assert plans[0].input_digest == plans[1].input_digest
                    assert plans[0].references_digest == plans[1].references_digest
                    assert plans[0].policy_digest == plans[1].policy_digest
                    assert plans[0].plan_digest != plans[1].plan_digest
                    checks = (
                        await db.scalars(select(PlanCheck).where(PlanCheck.operation_id == oid))
                    ).all()
                    assert {c.stage for c in checks} == {"plan_check", "plan_recheck"}
                if recheck != "pass" or bad:
                    assert op.status == "failed" and len(g.requests) == (3 if bad else 4)
                else:
                    assert (
                        op.generation_call_count == len(g.requests) == 11
                        and op.generation_tail_remaining == 0
                    )
        finally:
            await e.dispose()

    asyncio.run(run())


def test_rebuild_reservation_is_single_under_concurrency(registered):
    async def run():
        from om_fixtures import plan_fixture

        from app.agents.plan_check import inspect_plan
        from app.agents.shared_learning_plan import CallWindow
        from app.services.learning_budget import initialize_budget
        from app.services.plan_check import save_plan_check
        from app.services.plan_rebuild import reserve_rebuild

        e = create_database_engine(URL)
        f = async_sessionmaker(e, expire_on_commit=False)
        try:
            async with f() as db:
                _, _, op, plan = await plan_fixture(db)
                initialize_budget(op)
                op.status = "running"
                op.phase = "plan_check"
                op.generation_call_count = 2
                op.generation_tail_remaining = 7
                rec = await inspect_plan(RebuildGateway(), CallWindow(), plan, op.id)
                check = await save_plan_check(db, rec)
                uid = op.user_id
                oid = op.id
                cid = check.id
                await db.commit()

            async def reserve():
                async with f() as db:
                    try:
                        await reserve_rebuild(db, owner_id=uid, check_id=cid)
                        return True
                    except LearningContractError:
                        await db.rollback()
                        return False

            assert sorted(await asyncio.gather(reserve(), reserve())) == [False, True]
            async with f() as db:
                op = await db.get(LearningOperation, oid)
                assert (
                    op.generation_rebuild_count == 1
                    and op.generation_call_count == 2
                    and op.generation_tail_remaining == 9
                )
                assert (
                    len(
                        (
                            await db.scalars(
                                select(PlanRebuildEvent).where(PlanRebuildEvent.operation_id == oid)
                            )
                        ).all()
                    )
                    == 1
                )
        finally:
            await e.dispose()

    asyncio.run(run())


@pytest.mark.parametrize("problem", ["reject", "missing_premise", "unresolved", "user_target"])
def test_severe_unknown_or_user_requirement_never_becomes_rebuild(registered, problem):
    from dataclasses import replace

    class Unrepairable(RebuildGateway):
        async def generate_structured(self, request, *, retry_safe=False):
            result = await super().generate_structured(request, retry_safe=retry_safe)
            if request.stage == "plan_check":
                value = deepcopy(result.value)
                if problem == "reject":
                    value["verdict"] = "reject"
                    value["findings"][0].update(category="unsafe_plan", suggested_action="reject")
                elif problem == "missing_premise":
                    value["findings"][0]["category"] = "missing_premise"
                elif problem == "unresolved":
                    value["unresolved"] = ["Synthetic premise is not verified"]
                else:
                    payload = json.loads(request.prompt.messages[-1].content)
                    aid = next(
                        a["anchor_id"]
                        for a in payload["anchor_catalog"]
                        if a["source_kind"] == "user_request"
                    )
                    value["findings"][0]["target_anchor"] = aid
                return replace(result, value=value)
            return result

    async def run():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                gateway = Unrepairable()
                with pytest.raises(
                    LearningContractError,
                    match="PLAN_REJECTED" if problem == "reject" else "PLAN_REVIEW_REQUIRED",
                ):
                    await run_planned_operation(
                        db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=gateway
                    )
                op = await db.get(LearningOperation, oid, populate_existing=True)
                assert op.generation_rebuild_count == 0 and len(gateway.requests) == 2
        finally:
            await e.dispose()

    asyncio.run(run())


def test_publication_cannot_bypass_required_plan_check():
    async def run():
        from test_learning_review_cases import case_fixture

        from app.services.hybrid_learning_publication import publication_checks

        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                *_, case = await case_fixture(db, with_plan_check=False)
                material = deepcopy(case.payload["material"])
                with pytest.raises(LearningContractError, match="PUBLICATION_PLAN_CHECK_REQUIRED"):
                    await publication_checks(db, material, [])
                await db.rollback()
        finally:
            await e.dispose()

    asyncio.run(run())


@pytest.mark.parametrize("tamper", ["version", "premises"])
def test_proof_version_and_recomputed_premises_cannot_authorize_calls(registered, tamper):
    async def run():
        from om_fixtures import plan_fixture

        from app.agents.plan_check import inspect_plan
        from app.agents.shared_learning_plan import CallWindow
        from app.services.learning_budget import initialize_budget
        from app.services.plan_check import save_plan_check
        from app.services.plan_rebuild import reserve_rebuild

        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                _, _, op, plan = await plan_fixture(db)
                oid = op.id
                initialize_budget(op)
                op.status = "running"
                op.phase = "plan_check"
                op.generation_call_count = 2
                op.generation_tail_remaining = 7
                record = await inspect_plan(RebuildGateway(), CallWindow(), plan, op.id)
                if tamper == "version":
                    record["proofs"][0]["verifier_version"] = "unapproved-version"
                    with pytest.raises(LearningContractError, match="PLAN_EVIDENCE_INVALID"):
                        await save_plan_check(db, record)
                else:
                    record["proofs"][0]["premises_digest"] = "0" * 64
                    row = await save_plan_check(db, record)
                    await db.commit()
                    with pytest.raises(LearningContractError, match="PLAN_PROOF_SOURCE_INVALID"):
                        await reserve_rebuild(db, owner_id=op.user_id, check_id=row.id)
                    await db.rollback()
                    op = await db.get(LearningOperation, oid, populate_existing=True)
                    assert op.generation_rebuild_count == 0 and op.generation_call_count == 2
                await db.rollback()
        finally:
            await e.dispose()

    asyncio.run(run())


def test_rebuilt_pending_case_keeps_both_plan_audits_and_version_link(registered):
    async def run():
        from app.models.learning_review_case import LearningReviewCase
        from app.services.learning_review_history import case_review_history

        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                gateway = RebuildGateway()
                gateway.values[-1] = sequence("needs_human")[-1]
                result = await run_planned_operation(
                    db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=gateway
                )
                assert result["status"] == "awaiting_human"
                case = await db.scalar(
                    select(LearningReviewCase).where(LearningReviewCase.operation_id == oid)
                )
                view = await case_review_history(db, case)
                assert (
                    len(view["plan_checks"])
                    == len(view["plan_rebuild_events"])
                    == len(view["plan_history"])
                    == 2
                )
                assert view["plan_rebuild_events"][1]["new_plan_id"] == str(case.plan_id)
                assert [p["is_case_plan"] for p in view["plan_history"]] == [False, True]
                assert all(r["plan_id"] == str(case.plan_id) for r in view["candidate_history"])
                assert view["review_history"]["complete"]
        finally:
            await e.dispose()

    asyncio.run(run())
