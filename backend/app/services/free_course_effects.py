"""Atomic exact-version attestation/contribution invalidation before head publication."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.free_course import FreeCourseSceneVersion
from app.models.free_course_answers import FreeCourseExerciseVersion
from app.services.free_course_evidence import revoke_exercises
from app.services.free_course_snapshots import canonical, digest


async def replacement_effects(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    before: dict[str, Any],
    after: dict[str, Any],
    changed: set[str],
) -> None:
    # Compare actual group/rule/context/dependency/association bytes; never the instruction text.
    newer = {s["scene_id"]: s for s in after["scenes"]}
    invalid = []
    for item in before["scenes"]:
        if item["scene_version_id"] is None:
            continue
        exercises = (
            await db.scalars(
                select(FreeCourseExerciseVersion).where(
                    FreeCourseExerciseVersion.user_id == owner,
                    FreeCourseExerciseVersion.course_id == cid,
                    FreeCourseExerciseVersion.scene_version_id == UUID(item["scene_version_id"]),
                )
            )
        ).all()
        if not exercises:
            continue
        replacement = newer.get(item["scene_id"])
        sv = (
            await db.get(FreeCourseSceneVersion, UUID(replacement["scene_version_id"]))
            if replacement and replacement["scene_version_id"]
            else None
        )
        for e in exercises:
            block = (
                next(
                    (
                        b
                        for b in cast(list[dict[str, Any]], sv.content_json["blocks"])
                        if b.get("exercise_key") == e.content_json["exercise_key"]
                    ),
                    None,
                )
                if sv
                else None
            )
            context = (
                digest(
                    "exercise-context-v1",
                    content=sv.content_json,
                    actions=sv.actions_json,
                    dependencies=sv.dependency_bindings,
                )
                if sv
                else None
            )
            if (
                block is None
                or canonical(block) != canonical(e.content_json)
                or context != e.context_digest
                or canonical(before["node_links"]) != canonical(after["node_links"])
            ):
                invalid.append(e)
    await revoke_exercises(
        db,
        owner,
        cid,
        invalid,
        dict(
            kind="content_replacement",
            before=before.get("id"),
            after=after.get("id"),
            changed_scene_ids=sorted(changed),
        ),
    )


async def quality_effects(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    decision_id: UUID,
    targets: list[dict[str, Any]],
    action: str,
) -> None:
    if action != "confirm_defect":
        return  # Corrections/restores never revive old contributions.
    exercises: list[FreeCourseExerciseVersion] = []
    for t in targets:
        rows = (
            await db.scalars(
                select(FreeCourseExerciseVersion).where(
                    FreeCourseExerciseVersion.user_id == owner,
                    FreeCourseExerciseVersion.course_id == cid,
                    FreeCourseExerciseVersion.scene_version_id == UUID(t["scene_version_id"]),
                )
            )
        ).all()
        exercises.extend(e for e in rows if t["scope"] == "scene" or t["anchor_id"] == e.anchor_id)
    await revoke_exercises(
        db, owner, cid, exercises, dict(kind="confirmed_defect", decision_id=str(decision_id))
    )
