"""Versioned mechanical checks and private advisories; never semantic approval."""

from copy import deepcopy
from html import escape
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.free_course_planning import request_digest
from app.agents.free_scene_generation import build_request, validate_response
from app.models.free_course_writes import FreeCourseOperation
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.models.free_scene_validation import FreeSceneValidation
from app.services.free_course_snapshots import (
    SnapshotError,
    SnapshotRepository,
    WriteFence,
    canonical,
    digest,
)
from app.services.free_scene_consistency import check_consistency
from app.services.free_scene_generation import load_inputs
from app.services.free_scene_markdown import clean_code_markdown

RULE_VERSION = "free-scene-hard-gate-v4"


def clean_markdown(value: str) -> str:
    """Escape raw HTML/entities and neutralize all explicit Markdown links/images.

    Consumers must disable raw HTML, autolinking and plugins, and render code/labels as
    text. This is Markdown data, never safe HTML for innerHTML/v-html or an executable.
    """
    return escape(value.replace("\\", "\\\\"), quote=False).replace("[", "\\[").replace("]", "\\]")


def check_scene(raw: Any, inputs: dict[str, Any]) -> dict[str, Any]:
    """Fail closed with fixed findings, preserving raw content in the generation audit."""

    def rejected(code: str) -> dict[str, Any]:
        return dict(
            state="rejected",
            reason_code=code,
            findings=[dict(rule_id=f"{RULE_VERSION}:{code}", code=code)],
            cleaned=None,
        )

    try:
        value = validate_response(raw, inputs)
    except SnapshotError:
        return rejected("SCHEMA_INVALID")
    anchors = {b["anchor_id"]: b for b in value["blocks"]}
    if len(anchors) != len(value["blocks"]) or any(not k.strip() for k in anchors):
        return rejected("ANCHOR_INVALID")
    for block in value["blocks"]:
        if block["kind"] == "visualization":
            for step in block["steps"]:
                ids = [e["id"] for e in step["elements"]]
                if len(ids) != len(set(ids)) or any(not k.strip() for k in ids):
                    return rejected("VISUAL_REFERENCE_INVALID")
                if not set(step["highlight_ids"]) <= set(ids) or any(
                    e["next_id"] is not None and e["next_id"] not in ids for e in step["elements"]
                ):
                    return rejected("VISUAL_REFERENCE_INVALID")
    for action in value["actions"]:
        target = anchors.get(action["anchor_id"])
        if target is None:
            return rejected("ACTION_REFERENCE_INVALID")
        if action["type"] == "show_step" and (
            target["kind"] != "visualization" or action["step_index"] >= len(target["steps"])
        ):
            return rejected("ACTION_REFERENCE_INVALID")
    cleaned = deepcopy(value)
    try:
        for block in cleaned["blocks"]:
            if block["kind"] == "text":
                block["markdown"] = clean_code_markdown(block["markdown"])
            if block["kind"] == "exercise":
                # Private answer keys remain exact. Questions/labels/code are plain text data.
                for question in block["items"]:
                    question["solution"] = clean_code_markdown(question["solution"])
    except ValueError:
        return rejected("MARKDOWN_INVALID")
    # Persistent scene content+actions+exact direct dependencies, not only response bytes.
    scene = next(s for s in inputs["plan"]["scenes"] if s["scene_id"] == inputs["scene_id"])
    dependencies = [
        dict(
            scene_id=u["scene_id"],
            scene_version_id=u["scene_version_id"],
            content_digest=u["digest"],
        )
        for u in inputs["upstream"]
        if u["scene_id"] in scene["depends_on"]
    ]
    payload = dict(
        content=dict(blocks=cleaned["blocks"]),
        actions=cleaned["actions"],
        dependencies=dependencies,
    )
    if len(canonical(payload)) > 65536:
        return rejected("CLEANED_SIZE_EXCEEDED")
    advisory = check_consistency(value, inputs)
    return dict(
        state="accepted",
        reason_code=None,
        findings=[
            dict(
                rule_id=f"{RULE_VERSION}:SEMANTIC_ADVISORY",
                code="SEMANTIC_ADVISORY",
                report=advisory,
            )
        ],
        cleaned=payload,
    )


