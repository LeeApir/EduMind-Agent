"""Actual isolated PG evidence integrity; synthetic records only, no model calls."""

import asyncio
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from om_fixtures import plan_fixture
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.learning_publication import LearningPublication
from app.models.learning_review_case import LearningReviewDecision
from app.models.plan_check import PlanCheck, PlanRebuildEvent
from app.services.learning_contract import LearningContractError
from app.services.plan_check import (
    owned_plan_check,
    save_plan_check,
    save_plan_resolution,
    save_rebuild_event,
)

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="actual isolated PostgreSQL required")
SYNTHETIC = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "docs/acceptance/phase-1-plan-correction-proposal-r01/synthetic-record.json"
    ).read_text()
)


def bound_record(plan, op):
    x = deepcopy(SYNTHETIC)
    x["check_id"] = str(uuid4())
    x["binding"] = dict(
        owner_id=str(plan.user_id),
        unit_id=str(plan.learning_unit_id),
        operation_id=str(op.id),
        plan_id=str(plan.id),
        plan_version=plan.version,
        plan_digest=plan.plan_digest,
        input_digest=plan.input_digest,
        reference_digest=plan.references_digest,
        policy_digest=plan.policy_digest,
    )
    # Synthetic snapshots use a real text field, not a neighboring/derived fact.
    x["anchor_catalog"][0].update(
        source_digest=plan.input_digest,
        json_pointer="/metadata/goal",
        start_utf8=0,
        end_utf8=len(plan.input_snapshot["metadata"]["goal"].encode()),
    )
    x["anchor_catalog"][1].update(
        source_digest=plan.plan_digest,
        json_pointer="/goal",
        start_utf8=0,
        end_utf8=len(plan.plan_json["goal"].encode()),
    )
    return x


