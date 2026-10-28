"""Actual isolated PG: historical failed v1 and new v2 audit coexist without rewriting."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_free_course_planning import Gateway, authorize, exercise
from test_free_course_planning import migrate_database as migrate_database
from test_free_plan_objective_contract import correct_example, original
from test_p15_split_provider import only_pg_network as only_pg_network

from app.agents import free_course_planning as current
from app.models.free_course_planning import FreeCoursePlanningResult
from app.services import free_course_planning as storage
from app.services.free_course_recovery import Recovery
from app.services.free_course_scheduler import POLICY
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository

ROOT = Path(__file__).resolve().parents[2]


def legacy(tmp_path):
    for name in ("free_course_planning.py", "free_course_planning.schema.json"):
        content = subprocess.run(
            ["git", "show", "434fcb5:backend/app/agents/" + name],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        (tmp_path / name).write_bytes(content)
    spec = importlib.util.spec_from_file_location(
        "edumind_t065_actual_v1", tmp_path / "free_course_planning.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert module.PROMPT_VERSION == "free-course-plan-v1"
    return module


def test_v1_failure_and_v2_guidance_keep_owner_idempotency_and_immutable_source(
    tmp_path, monkeypatch
):
    old = legacy(tmp_path)
    data_fixture = original()

    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo = SnapshotRepository(db, owner)
            created = await repo.create_course(
                data_fixture["inputs"]["original_goal"],
                key="policy-bound-test",
                policy_snapshot=POLICY,
            )
            cid = UUID(created["course_id"])
            fence = await repo.acquire_write_fence(cid, UUID(created["operation_id"]))
            data = await storage.load_inputs(db, owner, cid, fence.operation_id)
            await db.commit()
        first_outcome = await old.plan_once(
            Gateway(data_fixture["raw"]), data, authorize_send=authorize
        )
        assert first_outcome.state == "failed"
        async with AsyncSession(engine) as db:
            with monkeypatch.context() as legacy_context:
                legacy_context.setattr(storage, "build_request", old.build_request)
                legacy_context.setattr(storage, "PROMPT_VERSION", old.PROMPT_VERSION)
                first = await storage.persist_outcome(
                    db,
                    owner,
                    cid,
                    fence,
                    expected_head=None,
                    call_key="historical-v1",
                    inputs=data,
                    outcome=first_outcome,
                )
                await db.commit()
            with pytest.raises(SnapshotError, match="PLANNING_INPUT_MISMATCH"):
                await storage.persist_outcome(
                    db,
                    owner,
                    cid,
                    fence,
                    expected_head=None,
                    call_key="wrong-producer",
                    inputs=data,
                    outcome=first_outcome,
                )
        # A failed operation is terminal. Use the existing explicit recovery API in this
        # isolated test, rather than reusing a fenced operation or altering its state.
        previous_operation = fence.operation_id
        async with AsyncSession(engine) as db:
            with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
                await SnapshotRepository(db, owner).acquire_write_fence(cid, previous_operation)
        resumed = await Recovery(async_sessionmaker(engine, expire_on_commit=False)).start(
            owner,
            cid,
            kind="resume",
            source_operation_id=previous_operation,
            expected_head=None,
            key="explicit-test-v2-operation",
        )
        async with AsyncSession(engine) as db:
            repo = SnapshotRepository(db, owner)
            fence = await repo.acquire_write_fence(cid, UUID(resumed["operation_id"]))
            data = await storage.load_inputs(db, owner, cid, fence.operation_id)
            await db.commit()
        g = Gateway(correct_example())
        second_outcome = await current.plan_once(g, data, authorize_send=authorize)
        assert second_outcome.state == "ready"
        async with AsyncSession(engine) as db:
            second = await storage.persist_outcome(
                db,
                owner,
                cid,
                fence,
                expected_head=None,
                call_key="fresh-v2",
                inputs=data,
                outcome=second_outcome,
            )
            assert second == await storage.persist_outcome(
                db,
                owner,
                cid,
                fence,
                expected_head=None,
                call_key="fresh-v2",
                inputs=data,
                outcome=second_outcome,
            )
            with pytest.raises(SnapshotError, match="NOT_FOUND"):
                await storage.persist_outcome(
                    db,
                    other,
                    cid,
                    fence,
                    expected_head=None,
                    call_key="other-owner",
                    inputs=data,
                    outcome=second_outcome,
                )
            await db.commit()
            rows = (
                await db.scalars(
                    select(FreeCoursePlanningResult).where(
                        FreeCoursePlanningResult.course_id == cid
                    )
                )
            ).all()
            assert len(rows) == 2 and {r.prompt_version for r in rows} == {
                "free-course-plan-v1",
                "free-course-plan-v2",
            }
            previous = await db.get(FreeCoursePlanningResult, UUID(first["result_id"]))
            assert previous.state == "failed" and previous.response_json == data_fixture["raw"]
            assert previous.request_digest != next(
                r.request_digest for r in rows if r.prompt_version == "free-course-plan-v2"
            )
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] is None
            for row in rows:
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await db.execute(
                            text(
                                "UPDATE free_course_planning_results SET state='failed' WHERE id=:i"
                            ),
                            dict(i=row.id),
                        )

    exercise(action)
