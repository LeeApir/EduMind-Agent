"""Real isolated PG: current validation preserves v1 cleaning facts and raw candidates."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate
from test_free_scene_generation import response
from test_free_scene_validation import stored_candidate
from test_p15_split_provider import only_pg_network as only_pg_network

from app.models.auth import User
from app.models.free_course import FreeCourseSceneVersion
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.models.free_scene_validation import FreeSceneValidation
from app.services import free_scene_validation as validation
from app.services.free_course_snapshots import SnapshotError


def test_rule_upgrade_keeps_old_facts_and_original_code_without_publishing(
    monkeypatch, record_testsuite_property
):
    async def run(sessions):
        owner = uuid4()
        other = uuid4()
        try:
            async with sessions() as db:
                db.add_all([User(id=owner, is_guest=True), User(id=other, is_guest=True)])
                await db.commit()
                raw = response()
                raw["blocks"][0]["markdown"] = (
                    '```c\n#include <stdio.h>\nint scores[6];\nprintf("%d\\n", scores[3]);\n```'
                )
                _, cid, fence, rid, _, _ = await stored_candidate(db, owner, raw)
                with monkeypatch.context() as old:
                    old.setattr(validation, "RULE_VERSION", "free-scene-hard-gate-v1")
                    old.setattr(validation, "clean_code_markdown", validation.clean_markdown)
                    first = await validation.validate_candidate(
                        db, owner, cid, fence, result_id=rid
                    )
                    await db.commit()
                old_json = deepcopy(first["cleaned"])
                assert r"scores\[6\]" in old_json["content"]["blocks"][0]["markdown"]
                with pytest.raises(SnapshotError, match="NOT_FOUND"):
                    await validation.validate_candidate(db, other, cid, fence, result_id=rid)
                second = await validation.validate_candidate(db, owner, cid, fence, result_id=rid)
                replay = await validation.validate_candidate(db, owner, cid, fence, result_id=rid)
                assert second == replay and first["validation_id"] != second["validation_id"]
                assert second["rule_version"] == "free-scene-hard-gate-v4"
                cleaned = second["cleaned"]["content"]["blocks"][0]["markdown"]
                assert "int scores[6];" in cleaned and "#include <stdio.h>" in cleaned
                assert r'printf("%d\n", scores[3]);' in cleaned
                assert r"scores\[6\]" not in cleaned
                assert first["cleaned_digest"] != second["cleaned_digest"]
                await db.commit()
            async with sessions() as db:
                rows = (
                    await db.scalars(
                        select(FreeSceneValidation).where(
                            FreeSceneValidation.generation_result_id == rid
                        )
                    )
                ).all()
                assert len(rows) == 2 and {r.rule_version for r in rows} == {
                    "free-scene-hard-gate-v1",
                    "free-scene-hard-gate-v4",
                }
                previous = next(r for r in rows if r.rule_version == "free-scene-hard-gate-v1")
                assert (
                    previous.cleaned_json == old_json
                    and previous.raw_digest
                    == next(r for r in rows if r.rule_version == second["rule_version"]).raw_digest
                )
                assert (await db.get(FreeSceneGenerationResult, rid)).response_json == raw
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(FreeCourseSceneVersion)
                        .where(FreeCourseSceneVersion.course_id == cid)
                    )
                    == 2
                )
                for row in rows:
                    with pytest.raises(DBAPIError):
                        async with db.begin_nested():
                            await db.execute(
                                text(
                                    "UPDATE free_course_scene_validations "
                                "SET state='rejected' WHERE id=:i"
                                ),
                                dict(i=row.id),
                            )
                record_testsuite_property("v1_validation_preserved", first["validation_id"])
                record_testsuite_property("current_validation_appended", second["validation_id"])
        finally:
            async with sessions() as db, db.begin():
                await db.execute(
                    text("DELETE FROM users WHERE id IN (:a,:b)"), dict(a=owner, b=other)
                )

    dbwork(run)
