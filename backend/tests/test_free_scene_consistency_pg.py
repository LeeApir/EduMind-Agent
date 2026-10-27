"""Actual PG: same candidate gets an append-only advisory, not a semantic rejection."""

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate
from test_free_scene_consistency import FIXTURE
from test_free_scene_generation import response
from test_free_scene_validation import stored_candidate
from test_p15_split_provider import only_pg_network as only_pg_network

from app.models.auth import User
from app.models.free_course_quality import FreeCourseQualityDecision
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.models.free_scene_validation import FreeSceneValidation
from app.services import free_scene_validation as validation
from app.services.free_course_snapshots import SnapshotError

ROOT = Path(__file__).resolve().parents[2]


def legacy_validator(tmp_path):
    source = subprocess.run(
        ["git", "show", "97130f5:backend/app/services/free_scene_validation.py"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    path = tmp_path / "legacy_validation.py"
    path.write_bytes(source)
    name = "edumind_actual_validation_v2"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    assert module.RULE_VERSION == "free-scene-hard-gate-v2"
    return module


def test_advisory_is_private_bound_append_only_and_never_confirms_a_quality_decision(tmp_path):
    old = legacy_validator(tmp_path)
    example = json.loads(FIXTURE.read_bytes())["raw"]
    raw = response()
    raw["blocks"][0]["markdown"] = example["blocks"][2]["markdown"]
    raw["blocks"][1]["source"] = example["blocks"][1]["source"]
    raw["blocks"][2]["items"] = example["blocks"][3]["items"]
    original = deepcopy(raw)

    async def run(sessions):
        owner, other = uuid4(), uuid4()
        try:
            async with sessions() as db:
                db.add_all([User(id=owner, is_guest=True), User(id=other, is_guest=True)])
                await db.commit()
                repo, cid, fence, rid, _, _ = await stored_candidate(db, owner, raw)
                first = await old.validate_candidate(db, owner, cid, fence, result_id=rid)
                assert first["state"] == "accepted"
                await db.commit()
                second = await validation.validate_candidate(db, owner, cid, fence, result_id=rid)
                assert second == await validation.validate_candidate(
                    db, owner, cid, fence, result_id=rid
                )
                assert (
                    second["state"] == "accepted"
                    and second["rule_version"] == "free-scene-hard-gate-v3"
                )
                assert first["validation_id"] != second["validation_id"]
                with pytest.raises(SnapshotError, match="NOT_FOUND"):
                    await validation.validate_candidate(db, other, cid, fence, result_id=rid)
                await db.commit()
                rows = (
                    await db.scalars(
                        select(FreeSceneValidation).where(
                            FreeSceneValidation.generation_result_id == rid
                        )
                    )
                ).all()
                assert len(rows) == 2
                previous = next(r for r in rows if r.rule_version == "free-scene-hard-gate-v2")
                current = next(r for r in rows if r.rule_version == "free-scene-hard-gate-v3")
                assert previous.findings == []
                assert previous.raw_digest == current.raw_digest
                assert previous.cleaned_digest == current.cleaned_digest
                assert previous.cleaned_json == current.cleaned_json
                advisory = current.findings[0]["report"]
                assert (
                    advisory["status"] == "needs_review"
                    and not advisory["semantic_correctness_verified"]
                )
                assert {"LOCAL_POINTER_CALLER_CLAIM", "QUESTION_RETURN_CONVENTION"} <= {
                    f["code"] for f in advisory["findings"]
                }
                assert (await db.get(FreeSceneGenerationResult, rid)).response_json == original
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
                                {"i": row.id},
                            )
        finally:
            async with sessions() as db, db.begin():
                await db.execute(
                    text("DELETE FROM users WHERE id IN (:a,:b)"), dict(a=owner, b=other)
                )

    dbwork(run)
    assert raw == original
