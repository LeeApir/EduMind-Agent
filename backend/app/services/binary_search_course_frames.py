"""Program-owned binary-search frames and the exact T128 archival derivation."""

from copy import deepcopy
from hashlib import sha256
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.services import binary_search_course_materials as original
from app.services import stack_course_materials as fixed
from app.services.course_question_stem import PROMPT_VERSION, is_single_line_stem
from app.services.free_course_snapshots import SnapshotError, canonical, digest

VERSION = "binary-search-program-frames-v1"
BATCH = "four-topic-live-reuse-r01-binary-search"
PARENT = "94ca8a296d685784ee1125d69e63f164154b5e712396f24d0e911d31ec9b1636"
REQUEST = "382b12c1ce2276dcaa9b16e1aee4c6a35adb858f11ffed267c08582517ec92eb"
RESPONSE = "ce5f62776767b05f971a0e887c408a72d639319e7bee6cd69f9bf9a7835cc9f9"
REVIEW = "6f8d10209302b1c3f8d6de1b3519d4adeeba58e1669ee5afa4294c2657f37b61"
SCHEMA = fixed.closed({
    key: value for key, value in original.SCHEMA["properties"].items() if key != "step_notes"
})
VALIDATOR = Draft202012Validator(SCHEMA)


def trace(values: tuple[int, ...], target: int) -> tuple[list[dict[str, Any]], int]:
    frames, result = original.search(values, target)
    iteration = 0
    comparison_frame_id = None
    for frame in frames:
        phase = frame["phase"]
        if phase in ("compare", "found"):
            iteration += 1
            comparison_frame_id = frame["frame_id"]
        frame.update(
            iteration=iteration or None,
            comparison_frame_id=comparison_frame_id,
            recomputed_mid=phase in ("compare", "found"),
            updated_endpoint=(
                ("left" if frame["comparison"] == "less" else "right")
                if phase == "narrowed" else None
            ),
            returned=result if phase == "found" else None,
        )
    if result == -1:
        frames.append(dict(
            frame_id=f"f{len(frames)}",
            phase="missing",
            line=original.CODE.splitlines().index("    return -1;") + 1,
            left=frames[-1]["left"],
            right=frames[-1]["right"],
            mid=None,
            target=target,
            comparison=None,
            iteration=None,
            comparison_frame_id=None,
            recomputed_mid=False,
            updated_endpoint=None,
            returned=-1,
        ))
    return frames, result


def note(frame: dict[str, Any], values: tuple[int, ...]) -> str:
    left, right, mid = (frame[key] for key in ("left", "right", "mid"))
    phase = frame["phase"]
    if phase == "initial":
        return f"循环开始前，初始化闭区间 [{left},{right}]，还未计算 mid。"
    if phase == "missing":
        return f"left={left} 大于 right={right}，闭区间为空。退出循环，返回 -1。"
    start = f"第 {frame['iteration']} 轮"
    value, target = values[mid], frame["target"]
    if phase == "found":
        return (
            f"{start}，计算 mid={mid}。values[{mid}]={value} 等于目标 {target}，"
            f"直接返回下标 {mid}。"
        )
    smaller = frame["comparison"] == "less"
    comparison = f"values[{mid}]={value} {'小于' if smaller else '大于'}目标 {target}"
    if phase == "compare":
        return f"{start}，在闭区间 [{left},{right}] 计算 mid={mid}，{comparison}。"
    endpoint = frame["updated_endpoint"]
    value_after = frame[endpoint]
    return (
        f"{start}，沿用同轮刚完成的比较：{comparison}。"
        f"更新 {endpoint}=mid{' + 1' if smaller else ' - 1'}={value_after}，"
        f"闭区间变为 [{left},{right}]。此帧保留 mid={mid}，尚未重新计算。"
    )


def materials() -> dict[str, Any]:
    data = original.materials()
    frames, _ = trace(original.MAIN, original.TARGET)
    data["version"] = VERSION
    data["main"]["frames"] = frames
    data["facts"].update({frame["frame_id"]: frame for frame in frames})
    data.pop("materials_digest")
    return {**data, "materials_digest": digest(VERSION, data=data)}


