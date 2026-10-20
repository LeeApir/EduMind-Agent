"""Actual isolated PG/CLI history, two corrections, privacy and absence of writes."""

import asyncio
import importlib.util
import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_hybrid_learning_publication import flow_inputs, fresh_operation, sequence
from test_hybrid_resource_review import ReviewGateway, answer
from test_learning_review_cases import case_fixture
from test_learning_review_cli import config

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import GeneratedResource, LearningOperation
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_publication import LearningPublication
from app.models.learning_review import LearningReviewRecord
from app.models.learning_review_case import LearningReviewCase, LearningReviewDecision
from app.services.learning_contract import LearningContractError
from app.services.learning_review_history import case_review_history
from app.services.planned_learning_flow import run_planned_operation

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="actual isolated PG required")
ROOT = Path(__file__).resolve().parents[2]


def cli_module():
    spec = importlib.util.spec_from_file_location(
        "review_history_cli", ROOT / "scripts/review_learning_cases.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def corrected_case(db):
    uid, oid = await fresh_operation(db)
    values = sequence("needs_human")
    first = deepcopy(values[1])
    first["content"]["markdown"] += "\nSynthetic revision one."
    second = deepcopy(first)
    second["content"]["markdown"] += "\nSynthetic revision two."
    gateway = ReviewGateway(
        [values[0], values[1], answer("revise"), first, answer("revise"), second, *values[2:]]
    )
    result = await run_planned_operation(
        db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=gateway
    )
    assert result["status"] == "awaiting_human" and len(gateway.requests) == 13
    case = await db.scalar(select(LearningReviewCase).where(LearningReviewCase.operation_id == oid))
    return case, gateway


async def database_state(db):
    models = [
        User,
        LearningOperation,
        GeneratedResource,
        LearningReviewRecord,
        LearningReviewCase,
        LearningReviewDecision,
        LearningPublication,
        LearningPlanVersion,
    ]
    counts = {m.__tablename__: await db.scalar(select(func.count()).select_from(m)) for m in models}
    operations = (
        await db.execute(
            select(
                LearningOperation.id,
                LearningOperation.status,
                LearningOperation.generation_call_count,
            )
        )
    ).all()
    cases = (
        await db.execute(
            select(
                LearningReviewCase.id,
                LearningReviewCase.state,
                LearningReviewCase.case_digest,
                LearningReviewCase.updated_at,
            )
        )
    ).all()
    return (
        counts,
        sorted(tuple(str(x) for x in r) for r in operations),
        sorted(tuple(str(x) for x in r) for r in cases),
    )


def test_cli_full_history_two_corrections_scope_and_private_readonly_export(tmp_path, monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    monkeypatch.setenv("EDUMIND_DATABASE_URL", URL)
    monkeypatch.setenv("EDUMIND_REVIEWER_CONFIG", str(config(tmp_path)))
    cli = cli_module()

    async def exercise():
        engine = create_database_engine(URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as db:
                case, gateway = await corrected_case(db)
                cid = case.id
                old_operation = case.operation_id
                old_final = list(case.payload["review_ids"])
                # Same owner/unit/plan, DIFFERENT operation must not pollute the old history.
                plan = await db.get(LearningPlanVersion, case.plan_id)
                op = LearningOperation(
                    user_id=case.user_id,
                    learning_unit_id=case.learning_unit_id,
                    idempotency_key=str(uuid4()),
                    request_digest="0" * 64,
                    goal="synthetic stack",
                    preferred_language="C",
                )
                db.add(op)
                await db.commit()
                await run_planned_operation(
                    db,
                    owner_id=case.user_id,
                    operation_id=op.id,
                    inputs=flow_inputs(),
                    gateway=ReviewGateway(sequence("needs_human")[1:]),
                    reuse_plan=plan,
                )
                # Another owner is excluded too.
                await corrected_case(db)
                await db.commit()
                baseline = await database_state(db)
            args = ["show", str(cid)]
            summary = await cli.run(cli.parser().parse_args(args))
            assert (
                "payload" not in summary
                and "automatic_reviews" not in summary
                and "candidate_history" not in summary
            )
            assert summary["state"] == "invalidated"  # History remains inspectable, not approvable.
            full = await cli.run(cli.parser().parse_args(args + ["--body"]))
            assert len(full["plan_checks"]) == 1
            assert full["plan_checks"][0]["binding"]["operation_id"] == str(old_operation)
            history = full["review_history"]
            assert history["complete"] and history["issues"] == []
            assert history["scope"]["operation_id"] == str(old_operation)
            assert history["final_review_ids"] == old_final
            assert len(full["automatic_reviews"]) == len(history["entries"]) == 6
            assert sum(r["is_final_for_case"] for r in history["entries"]) == 4
            assert all(
                r["binding"]["operation_id"] == str(old_operation)
                for r in full["automatic_reviews"]
            )
            assert [r["result"]["verdict"] for r in full["automatic_reviews"]][:3] == [
                "revise",
                "revise",
                "pass",
            ]
            assert len(full["candidate_history"]) == 5
            explanations = [r for r in full["candidate_history"] if r["role"] == "explanation"]
            assert [r["scene_version"] for r in explanations] == [1, 2, 3]
            assert [r["is_final_for_case"] for r in explanations] == [False, False, True]
            assert len({r["content_digest"] for r in explanations}) == 3
            assert "Synthetic revision one" in explanations[1]["content"]["markdown"]
            assert "Synthetic revision two" in explanations[2]["content"]["markdown"]
            links = full["candidate_revisions"]
            assert len(links) == 2 and all(x["content_changed"] for x in links)
            assert links[0]["after_resource_id"] == links[1]["before_resource_id"]
            assert links[0]["before_review_ids"] and links[1]["after_review_ids"]
            again = await cli.run(cli.parser().parse_args(args + ["--body"]))
            assert full == again  # Deterministic display, including historical/final marker.
            target = tmp_path / "private-case.json"
            await cli.run(cli.parser().parse_args(args + ["--export", str(target)]))
            assert target.stat().st_mode & 0o777 == 0o600
            assert json.loads(target.read_text()) == full
            with pytest.raises(LearningContractError, match="CASE_EXPORT_FAILED"):
                await cli.run(cli.parser().parse_args(args + ["--export", str(target)]))
            async with factory() as db:
                assert await database_state(db) == baseline
            assert len(gateway.requests) == 13
            monkeypatch.delenv("EDUMIND_REVIEWER_CONFIG")
            with pytest.raises(LearningContractError, match="MAINTAINER_NOT_AUTHORIZED"):
                await cli.run(cli.parser().parse_args(args + ["--body"]))
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_missing_candidates_are_explicit_not_silently_complete():
    async def exercise():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                *_, case = await case_fixture(
                    db
                )  # Legacy synthetic fixture persists no candidates.
                await db.commit()
                view = await case_review_history(db, case)
                assert len(view["automatic_reviews"]) == 4
                assert view["candidate_history"] == [] and not view["review_history"]["complete"]
                issue = next(
                    i for i in view["review_history"]["issues"] if i["code"] == "CANDIDATES_MISSING"
                )
                assert len(issue["ids"]) == 3 and case.state == "pending"
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_projection_never_autoflushes_pending_caller_changes(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def exercise():
        engine = create_database_engine(URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as db:
                case, _ = await corrected_case(db)
                pending = User(id=uuid4(), is_guest=True)
                db.add(pending)
                await case_review_history(db, case)
                assert pending in db.new
                async with factory() as other:
                    assert await other.get(User, pending.id) is None
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
