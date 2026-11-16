"""Publish T151 B's program-authored exercise format change in the isolated dev database."""

import asyncio
import json
import os
import sys
from copy import deepcopy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.free_course_progress import FreeCourseStep
from app.models.free_course_writes import FreeCourseOperation
from app.models.free_scene_actions import FreeScenePresentation
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.models.free_scene_validation import FreeSceneValidation
from app.services import free_scene_availability as availability
from app.services.free_course_answers import TYPED_RULE, compare_answer, ensure_exercise
from app.services.free_course_exercise_identity import exercise_identity
from app.services.free_course_quality import local_authority
from app.services.free_course_snapshots import (
    ACTIVE,
    SnapshotError,
    SnapshotRepository,
    digest,
)
from app.services.free_scene_actions import compile_presentation
from scripts.head_course_goal import raw_io_audit
from scripts.stack_goal_selection_trial import require_database

COURSE = UUID("f8750937-736e-427f-8eb3-5d60288ae314")
SOURCE_OPERATION = UUID("59aac7b5-1f71-48b4-9bbb-072698fd5342")
SOURCE_VERSION = 3
SOURCE_DIGEST = "c584df03d48a816acaf520f225d6be3f991b9f17e5cfac1f93826cc741ab861e"
RULE = "stack-b-program-exercise-format-v1"
SOURCES = {
    "normal": "b1d7441b2654037d32417ecebb2cfb3563a5eeee3d6dab4b759d8ee752fff63e",
    "rejections": "1ee82e4f9d4a831c6fd609d714eaf9ea4e48e448375e56a36dfc1e7647cff3c7",
}
INTEGER_RANGES = {
    "first_pop": "[-4,9] 范围内的",
    "final_top": "[-4,9] 范围内的",
    "full_count": "[0,3] 范围内的",
    "empty_return": "值为 0 或 1 的",
    "empty_output": "[-99,7] 范围内的",
}
QUESTIONS = {
    "normal": ["first_pop", "final_top"],
    "rejections": ["full_count", "empty_return", "empty_output", "guard_pair"],
}
FORMAT_GUIDE = (
    " 整数题格式示例：12 或 -7。负数使用半角减号，不加正号、前导零、小数点、"
    "引号、单位或解释。反馈若提示输入格式，表示该输入未参与数值比较。"
)


def revise_exercise(content, scene_key):
    blocks = [block for block in content["blocks"] if block["kind"] == "exercise"]
    if len(blocks) != 1 or blocks[0]["exercise_key"] != "stack-practice":
        raise SnapshotError("STACK_B_FORMAT_BINDING")
    block = blocks[0]
    if [q["question_id"] for q in block["items"]] != QUESTIONS[scene_key]:
        raise SnapshotError("STACK_B_FORMAT_BINDING")
    block["question"] += FORMAT_GUIDE
    for question in block["items"]:
        key = question["question_id"]
        stem, separator, _ = question["question"].rpartition("。只输入")
        if not separator or question["input_type"] != "short_text":
            raise SnapshotError("STACK_B_FORMAT_BINDING")
        if key == "guard_pair":
            instruction = "输入 A 或 B，大小写均可，不加其他文字。"
        else:
            question["input_type"] = "integer"
            instruction = f"只输入{INTEGER_RANGES[key]}一个 JSON 整数。"
        question["question"] = stem + "。" + instruction
        if compare_answer(question, question["answer_key"]) != (
            True,
            question["solution"],
        ):
            raise SnapshotError("STACK_B_FORMAT_REFERENCE")
    return block


