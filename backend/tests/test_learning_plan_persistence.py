"""Actual PG immutability, ownership and legacy compatibility; synthetic plan only."""

import asyncio
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import GeneratedResource, LearningOperation, LearningScene, LearningUnit
from app.services.learning_contract import LearningContractError, canonical, validate_plan
from app.services.learning_plans import save_plan

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads(
    (ROOT / "docs/acceptance/phase-1-om-redesign/contract-examples.json").read_text()
)
PLAN = SAMPLE["plan_record"]["plan"]
REFS = {r["reference_id"]: r for r in PLAN["references"]}
URL = os.getenv("EDUMIND_TEST_DATABASE_URL")


@pytest.mark.parametrize(
    "mutation", ["extra", "goal", "objectives", "reference", "size", "float", "convention"]
)
def test_plan_rejects_invalid_contract(mutation: str) -> None:
    p = deepcopy(PLAN)
    if mutation == "extra":
        p["extra"] = True
    if mutation == "goal":
        del p["goal"]
    if mutation == "objectives":
        p["scenes"][0]["objective_ids"] = ["unknown"]
    if mutation == "reference":
        p["references"][0]["digest"] = "1" * 64
    if mutation == "size":
        p["goal"] = "文" * 3000
    if mutation == "float":
        p["conventions"]["capacity"] = 4.0
    if mutation == "convention":
        p["conventions"]["capacity"] = None
    with pytest.raises(LearningContractError):
        validate_plan(p, node_ids={"stack"}, references=REFS)


def test_contract_schema_matches_approved_bytes() -> None:
    assert (ROOT / "backend/app/services/learning_contract.schema.json").read_bytes() == (
        ROOT / "docs/acceptance/phase-1-om-redesign/minimum-contract.schema.json"
    ).read_bytes()
    assert canonical({"b": 2, "a": "文"}) == b'{"a":"\xe6\x96\x87","b":2}'


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
def test_plan_persistence_and_database_guards() -> None:
    assert URL

    async def exercise() -> None:
        engine = create_database_engine(URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as db:
                user, other = User(is_guest=True), User(is_guest=True)
                db.add_all([user, other])
                await db.flush()
                unit = LearningUnit(user_id=user.id, title="synthetic stack")
                db.add(unit)
                await db.flush()
                op = LearningOperation(
                    user_id=user.id,
                    learning_unit_id=unit.id,
                    idempotency_key=str(unit.id),
                    request_digest="0" * 64,
                    goal="stack",
                    preferred_language="C",
                )
                db.add(op)
                await db.flush()
                plan = await save_plan(
                    db,
                    owner_id=user.id,
                    unit_id=unit.id,
                    operation_id=op.id,
                    plan=PLAN,
                    input_snapshot={"goal": "stack"},
                    references=REFS,
                    node_ids={"stack"},
                    policy_version="hybrid-review-v1",
                    policy={},
                )
                scene = LearningScene(
                    learning_unit_id=unit.id,
                    plan_id=plan.id,
                    dependency_digest="0" * 64,
                    scene_key="explanation",
                    scene_type="explanation",
                    scene_order=1,
                    version=1,
                )
                db.add(scene)
                await db.flush()
                resource = GeneratedResource(
                    user_id=user.id,
                    learning_unit_id=unit.id,
                    scene_id=scene.id,
                    plan_id=plan.id,
                    content_digest="0" * 64,
                    dependency_digest="0" * 64,
                    resource_type="explanation",
                    content={"markdown": "private candidate"},
                )
                db.add(resource)
                await db.flush()
                for sql, params in [
                    ("UPDATE learning_plan_versions SET version=2 WHERE id=:id", {"id": plan.id}),
                    ("UPDATE learning_scenes SET scene_key='intro' WHERE id=:id", {"id": scene.id}),
                    (
                        "UPDATE generated_resources SET content='{}'::jsonb WHERE id=:id",
                        {"id": resource.id},
                    ),
                ]:
                    with pytest.raises(DBAPIError):
                        async with db.begin_nested():
                            await db.execute(text(sql), params)
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        db.add(
                            GeneratedResource(
                                user_id=other.id,
                                learning_unit_id=unit.id,
                                scene_id=scene.id,
                                plan_id=plan.id,
                                content_digest="0" * 64,
                                dependency_digest="0" * 64,
                                resource_type="code",
                                content={},
                            )
                        )
                        await db.flush()
                legacy = LearningScene(
                    learning_unit_id=unit.id,
                    scene_key="intro",
                    scene_type="explanation",
                    scene_order=1,
                    version=1,
                )
                db.add(legacy)
                await db.commit()
                pid, sid = plan.id, legacy.id
            await engine.dispose()
            async with factory() as db:
                from app.models.learning_plan import LearningPlanVersion

                loaded = await db.get(LearningPlanVersion, pid)
                assert loaded and loaded.plan_json == PLAN
                old = await db.get(LearningScene, sid)
                assert old and old.plan_id is None and old.scene_key == "intro"
            async with factory() as db:
                before_revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
                expected_guard = "planned data prevents downgrade"
                for table, message in [
                    ("learning_publications", "publication data prevents downgrade"),
                    ("learning_review_cases", "review cases prevent downgrade"),
                    ("learning_review_records", "review data prevents downgrade"),
                ]:
                    exists = await db.scalar(text("SELECT to_regclass(:name)"), {"name": table})
                    if exists and await db.scalar(text(f"SELECT count(*) FROM {table}")):
                        expected_guard = message
                        break
                has_context = await db.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                        "WHERE table_name='learning_operations' AND column_name='teaching_context')"
                    )
                )
                if has_context and await db.scalar(
                    text(
                        "SELECT count(*) FROM learning_operations "
                        "WHERE teaching_context IS NOT NULL"
                    )
                ):
                    expected_guard = "teaching data prevents downgrade"
                # Newer append-only migrations stop first; assert the exact highest guard.
                plan_evidence = await db.scalar(text("SELECT to_regclass('learning_plan_checks')"))
                if plan_evidence and await db.scalar(
                    text("SELECT count(*) FROM learning_plan_checks")
                ):
                    expected_guard = "plan evidence prevents downgrade"
                budget_table = await db.scalar(
                    text("SELECT to_regclass('learning_generation_attempts')")
                )
                if budget_table and await db.scalar(
                    text(
                        "SELECT count(*) FROM learning_operations "
                        "WHERE generation_budget_version IS NOT NULL"
                    )
                ):
                    expected_guard = "budget evidence prevents downgrade"
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "downgrade", "0025_animation_dsl_media"],
                cwd=ROOT / "backend",
                env={**os.environ, "EDUMIND_DATABASE_URL": URL},
                capture_output=True,
                text=True,
            )
            assert result.returncode != 0
            assert expected_guard in result.stderr
            async with factory() as db:
                assert (
                    await db.scalar(text("SELECT version_num FROM alembic_version"))
                    == before_revision
                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())
