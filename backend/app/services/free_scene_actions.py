"""Bounded non-executable presentation snapshots and a pure playback reducer."""

from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.free_course_writes import FreeCourseOperation
from app.models.free_scene_actions import FreeScenePresentation
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.models.free_scene_validation import FreeSceneValidation
from app.services.free_course_snapshots import (
    SnapshotError,
    SnapshotRepository,
    WriteFence,
    canonical,
    digest,
)
from app.services.free_scene_validation import validate_candidate

RULE_VERSION = "free-scene-actions-v1"
FALLBACKS = {"MEDIA_UNAVAILABLE", "RENDERER_UNAVAILABLE", "ACTION_UNAVAILABLE"}


def compile_presentation(
    cleaned: dict[str, Any],
    binding: dict[str, Any],
    *,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    """Private derived view, not a REST scene projection or a publishing capability."""
    if fallback_reason is not None and fallback_reason not in FALLBACKS:
        raise SnapshotError("PRESENTATION_REASON_INVALID")
    blocks = deepcopy(cleaned["content"]["blocks"])
    for block in blocks:
        if block["kind"] == "exercise":
            block["items"] = [
                {key: q[key] for key in ("question_id", "question", "input_type")}
                for q in block["items"]
            ]
    payload = dict(
        rule_version=RULE_VERSION,
        binding=deepcopy(binding),
        blocks=blocks,
        timeline=deepcopy(cleaned["actions"]) if fallback_reason is None else [],
        diagnostics=[dict(code=fallback_reason)] if fallback_reason else [],
        mode="guided" if fallback_reason is None else "static",
        code_execution=False,
        media_requested=False,
        animation_executed=False,
        description="状态步骤演示；代码仅作文本，未执行代码或渲染媒体。",
    )
    if len(canonical(payload)) > 65536:
        raise SnapshotError("PRESENTATION_TOO_LARGE")
    return {**payload, "digest": digest("scene-presentation", payload=payload)}


def _verified(presentation: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in presentation.items() if k != "digest"}
    if (
        len(canonical(payload)) > 65536
        or payload.get("rule_version") != RULE_VERSION
        or presentation.get("digest") != digest("scene-presentation", payload=payload)
    ):
        raise SnapshotError("PRESENTATION_CORRUPT")
    return payload


def initial_state(presentation: dict[str, Any]) -> dict[str, Any]:
    value = _verified(presentation)
    return dict(
        presentation_digest=presentation["digest"],
        mode=value["mode"],
        paused=True,
        cursor=-1,
        active_anchor=None,
        code_anchor=None,
        step_indices={b["anchor_id"]: 0 for b in value["blocks"] if b["kind"] == "visualization"},
        diagnostics=deepcopy(value["diagnostics"]),
    )


def transition(
    presentation: dict[str, Any],
    state: dict[str, Any],
    command: str,
    *,
    anchor_id: str | None = None,
) -> dict[str, Any]:
    """Only move through existing JSON snapshots. No timers, compilation, fetch or execution."""
    value = _verified(presentation)
    if state.get("presentation_digest") != presentation["digest"]:
        raise SnapshotError("STALE_PRESENTATION")
    start = initial_state(presentation)

    def static(reason: str) -> dict[str, Any]:
        diagnostics = {d["code"] for d in start["diagnostics"]}
        diagnostics.add(reason)
        return {
            **start,
            "mode": "static",
            "diagnostics": [dict(code=c) for c in sorted(diagnostics)],
        }

    if not isinstance(command, str):
        return static("ACTION_UNAVAILABLE")
    if command in FALLBACKS:
        return static(command)
    if (
        set(state) != set(start)
        or not isinstance(state.get("mode"), str)
        or state["mode"] not in {"guided", "static"}
    ):
        return static("ACTION_UNAVAILABLE")
    blocks = {b["anchor_id"]: b for b in value["blocks"]}
    steps = state["step_indices"]
    if (
        type(state["cursor"]) is not int
        or not -1 <= state["cursor"] < max(1, len(value["timeline"]))
        or type(state["paused"]) is not bool
        or not isinstance(steps, dict)
        or set(steps) != set(start["step_indices"])
        or any(type(i) is not int or not 0 <= i < len(blocks[a]["steps"]) for a, i in steps.items())
        or state["active_anchor"] not in [None, *blocks]
        or state["code_anchor"]
        not in [None, *(a for a, b in blocks.items() if b["kind"] == "code")]
        or not isinstance(state["diagnostics"], list)
        or len(state["diagnostics"]) > 3
        or any(
            not isinstance(d, dict)
            or set(d) != {"code"}
            or not isinstance(d["code"], str)
            or d["code"] not in FALLBACKS
            for d in state["diagnostics"]
        )
    ):
        return static("ACTION_UNAVAILABLE")
    if state["mode"] == "static":
        result = static("ACTION_UNAVAILABLE")
        codes = {d["code"] for d in state["diagnostics"]} | {
            d["code"] for d in start["diagnostics"]
        }
        result["diagnostics"] = [dict(code=c) for c in sorted(codes or {"ACTION_UNAVAILABLE"})]
        return result
    result = deepcopy(state)
    if command in {"play", "pause"}:
        result["paused"] = command == "pause"
    elif command in {"next_step", "previous_step"}:
        if anchor_id not in steps:
            return static("ACTION_UNAVAILABLE")
        index = steps[anchor_id] + (1 if command == "next_step" else -1)
        result["step_indices"][anchor_id] = max(0, min(index, len(blocks[anchor_id]["steps"]) - 1))
        result["active_anchor"] = anchor_id
    elif command == "next_action":
        index = state["cursor"] + 1
        if index >= len(value["timeline"]):
            result["paused"] = True
            return result
        action = value["timeline"][index]
        target = blocks.get(action.get("anchor_id"))
        if target is None or action.get("type") not in {"highlight_block", "show_step", "pause"}:
            return static("ACTION_UNAVAILABLE")
        result["cursor"] = index
        result["active_anchor"] = action["anchor_id"]
        result["code_anchor"] = action["anchor_id"] if target["kind"] == "code" else None
        if action["type"] == "show_step":
            i = action.get("step_index")
            if (
                target["kind"] != "visualization"
                or type(i) is not int
                or not 0 <= i < len(target["steps"])
            ):
                return static("ACTION_UNAVAILABLE")
            result["step_indices"][action["anchor_id"]] = i
        elif action.get("step_index") is not None:
            return static("ACTION_UNAVAILABLE")
        elif action["type"] == "pause":
            result["paused"] = True
    else:
        return static("ACTION_UNAVAILABLE")
    return result


async def prepare_presentation(
    db: AsyncSession,
    owner_id: UUID,
    course_id: UUID,
    fence: WriteFence,
    *,
    validation_id: UUID,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    """Persist a source-bound derived snapshot/diagnostic, without publishing it."""
    repo = SnapshotRepository(db, owner_id)
    async with db.begin_nested():
        await repo._owner_lock()
        await repo._course(course_id, lock=True)
        await repo._fence(course_id, fence)
        row = await db.scalar(
            select(FreeSceneValidation)
            .where(
                FreeSceneValidation.id == validation_id,
                FreeSceneValidation.user_id == owner_id,
                FreeSceneValidation.course_id == course_id,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise SnapshotError("NOT_FOUND")
        checked = await validate_candidate(
            db, owner_id, course_id, fence, result_id=row.generation_result_id
        )
        if checked["validation_id"] != str(validation_id) or checked["state"] != "accepted":
            raise SnapshotError("HARD_GATE_REJECTED")
        if (
            row.cleaned_json != checked["cleaned"]
            or row.cleaned_digest != checked["cleaned_digest"]
        ):
            raise SnapshotError("SNAPSHOT_CORRUPT")
        source = await db.get(FreeSceneGenerationResult, row.generation_result_id)
        if source is None:
            raise SnapshotError("SNAPSHOT_CORRUPT")
        # Every block/action retains the exact immutable source identity and digest.
        view = compile_presentation(
            checked["cleaned"],
            dict(
                course_id=str(course_id),
                operation_id=str(fence.operation_id),
                lease_epoch=fence.epoch,
                validation_id=str(validation_id),
                result_id=str(row.generation_result_id),
                cleaned_digest=checked["cleaned_digest"],
                plan_id=str(source.plan_id),
                scene_id=str(source.scene_id),
                expected_head=source.expected_head,
            ),
            fallback_reason=fallback_reason,
        )
        fallback_key = fallback_reason or "none"
        saved = await db.scalar(
            select(FreeScenePresentation).where(
                FreeScenePresentation.user_id == owner_id,
                FreeScenePresentation.course_id == course_id,
                FreeScenePresentation.validation_id == validation_id,
                FreeScenePresentation.rule_version == RULE_VERSION,
                FreeScenePresentation.fallback_key == fallback_key,
            )
        )
        if saved is None:
            saved = FreeScenePresentation(
                user_id=owner_id,
                course_id=course_id,
                validation_id=validation_id,
                rule_version=RULE_VERSION,
                fallback_key=fallback_key,
                presentation_json=view,
                presentation_digest=view["digest"],
            )
            db.add(saved)
            await db.flush()
        elif saved.presentation_json != view or saved.presentation_digest != view["digest"]:
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
        return deepcopy(dict(presentation_id=str(saved.id), presentation=view))