async def publish(db):
    historical = await db.get(FreeCourseOperation, SOURCE_OPERATION)
    if (
        historical is None
        or historical.course_id != COURSE
        or historical.state != "succeeded"
    ):
        raise SnapshotError("STACK_B_FORMAT_BINDING")
    owner = historical.user_id
    repo = SnapshotRepository(db, owner)
    await repo._owner_lock()
    course = await repo._course(COURSE, lock=True)
    source = await repo.get_version(COURSE, SOURCE_VERSION)
    if source["digest"] != SOURCE_DIGEST:
        raise SnapshotError("STACK_B_FORMAT_BINDING")

    route = f"maintenance:exercise-format:{COURSE}"
    provenance = dict(
        rule=RULE,
        source_version=SOURCE_VERSION,
        source_digest=SOURCE_DIGEST,
        source_operation_id=str(SOURCE_OPERATION),
        provider_calls=0,
    )
    fingerprint = digest("program-exercise-format", **provenance)
    previous = await repo._receipt(route, RULE, fingerprint)
    if previous is not None:
        return previous
    await repo._expected(course, SOURCE_VERSION)
    active = await db.scalar(
        select(FreeCourseOperation.id).where(
            FreeCourseOperation.user_id == owner,
            FreeCourseOperation.state.in_(ACTIVE),
        )
    )
    if active is not None:
        raise SnapshotError("OPERATION_ACTIVE")

    operation = FreeCourseOperation(
        user_id=owner,
        course_id=COURSE,
        request_id=historical.request_id,
        kind="revise_scene",
        base_head_version=SOURCE_VERSION,
        state="queued",
        config_snapshot=deepcopy(historical.config_snapshot),
        policy_snapshot={"program_exercise_format": provenance},
    )
    db.add(operation)
    await db.flush()
    fence = await repo.acquire_write_fence(COURSE, operation.id)
    plan_id = UUID(source["plan_id"])
    replacements = {}
    ready_steps = []
    for item, (scene_key, expected_digest) in zip(
        source["scenes"], SOURCES.items(), strict=True
    ):
        sid = UUID(item["scene_id"])
        raw = await repo.get_scene_snapshot(COURSE, SOURCE_VERSION, sid)
        if raw["digest"] != expected_digest:
            raise SnapshotError("STACK_B_FORMAT_BINDING")
        await availability.read_ready_scene(
            db, owner, COURSE, version=SOURCE_VERSION, scene_id=sid
        )
        old_step = await db.scalar(
            select(FreeCourseStep).where(
                FreeCourseStep.user_id == owner,
                FreeCourseStep.course_id == COURSE,
                FreeCourseStep.scene_version_id == UUID(item["scene_version_id"]),
                FreeCourseStep.state == "ready",
            )
        )
        if (
            old_step is None
            or old_step.step_key != f"scene:{scene_key}"
            or old_step.operation_id != SOURCE_OPERATION
        ):
            raise SnapshotError("STACK_B_FORMAT_BINDING")
        old_view = await db.get(FreeScenePresentation, old_step.presentation_id)
        if old_view is None or old_view.fallback_key != "none":
            raise SnapshotError("STACK_B_FORMAT_BINDING")

        # The archived model audit retains its original inputs and upstream digest.
        # Only the runtime dependency binding follows the newly published scene version.
        dependencies = [
            dict(
                scene_id=dep["scene_id"],
                scene_version_id=replacements[dep["scene_id"]]["id"],
                content_digest=replacements[dep["scene_id"]]["digest"],
            )
            for dep in raw["dependencies"]
        ]
        body = dict(
            content=raw["content"], actions=raw["actions"], dependencies=dependencies
        )
        exercise = revise_exercise(body["content"], scene_key)
        parent = dict(
            scene_version_id=item["scene_version_id"],
            scene_digest=expected_digest,
            validation_id=str(old_view.validation_id),
            generation_source=body["content"]["generation_source"],
        )
        # Audit the local derivation separately from the original model response and review.
        delta = dict(
            origin=RULE,
            group_question=exercise["question"],
            items=[
                {field: q[field] for field in ("question_id", "question", "input_type")}
                for q in exercise["items"]
            ],
        )
        derived = FreeSceneGenerationResult(
            user_id=owner,
            course_id=COURSE,
            operation_id=operation.id,
            request_id=historical.request_id,
            lease_epoch=fence.epoch,
            call_key=RULE,
            expected_head=SOURCE_VERSION,
            plan_id=plan_id,
            scene_id=sid,
            prompt_version=RULE,
            schema_version=RULE,
            state="candidate",
            input_snapshot=parent,
            input_digest=digest("program-exercise-input", **parent),
            request_digest=fingerprint,
            response_json=delta,
            response_digest=digest("program-exercise-delta", **delta),
            origin_type="existing_real_candidate_replay",
            sent_attempts=0,
            usage_json=None,
        )
        db.add(derived)
        await db.flush()
        validation = FreeSceneValidation(
            user_id=owner,
            course_id=COURSE,
            generation_result_id=derived.id,
            rule_version=RULE,
            state="accepted",
            cleaned_json=body,
            raw_digest=digest("scene-validation-raw", response=delta),
            cleaned_digest=digest("scene-validation-cleaned", payload=body),
            findings=[dict(rule_id=RULE, code="EXERCISE_FORMAT_ONLY")],
        )
        db.add(validation)
        await db.flush()
        stored = await repo.store_scene(
            COURSE,
            fence,
            expected_head=SOURCE_VERSION,
            key=RULE,
            plan_id=plan_id,
            scene_id=sid,
            **body,
        )
        sv = UUID(stored["scene_version_id"])
        scene_digest = digest("scene", **body)
        view = compile_presentation(
            body,
            dict(
                course_id=str(COURSE),
                operation_id=str(operation.id),
                lease_epoch=fence.epoch,
                validation_id=str(validation.id),
                result_id=str(derived.id),
                cleaned_digest=validation.cleaned_digest,
                plan_id=str(plan_id),
                scene_id=str(sid),
                expected_head=SOURCE_VERSION,
            ),
        )
        presentation = FreeScenePresentation(
            user_id=owner,
            course_id=COURSE,
            validation_id=validation.id,
            rule_version=view["rule_version"],
            fallback_key="none",
            presentation_json=view,
            presentation_digest=view["digest"],
        )
        db.add(presentation)
        await db.flush()
        ready_steps.append(
            FreeCourseStep(
                user_id=owner,
                course_id=COURSE,
                operation_id=operation.id,
                plan_id=plan_id,
                scene_id=sid,
                step_key=old_step.step_key,
                state="ready",
                scene_version_id=sv,
                presentation_id=presentation.id,
            )
        )
        eid, evid = exercise_identity(owner, COURSE, sid, sv, exercise["exercise_key"])
        replacements[str(sid)] = dict(
            id=str(sv),
            digest=scene_digest,
            exercise_id=str(eid),
            exercise_version_id=str(evid),
        )

    result = await repo.commit_manifest(
        COURSE,
        fence,
        expected_head=SOURCE_VERSION,
        key=RULE,
        plan_id=plan_id,
        bindings=[UUID(scene["id"]) for scene in replacements.values()],
        node_links=source["node_links"],
    )
    if result["version"] != SOURCE_VERSION + 1:
        raise SnapshotError("STACK_B_FORMAT_BINDING")
    db.add_all(ready_steps)
    await db.flush()
    for sid, binding in replacements.items():
        exact = dict(
            course_version=result["version"],
            scene_id=sid,
            scene_version_id=binding["id"],
        )
        exercise = await ensure_exercise(
            db,
            owner,
            COURSE,
            exact,
            binding["exercise_id"],
            binding["exercise_version_id"],
        )
        if exercise.rule_version != TYPED_RULE:
            raise SnapshotError("STACK_B_FORMAT_REFERENCE")
        await availability._emit(
            db,
            owner,
            COURSE,
            fence,
            "scene_ready",
            result,
            {
                "scene_id": sid,
                "scene_version_id": binding["id"],
                "state": "ready",
            },
        )
    await availability._emit(
        db, owner, COURSE, fence, "done", result, {"state": "succeeded"}
    )
    await repo._fence(COURSE, fence)
    operation.state = "succeeded"
    operation.lease_token = operation.lease_expires_at = None
    return await repo._record(
        COURSE,
        route,
        RULE,
        fingerprint,
        {
            **result,
            "course_id": str(COURSE),
            "operation_id": str(operation.id),
            "scenes": replacements,
            "provenance": provenance,
        },
    )


async def main():
    local_authority()
    url = os.environ["EDUMIND_DATABASE_URL"]
    require_database(url)
    sys.addaudithook(raw_io_audit)
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine).begin() as db:
            result = await publish(db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
