"""Read-only development DB check of original failed course and reviewed private child."""

import asyncio
import json
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from sqlalchemy import func, select, text  # noqa: E402
from app.models.free_course_planning import FreeCoursePlanningResult  # noqa: E402
from app.models.free_scene_generation import FreeSceneGenerationResult  # noqa: E402
from app.models.free_course_writes import FreeCourseOperation  # noqa: E402
from app.services.free_course_snapshots import SnapshotRepository  # noqa: E402
from app.services.head_course_evidence_publication import validate_publication  # noqa: E402
from scripts.head_course_goal import database  # noqa: E402

HERE = Path(__file__).resolve().parent


async def inspect(db):
    await db.execute(text("SET TRANSACTION READ ONLY"))
    owner = UUID("0b1b71df-9b00-470e-abc4-ae41aeb20cf9")
    cid = UUID("6be90c82-adfd-408d-82b6-32125db0dcbf")
    repo = SnapshotRepository(db, owner)
    original = await repo.get_course(cid)
    op = await db.scalar(
        select(FreeCourseOperation).where(
            FreeCourseOperation.id == UUID("ecb65468-da85-4772-8a5d-b7f1bb5e8fa1"),
            FreeCourseOperation.user_id == owner,
            FreeCourseOperation.course_id == cid,
        )
    )
    counts = {}
    for label, model in (
        ("planning_results", FreeCoursePlanningResult),
        ("scene_generation_results", FreeSceneGenerationResult),
    ):
        counts[label] = await db.scalar(
            select(func.count()).select_from(model).where(model.course_id == cid)
        )
    assert (
        original["head_version"] == 1
        and op.state == "failed"
        and op.reason_code == "TEACHING_REVIEW_FAILED"
    )
    assert counts == dict(planning_results=1, scene_generation_results=0)
    binding = json.loads((HERE / "app-binding.json").read_text())
    child_id = UUID(binding["course_id"])
    child_repo = SnapshotRepository(db, UUID("c1b724d1-2bb5-49ad-aa8c-f361704e9872"))
    child = await child_repo.get_course(child_id)
    assert (
        child["head_version"] == 2
        and child["original_goal"] == original["original_goal"]
    )
    row = (
        await db.scalars(
            select(FreeSceneGenerationResult).where(
                FreeSceneGenerationResult.course_id == child_id
            )
        )
    ).one()
    assert (
        validate_publication(row, row.input_snapshot["inputs"])["state"] == "accepted"
    )
    child_op = await db.scalar(
        select(FreeCourseOperation).where(
            FreeCourseOperation.id == UUID(binding["operation_id"]),
            FreeCourseOperation.course_id == child_id,
        )
    )
    assert child_op.state == "succeeded"
    result = dict(
        original_course=original,
        original_operation=dict(state=op.state, reason_code=op.reason_code),
        original_counts=counts,
        child_course=child,
        child_operation_state=child_op.state,
        full_stored_revision_binding="accepted",
        provider_calls=0,
        database_writes=0,
    )
    return result


if __name__ == "__main__":
    print(json.dumps(asyncio.run(database(inspect)), ensure_ascii=False, indent=2))