async def validate_candidate(
    db: AsyncSession,
    owner_id: UUID,
    course_id: UUID,
    fence: WriteFence,
    *,
    result_id: UUID,
) -> dict[str, Any]:
    """Bind checks to the actual candidate/current write fence; caller owns commit.

    Returned private content includes answers. T013 must recheck bindings while publishing;
    this function emits no scene version, head switch, event or formal approval.
    """
    repo = SnapshotRepository(db, owner_id)
    async with db.begin_nested():
        await repo._owner_lock()
        course = await repo._course(course_id, lock=True)
        await repo._fence(course_id, fence)
        row = await db.scalar(
            select(FreeSceneGenerationResult)
            .where(
                FreeSceneGenerationResult.id == result_id,
                FreeSceneGenerationResult.user_id == owner_id,
                FreeSceneGenerationResult.course_id == course_id,
                FreeSceneGenerationResult.operation_id == fence.operation_id,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise SnapshotError("NOT_FOUND")
        await repo._expected(course, row.expected_head)
        if row.lease_epoch != fence.epoch:
            raise SnapshotError("OPERATION_FENCED")
        actual = await load_inputs(
            db,
            owner_id,
            course_id,
            fence.operation_id,
            plan_id=row.plan_id,
            scene_id=row.scene_id,
            expected_head=row.expected_head,
        )
        if row.origin_type == "existing_real_candidate_replay":
            from app.services.head_course_replay import validate_replay

            checked = validate_replay(row, actual)
        elif row.origin_type == "model_generation":
            fingerprint = digest(
                "scene-generation-outcome",
                input_digest=row.input_digest,
                request_digest=row.request_digest,
                state=row.state,
                reason_code=row.reason_code,
                response=row.response_json,
                usage=row.usage_json,
                sent_attempts=row.sent_attempts,
            )
            if (
                row.input_digest != digest("scene-generation-input", snapshot=actual)
                or row.input_snapshot != actual
                or row.request_id != UUID(actual["request"]["request_id"])
                or row.request_digest != request_digest(build_request(actual))
                or row.response_digest != fingerprint
            ):
                raise SnapshotError("SNAPSHOT_CORRUPT")
            checked = (
                check_scene(row.response_json, actual)
                if row.state == "candidate"
                else dict(
                    state="rejected",
                    reason_code="GENERATION_FAILED",
                    findings=[
                        dict(rule_id=f"{RULE_VERSION}:GENERATION_FAILED", code="GENERATION_FAILED")
                    ],
                    cleaned=None,
                )
            )
        else:
            raise SnapshotError("REPLAY_SOURCE_INVALID")
        raw_digest = digest("scene-validation-raw", response=row.response_json)
        cleaned_digest = (
            digest("scene-validation-cleaned", payload=checked["cleaned"])
            if checked["cleaned"] is not None
            else None
        )
        existing = await db.scalar(
            select(FreeSceneValidation).where(
                FreeSceneValidation.user_id == owner_id,
                FreeSceneValidation.course_id == course_id,
                FreeSceneValidation.generation_result_id == result_id,
                FreeSceneValidation.rule_version == RULE_VERSION,
            )
        )
        if existing is None:
            existing = FreeSceneValidation(
                user_id=owner_id,
                course_id=course_id,
                generation_result_id=result_id,
                rule_version=RULE_VERSION,
                state=checked["state"],
                reason_code=checked["reason_code"],
                findings=checked["findings"],
                raw_digest=raw_digest,
                cleaned_digest=cleaned_digest,
                cleaned_json=checked["cleaned"],
            )
            db.add(existing)
            await db.flush()
        elif (
            existing.raw_digest != raw_digest
            or existing.cleaned_digest != cleaned_digest
            or existing.state != checked["state"]
            or existing.findings != checked["findings"]
        ):
            raise SnapshotError("SNAPSHOT_CORRUPT")
        live = await db.scalar(
            update(FreeCourseOperation)
            .where(
                FreeCourseOperation.id == fence.operation_id,
                FreeCourseOperation.user_id == owner_id,
                FreeCourseOperation.course_id == course_id,
                FreeCourseOperation.state == "running",
                FreeCourseOperation.lease_epoch == fence.epoch,
                FreeCourseOperation.lease_token == fence.token,
                FreeCourseOperation.cancel_requested_at.is_(None),
                FreeCourseOperation.lease_expires_at > func.clock_timestamp(),
                FreeCourseOperation.deadline_at > func.clock_timestamp(),
            )
            .values(state="running")
            .returning(FreeCourseOperation.id)
            .execution_options(synchronize_session="fetch")
        )
        if live is None:
            raise SnapshotError("OPERATION_FENCED")
        return deepcopy(
            dict(
                validation_id=str(existing.id),
                rule_version=RULE_VERSION,
                **checked,
                cleaned_digest=cleaned_digest,
            )
        )
