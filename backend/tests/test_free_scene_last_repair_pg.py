"""Real PG: historical v3 + historical v1 advice coexist with current v4 facts."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate
from test_free_scene_generation import response
from test_free_scene_last_repair import FIXTURE
from test_free_scene_validation import stored_candidate
from test_p15_split_provider import only_pg_network as only_pg_network

from app.models.auth import User
from app.models.free_course_quality import FreeCourseQualityDecision
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.models.free_scene_validation import FreeSceneValidation
from app.services import free_scene_validation as current
from app.services.free_course_snapshots import SnapshotError

ROOT = Path(__file__).resolve().parents[2]


def historical(tmp_path, filename):
    code = subprocess.run(
        ["git", "show", "6e1aff8:backend/app/services/" + filename + ".py"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    path = tmp_path / (filename + ".py")
    path.write_bytes(code)
    name = "edumind_t064_historical_" + filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_exact_old_advice_is_preserved_with_new_cycle_finding_and_no_quality_rights(tmp_path):
    old_advice = historical(tmp_path, "free_scene_consistency")
    old = historical(tmp_path, "free_scene_validation")
    assert (
        old_advice.VERSION == "free-scene-consistency-v1"
        and old.RULE_VERSION == "free-scene-hard-gate-v3"
    )
    old.check_consistency = old_advice.check_consistency
    fixture = json.loads(FIXTURE.read_bytes())["raw"]
    raw = response()
    raw["blocks"][0]["markdown"] = fixture["blocks"][0]["markdown"]
    raw["blocks"][1]["source"] = fixture["blocks"][1]["source"]
    raw["blocks"][2]["items"] = fixture["blocks"][3]["items"]

    async def run(sessions):
        owner, other = uuid4(), uuid4()
        try:
            async with sessions() as db:
                db.add_all([User(id=owner, is_guest=True), User(id=other, is_guest=True)])
                await db.commit()
                repo, cid, fence, rid, _, _ = await stored_candidate(db, owner, raw)
                first = await old.validate_candidate(db, owner, cid, fence, result_id=rid)
                await db.commit()
                second = await current.validate_candidate(db, owner, cid, fence, result_id=rid)
                assert second == await current.validate_candidate(
                    db, owner, cid, fence, result_id=rid
                )
                assert first["validation_id"] != second["validation_id"]
                assert first["state"] == second["state"] == "accepted"
                with pytest.raises(SnapshotError, match="NOT_FOUND"):
                    await current.validate_candidate(db, other, cid, fence, result_id=rid)
                await db.commit()
                rows = (
                    await db.scalars(
                        select(FreeSceneValidation).where(
                            FreeSceneValidation.generation_result_id == rid
                        )
                    )
                ).all()
                assert len(rows) == 2
                previous = next(r for r in rows if r.rule_version == "free-scene-hard-gate-v3")
                newer = next(r for r in rows if r.rule_version == "free-scene-hard-gate-v4")
                assert len(previous.findings[0]["report"]["findings"]) == 4
                assert all(
                    f["code"] == "QUESTION_RETURN_CONVENTION"
                    for f in previous.findings[0]["report"]["findings"]
                )
                findings = newer.findings[0]["report"]["findings"]
                assert (
                    len(findings) == 1 and findings[0]["code"] == "CYCLE_FINITE_SEQUENCE_CONFLICT"
                )
                assert (
                    not findings[0]["confirmed"]
                    and not newer.findings[0]["report"]["semantic_correctness_verified"]
                )
                assert previous.raw_digest == newer.raw_digest
                assert (
                    previous.cleaned_digest == newer.cleaned_digest
                    and previous.cleaned_json == newer.cleaned_json
                )
                assert (await db.get(FreeSceneGenerationResult, rid)).response_json == raw
                assert (await repo.get_course(cid))["head_version"] == 1
                assert not (
                    await db.scalars(
                        select(FreeCourseQualityDecision).where(
                            FreeCourseQualityDecision.course_id == cid
                        )
                    )
                ).all()
                for row in rows:
                    with pytest.raises(DBAPIError):
                        async with db.begin_nested():
                            await db.execute(
                                text(
                                    "UPDATE free_course_scene_validations "
                                    "SET findings='[]'::jsonb WHERE id=:i"
                                ),
                                dict(i=row.id),
                            )
        finally:
            async with sessions() as db, db.begin():
                await db.execute(
                    text("DELETE FROM users WHERE id IN (:a,:b)"), dict(a=owner, b=other)
                )

    dbwork(run)