def request() -> dict[str, Any]:
    # The archived request remains on its original schema and instruction.
    before, rest = original.INSTRUCTION.split("[FRAMES]", 1)
    _, after = rest.split("[TEXT]", 1)
    instruction = (
        before + "[FRAMES] The program owns all frame notes. Do not return step_notes. "
        "Use the supplied iteration and comparison_frame_id to refer to the demonstration. "
        "The demonstration only shows the main example's successful search.\n[TEXT]" + after
    )
    return fixed.fixed_request(
        instruction, original.GOAL, original.outline(), materials(),
        "edumind_binary_search_program_frames_v1", SCHEMA, stem_prompt_version=PROMPT_VERSION,
    )


def candidate(parent: dict[str, Any]) -> dict[str, Any]:
    from app.services.course_trial_publication import LIVE_REUSE
    from app.services.course_trial_publication import candidate as historical_candidate

    profile = LIVE_REUSE["binary-search"]
    ctx, raw, receipt = (parent[key] for key in ("context", "raw_output", "receipt"))
    if (
        parent["candidate_digest"] != PARENT
        or receipt["request_sha256"] != REQUEST
        or receipt["raw_sha256"] != RESPONSE
        or sha256(canonical(profile.request())).hexdigest() != REQUEST
        or ctx["evidence_kind"] != "actual_provider_response"
        or ctx["plan_source"] != "fixed_outline"
        or parent != historical_candidate(ctx, raw, receipt, profile=profile)
    ):
        raise SnapshotError("BINARY_FRAMES_ARCHIVE")
    mat = materials()
    content = {key: value for key, value in raw.items() if key != "step_notes"}
    if (
        not VALIDATOR.is_valid(content)
        or any(not set(p["fact_ids"]) <= mat["facts"].keys() for p in content["paragraphs"])
        or any(not is_single_line_stem(q["stem"]) for q in content["questions"].values())
    ):
        raise SnapshotError("BINARY_FRAMES_CONTENT")
    data = dict(
        parent_digest=PARENT,
        source_request_sha256=REQUEST,
        source_response_sha256=RESPONSE,
        original_materials_digest=parent["materials_digest"],
        plan_digest=parent["plan_digest"],
        materials_digest=mat["materials_digest"],
        content=content,
        step_notes=[
            dict(frame_id=frame["frame_id"], note=note(frame, original.MAIN))
            for frame in mat["main"]["frames"]
        ],
    )
    return {**data, "candidate_digest": digest(VERSION, data=data)}


def assembly(derived: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    mat = materials()
    # Reuse the original presentation and exercise assembly, then expose the enriched trace.
    raw = dict(derived["content"], step_notes=derived["step_notes"])
    assembled = original.assemble(raw, source)
    visual = next(block for block in assembled["blocks"] if block["kind"] == "visualization")
    for step, frame in zip(visual["steps"], mat["main"]["frames"], strict=True):
        step["binary_search_frame"].update(deepcopy(frame))
    return dict(blocks=assembled["blocks"], actions=assembled["actions"], replay_source=source)


def reviewed_projection(parent, review, *, origin):
    from app.services.course_trial_publication import BINARY_SEARCH

    derived = candidate(parent)
    review_sha256 = sha256(canonical(review)).hexdigest()
    if (
        review_sha256 != REVIEW
        or review.get("candidate_digest") != derived["candidate_digest"]
        or review.get("parent_digest") != PARENT
        or review.get("verdict") != "pass"
        or review.get("full_lesson_reviewed") is not True
        or review.get("blocking_findings") != []
        or review.get("checks") != dict.fromkeys(BINARY_SEARCH.checks, True)
    ):
        raise SnapshotError("BINARY_FRAMES_REVIEW")
    source = dict(
        mapping_version=VERSION,
        origin=origin,
        topic="binary-search",
        batch=BATCH,
        model=original.request()["model"],
        prompt_version=original.VERSION,
        plan_source="fixed_outline",
        historical_stage="first_draft_teaching_failed",
        new_provider_calls=0,
        review_sha256=review_sha256,
        **{key: derived[key] for key in (
            "candidate_digest", "parent_digest", "plan_digest", "materials_digest",
            "original_materials_digest", "source_request_sha256", "source_response_sha256",
        )},
    )
    return original.GOAL, original.outline(), assembly(derived, source)
