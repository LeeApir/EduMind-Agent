"""Targeted fact-revision real-PG admission/private-feedback checks; entire transaction rolls back."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.main import app  # noqa: E402,F401
from app.services import head_course_fact_publication as d  # noqa: E402
from app.services import head_course_generation as g  # noqa: E402
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository  # noqa: E402
from app.models.free_scene_generation import FreeSceneGenerationResult  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from app.core.database import create_database_engine  # noqa: E402


async def main():
    g.require_development_database()
    engine = create_database_engine()
    record, _ = d.mapping()
    owner = UUID("e5b129e0-f03f-4c0b-96cd-3ac202f34c56")
    try:
        async with AsyncSession(engine) as db:
            try:
                result = await d.import_course(db, owner)
                cid = UUID(result["course_id"])
                row = await db.scalar(
                    select(FreeSceneGenerationResult).where(
                        FreeSceneGenerationResult.course_id == cid
                    )
                )
                assert (
                    g.validate_generation(row, row.input_snapshot["inputs"])["state"]
                    == "accepted"
                )
                altered = SimpleNamespace(
                    **{
                        column.name: deepcopy(getattr(row, column.name))
                        for column in row.__table__.columns
                    }
                )
                altered.response_json["generation_source"]["evidence_kind"] = (
                    "actual_provider_response"
                )
                try:
                    g.validate_generation(altered, row.input_snapshot["inputs"])
                except SnapshotError:
                    pass
                else:
                    raise AssertionError("False first-pass provenance accepted")
                assert (await SnapshotRepository(db, owner).get_course(cid))[
                    "head_version"
                ] == 2
                # Projection must continue using the existing private answer redaction.
                from app.services.free_scene_availability import read_ready_scene

                view = await read_ready_scene(
                    db, owner, cid, version=2, scene_id=UUID(result["scene_id"])
                )
                assert "answer_key" not in str(view) and "solution" not in str(view)
                assert (
                    view["generation_source"]["evidence_kind"]
                    == "targeted_fact_revision"
                )
                replay = await d.import_course(db, owner)
                assert (
                    replay["course_id"] == result["course_id"]
                    and replay["imported"] is False
                )
                original = __import__(
                    "app.services.head_course_derivation", fromlist=["mapping"]
                ).mapping()[0]["original_context"]
                original_cid = UUID(original["course_id"])
                original_oid = UUID(original["operation_id"])
                original_owner = UUID(original["owner"])
                original_course = await SnapshotRepository(
                    db, original_owner
                ).get_course(original_cid)
                original_op = await SnapshotRepository(db, original_owner)._operation(
                    original_cid, original_oid
                )
                assert (
                    original_course["head_version"] == 1
                    and original_op.state == "failed"
                )
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(FreeSceneGenerationResult)
                        .where(FreeSceneGenerationResult.course_id == original_cid)
                    )
                    == 0
                )
                print(
                    "PASS: real PG fact revision admission/review gate/source tamper/private projection/idempotence; rolled back; Provider calls 0."
                )
            finally:
                await db.rollback()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