def resolution(row):
    return dict(
        schema_version="plan-issue-resolution-v1",
        resolution_id=str(uuid4()),
        check_id=str(row.id),
        expected_check_digest=row.record_digest,
        reviewer_id="synthetic",
        identity_source="test-only",
        kind="new_request_needed",
        reason="Synthetic persistence test, no actual course decision.",
        idempotency_key=str(uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def test_persist_isolated_immutable_history_and_no_publication():
    async def run():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                _, _, op, plan = await plan_fixture(db)
                row = await save_plan_check(db, bound_record(plan, op))
                r = resolution(row)
                note = await save_plan_resolution(
                    db,
                    owner_id=plan.user_id,
                    value=r,
                    trusted_reviewer_id="synthetic",
                    trusted_identity_source="test-only",
                )
                await db.commit()
                assert (
                    await owned_plan_check(db, owner_id=plan.user_id, check_id=row.id)
                ).record == row.record
                with pytest.raises(LearningContractError, match="PLAN_CHECK_NOT_FOUND"):
                    await owned_plan_check(db, owner_id=uuid4(), check_id=row.id)
                for table, rid in [
                    ("learning_plan_checks", row.id),
                    ("learning_plan_check_resolutions", note.id),
                ]:
                    for sql in [
                        f"UPDATE {table} SET record=record WHERE id=:id",
                        f"DELETE FROM {table} WHERE id=:id",
                    ]:
                        with pytest.raises(DBAPIError):
                            async with db.begin_nested():
                                await db.execute(text(sql), dict(id=rid))
                # Unique stage forbids a second report, even a different check UUID.
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await save_plan_check(db, bound_record(plan, op))
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        r["resolution_id"] = str(uuid4())
                        await save_plan_resolution(
                            db,
                            owner_id=plan.user_id,
                            value=r,
                            trusted_reviewer_id="synthetic",
                            trusted_identity_source="test-only",
                        )
                # DB owner composite FK still guards callers bypassing the service.
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        db.add(
                            PlanCheck(
                                id=uuid4(),
                                user_id=uuid4(),
                                learning_unit_id=plan.learning_unit_id,
                                operation_id=op.id,
                                plan_id=plan.id,
                                stage="plan_recheck",
                                record_digest="0" * 64,
                                record={},
                            )
                        )
                        await db.flush()
                assert (
                    await db.scalar(select(func.count()).select_from(LearningReviewDecision)) == 0
                )
                assert await db.scalar(select(func.count()).select_from(LearningPublication)) == 0
                # Old human case construction remains compatible on the same migrated DB.
                from test_learning_review_cases import case_fixture

                *_, case = await case_fixture(db)
                assert case.state == "pending"
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "snapshot",
        "pointer",
        "range",
        "utf8",
        "model_authority",
        "unsafe_route",
        "identity",
        "digest",
        "approve",
    ],
)
def test_binding_anchor_and_authority_rejections(mutation):
    async def run():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                _, _, op, plan = await plan_fixture(db)
                x = bound_record(plan, op)
                if mutation in ["identity", "digest", "approve"]:
                    row = await save_plan_check(db, x)
                    r = resolution(row)
                    if mutation == "identity":
                        r["reviewer_id"] = "forged"
                    elif mutation == "digest":
                        r["expected_check_digest"] = "0" * 64
                    else:
                        r["kind"] = "approve_plan"
                    with pytest.raises(LearningContractError):
                        await save_plan_resolution(
                            db,
                            owner_id=plan.user_id,
                            value=r,
                            trusted_reviewer_id="synthetic",
                            trusted_identity_source="test-only",
                        )
                else:
                    if mutation == "owner":
                        x["binding"]["owner_id"] = str(uuid4())
                    elif mutation == "snapshot":
                        plan.input_snapshot = {**plan.input_snapshot, "tampered": True}
                    elif mutation == "pointer":
                        x["anchor_catalog"][1]["json_pointer"] = "/missing"
                    elif mutation == "range":
                        x["anchor_catalog"][0]["end_utf8"] = 999999
                    elif mutation == "utf8":
                        # A byte offset inside a Chinese character is not a valid citation.
                        a = x["anchor_catalog"][0]
                        raw = plan.input_snapshot["metadata"]["goal"].encode()
                        index = next((i for i, b in enumerate(raw) if b >= 0xE0), None)
                        assert index is not None
                        a["start_utf8"] = index + 1
                    elif mutation == "model_authority":
                        x["model_result"]["repair_allowed"] = True
                    elif mutation == "unsafe_route":
                        x["server_assessment"]["route"] = "rebuild_once"
                    with pytest.raises(LearningContractError):
                        await save_plan_check(db, x)
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_event_storage_cannot_authorize_rebuild_and_db_terminal_unique():
    async def run():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                _, _, op, plan = await plan_fixture(db)
                row = await save_plan_check(db, bound_record(plan, op))
                event = dict(
                    schema_version="plan-rebuild-event-v1",
                    event_id=str(uuid4()),
                    operation_id=str(op.id),
                    event_type="reserved",
                    attempt=1,
                    prior_plan_id=str(plan.id),
                    prior_plan_digest=plan.plan_digest,
                    trigger_check_id=str(row.id),
                    proof_ids=[str(uuid4())],
                    new_plan_id=None,
                    new_plan_digest=None,
                    input_digest=plan.input_digest,
                    reference_digest=plan.references_digest,
                    policy_digest=plan.policy_digest,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                with pytest.raises(LearningContractError, match="PLAN_REBUILD_NOT_AUTHORIZED"):
                    await save_rebuild_event(db, owner_id=plan.user_id, record=event)

                # Direct synthetic DB rows exercise constraints, not a supported repair path.
                def raw(kind):
                    return PlanRebuildEvent(
                        id=uuid4(),
                        user_id=plan.user_id,
                        learning_unit_id=plan.learning_unit_id,
                        operation_id=op.id,
                        plan_id=plan.id,
                        check_id=row.id,
                        event_type=kind,
                        record_digest="0" * 64,
                        record={},
                    )

                reserved = raw("reserved")
                db.add(reserved)
                await db.flush()
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        db.add(raw("reserved"))
                        await db.flush()
                db.add(raw("failed"))
                await db.flush()
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        db.add(raw("completed"))
                        await db.flush()
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await db.execute(
                            text("DELETE FROM learning_plan_rebuild_events WHERE id=:id"),
                            dict(id=reserved.id),
                        )
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(run())
