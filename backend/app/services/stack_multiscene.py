"""Explicit, offline-ready adapters for the existing planning and scene services."""

import json
from dataclasses import replace
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.agents import free_course_planning as planning
from app.agents import free_scene_generation as scenes
from app.services import stack_course_materials as stack
from app.services import stack_multiscene_materials as basis
from app.services.free_course_snapshots import SnapshotError, canonical
from app.services.free_scene_validation import check_scene
from app.services.provider_gateway import ChatMessage, StructuredRequest

PLAN_PROMPT = "stack-boundaries-plan-v1"
SCENE_PROMPT = "stack-boundaries-scene-v1"


def planning_request(inputs: dict[str, Any]) -> StructuredRequest:
    if inputs["original_goal"] != basis.GOAL or inputs["code_language"] != "C":
        raise SnapshotError("STACK_PLAN_SCOPE")
    request = planning.build_request(inputs)
    data = basis.materials()
    payload = json.loads(request.prompt.messages[1].content)
    payload.update(
        prompt_version=PLAN_PROMPT,
        supported_material=dict(
            id=basis.VERSION, materials_digest=data["materials_digest"],
            scene_goal_excerpts={key: list(value) for key, value in basis.SCENE_GOALS.items()},
            scenes={
                key: dict(
                    demonstrated=mat["demonstrated"], text_only=mat["text_only"],
                    exercise_targets=[item["checkpoint"] for item in mat["questions"]],
                )
                for key, mat in data["scenes"].items()
            },
        ),
    )
    instruction = request.prompt.messages[0].content + """
[STACK SCENE CONSTRAINTS]
Use the supplied shared example ID. Plan normal, then rejections, each with text, code,
visualization and exercise. Make rejections depend on normal. Use one objective per supplied
exact goal excerpt with source user_requirement and a real source key. Assign each objective
to the scene that teaches and practices it, as specified in scene_goal_excerpts. Write
meaningful objective descriptions and scene purposes, distinguishing the successful trace
from both refused operations. The program provides the implementation and checkpoints.
"""
    return replace(request, prompt=replace(
        request.prompt, messages=(
            ChatMessage("system", instruction), ChatMessage("user", canonical(payload).decode())
        ),
    ))


def validate_plan(raw: Any, inputs: dict[str, Any]) -> dict[str, Any]:
    if inputs["original_goal"] != basis.GOAL or inputs["code_language"] != "C":
        raise SnapshotError("STACK_PLAN_SCOPE")
    value = planning.validate_response(raw, inputs)
    if value["needs_clarification"]:
        return value
    plan = value["plan"]
    objectives = {obj["id"]: obj for obj in plan["objectives"]}
    if (
        plan["shared_example"] != basis.VERSION
        or list(basis.SCENE_GOALS) != [s["scene_key"] for s in plan["scenes"]]
        or len(objectives) != sum(len(goals) for goals in basis.SCENE_GOALS.values())
        or any(obj["source"] != "user_requirement" for obj in objectives.values())
    ):
        raise SnapshotError("STACK_PLAN_SCOPE")
    for scene in plan["scenes"]:
        key = scene["scene_key"]
        excerpts = [objectives[obj]["source_excerpt"] for obj in scene["objective_ids"]]
        if (
            sorted(excerpts) != sorted(basis.SCENE_GOALS[key])
            or set(scene["forms"]) != set(basis.FORMS)
            or scene["depends_on"] != ([] if key == "normal" else ["normal"])
        ):
            raise SnapshotError("STACK_PLAN_SCOPE")
    return value



def fixed_outline(inputs: dict[str, Any]) -> dict[str, Any]:
    """Derive the reviewed plan from the sole supported goal, without model output."""
    snapshot = planning.snapshot_input(inputs)
    source = snapshot["request_sources"].get("request_1")
    if (
        snapshot.get("stack_boundaries") != basis.FIXED_BATCH
        or set(snapshot["request_sources"]) != {"request_1"}
        or source != dict(request_id=snapshot["request_id"], version=1, text=basis.GOAL)
        or snapshot["learner_evidence"]
        or snapshot["profile_id"] is not None
        or snapshot["profile_version"] is not None
    ):
        raise SnapshotError("STACK_FIXED_OUTLINE_SCOPE")
    descriptions = {
        "normal": (
            "追踪从空栈执行 push(3)、push(8)、pop、push(5)，"
            "用有效元素、栈顶和出栈值解释后进先出。",
        ),
        "rejections": (
            "解释 count == CAP 时 push 在写入前返回 false，并核对有效元素和计数。",
            "解释 count == 0 时 pop 在修改计数和写出参数前返回 false。"
            "核对拒绝前后状态，区分保留的旧 value 和本步出栈值。",
        ),
    }
    purposes = {
        "normal": ("正常入栈与出栈", "用五帧追踪成功操作，练习区分出栈值与当前栈顶。"),
        "rejections": ("满栈与空栈的拒绝", "用九帧对照两次守卫及返回值，练习判断拒绝后的状态。"),
    }
    objectives = []
    scenes = []
    for scene_key, excerpts in basis.SCENE_GOALS.items():
        ids = []
        for index, (excerpt, description) in enumerate(
            zip(excerpts, descriptions[scene_key], strict=True), 1,
        ):
            objective_id = f"{scene_key}-{index}"
            ids.append(objective_id)
            objectives.append(dict(
                id=objective_id, description=description, source="user_requirement",
                source_key="request_1", source_excerpt=excerpt,
            ))
        title, purpose = purposes[scene_key]
        scenes.append(dict(
            scene_key=scene_key, title=title, purpose=purpose, forms=list(basis.FORMS),
            objective_ids=ids, depends_on=[] if scene_key == "normal" else ["normal"],
        ))
    plan = dict(
        title="固定容量数组栈：正常操作与拒绝边界",
        shared_example=basis.VERSION, objectives=objectives, scenes=scenes,
        terminology=[
            dict(term="有效前缀", meaning="data 的前 count 个元素；count 是有效元素个数。"),
            dict(term="栈顶", meaning="count 大于 0 时，栈顶为 data[count - 1]。空栈没有栈顶。"),
            dict(term="后进先出", meaning="成功出栈取出当前栈顶元素。"),
        ],
        conventions=[
            "CAP 为 3，演示使用有效指针，底层数组不扩容。",
            "拒绝场景中，两次失败都保留有效元素、计数、底层槽位和调用者的旧 value。",
            "底层残留值由 count 划定是否有效，旧 value 不代表本步有新的出栈值。",
        ],
    )
    return validate_plan(dict(
        needs_clarification=False, plan=plan, questions=[], reason=None, source_keys=[],
    ), snapshot)["plan"]

def scene_request(inputs: dict[str, Any]) -> StructuredRequest:
    snapshot = scenes.snapshot_input(inputs)
    validate_plan(
        dict(needs_clarification=False, plan=snapshot["plan"]["candidate"],
             questions=[], reason=None, source_keys=[]),
        snapshot["request"],
    )
    selected = next(
        row for row in snapshot["plan"]["scenes"] if row["scene_id"] == snapshot["scene_id"]
    )
    key = selected["scene_key"]
    planned = next(
        (row for row in snapshot["plan"]["candidate"]["scenes"] if row["scene_key"] == key),
        None,
    )
    ids = {row["scene_key"]: row["scene_id"] for row in snapshot["plan"]["scenes"]}
    upstream = [row["scene_id"] for row in snapshot["upstream"]]
    if (
        planned is None
        or any(selected[field] != planned[field]
            for field in ("title", "purpose", "forms", "objective_ids"))
        or upstream != selected["depends_on"]
        or upstream != [ids.get(dep) for dep in planned["depends_on"]]
    ):
        raise SnapshotError("STACK_SCENE_DEPENDENCY")
    data = basis.materials()
    mat = data["scenes"][key]
    request = scenes.build_request(snapshot)
    payload = dict(
        prompt_version=SCENE_PROMPT, **snapshot, materials_digest=data["materials_digest"],
        scene_material=mat,
    )
    if len(canonical(payload)) > 128000:
        raise SnapshotError("SCENE_INPUT_TOO_LARGE")
    schema = stack.closed(dict(
        paragraphs=dict(
            type="array", minItems=2, maxItems=7,
            items=stack.SCHEMA["properties"]["paragraphs"]["items"],
        ),
        explanations=stack.closed({item["key"]: stack.TEXT for item in mat["questions"]}),
    ))
    instruction = """Write only the assigned stack scene's Chinese teaching paragraphs and
question explanations. Cite only supplied facts for that scene. Teach the assigned objectives
using the exact provided code and frames. Explain why the relevant state changes or stays
unchanged. Distinguish success, popped value and caller output; unchanged output on refusal is
not a new popped value. Follow demonstrated and text_only. Use upstream only as prior learning.
The program supplies code, visualization, stems and private answers. Do not output those fields.
Keep transfer answers in their explanations, not in lesson text. No HTML, links, tools or code
execution. Return only the supplied closed schema."""
    return replace(request, json_schema=schema, prompt=replace(
        request.prompt, messages=(
            ChatMessage("system", instruction), ChatMessage("user", canonical(payload).decode())
        ),
    ))


def assemble(raw: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    request = scene_request(inputs)
    payload = json.loads(request.prompt.messages[1].content)
    mat = payload["scene_material"]
    if (
        not Draft202012Validator(request.json_schema).is_valid(raw)
        or any(not p["text"].strip() or not set(p["fact_ids"]) <= mat["facts"].keys()
               for p in raw["paragraphs"])
        or any(not text.strip() for text in raw["explanations"].values())
    ):
        raise SnapshotError("STACK_SCENE_CONTENT")
    blocks = [
        dict(kind="text", anchor_id=f"paragraph-{i}", markdown=p["text"])
        for i, p in enumerate(raw["paragraphs"])
    ]
    steps = []
    for frame in mat["frames"]:
        caption = frame["operation"]
        if frame.get("rejection"):
            caption += " · " + ("满栈拒绝" if frame["rejection"] == "full" else "空栈拒绝")
        if "output" in frame:
            if frame["success"] is not None:
                caption += f" · 返回 {'true' if frame['success'] else 'false'}"
            caption += f" · count={frame['count']}，value={frame['output']}"
            caption += f"，底层槽位={frame['storage']}"
        if frame["popped"] is not None:
            caption += f" · 出栈值={frame['popped']}"
        elements = [
            dict(id=f"slot-{i}", label=str(value), next_id=None)
            for i, value in enumerate(frame["values"])
        ]
        steps.append(dict(
            caption=caption, elements=elements,
            highlight_ids=[elements[-1]["id"]] if elements else [],
        ))
    blocks.extend([
        dict(kind="code", anchor_id="demo-code", language="c", source=mat["source"]),
        dict(kind="visualization", anchor_id="stack-state", visualization_type="stack",
             text_alternative=mat["demonstrated"], steps=steps),
        dict(kind="code", anchor_id="practice-code", language="c", source=mat["exercise_source"]),
        dict(kind="exercise", anchor_id="practice", exercise_key="stack-practice",
             question="阅读本场景 practice-code 中的 C 代码并作答。",
             items=[
                 dict(question_id=q["key"], input_type="short_text",
                      question=f"根据 practice-code 中的代码，{q['checkpoint']}。"
                               f"只输入{q['domain']}，不加单位或解释。",
                      answer_key=q["private_answer"], solution=raw["explanations"][q["key"]])
                 for q in mat["questions"]
             ]),
    ])
    candidate = dict(
        blocks=blocks,
        actions=[dict(type="show_step", anchor_id="stack-state", step_index=i)
                 for i in range(len(steps))],
    )
    checked = check_scene(candidate, inputs)
    if checked["state"] != "accepted":
        raise SnapshotError(checked["reason_code"])
    return candidate


PLAN_WIRE = "stack-boundaries-planning-wire-v1"
SCENE_WIRE = "stack-boundaries-scene-wire-v1"


def wire_plan_request(inputs: dict[str, Any]) -> StructuredRequest:
    from copy import deepcopy

    from app.agents.head_course_planning_wire import INSTRUCTION, SCHEMA, VERSION

    if inputs.get("stack_boundaries") != basis.VERSION:
        raise SnapshotError("STACK_PLAN_SCOPE")
    request = planning_request(inputs)
    schema = deepcopy(SCHEMA)
    schema["properties"]["protocol_version"]["enum"] = [PLAN_WIRE]
    system, user = request.prompt.messages
    instruction = system.content.replace(
        "Planner suggestions have null source_key/source_excerpt.",
        "Only user_requirement objectives with exact evidence are supported here.",
    )
    return replace(request, json_schema=schema, prompt=replace(
        request.prompt, messages=(
            ChatMessage("system", instruction + "\n" + INSTRUCTION.replace(VERSION, PLAN_WIRE)),
            user,
        ),
    ))


def wire_plan_response(raw: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    request = wire_plan_request(inputs)
    if not Draft202012Validator(request.json_schema).is_valid(raw):
        raise SnapshotError("STACK_PLAN_WIRE")
    plans = raw["plans"]
    if len(plans) != (0 if raw["needs_clarification"] else 1):
        raise SnapshotError("STACK_PLAN_WIRE")
    return validate_plan(dict(
        needs_clarification=raw["needs_clarification"],
        plan=plans[0] if plans else None,
        questions=raw["questions"], reason=raw["reason"] or None,
        source_keys=raw["source_keys"],
    ), inputs)


def bound_scene_request(inputs: dict[str, Any]) -> StructuredRequest:
    """Only the transaction-local lease is omitted from the outbound snapshot."""
    batch = inputs["request"].get("stack_boundaries")
    if batch not in (basis.VERSION, basis.FIXED_BATCH):
        raise SnapshotError("STACK_SCENE_SCOPE")
    fixed = batch == basis.FIXED_BATCH
    if fixed and inputs["plan"]["candidate"] != fixed_outline(inputs["request"]):
        raise SnapshotError("STACK_FIXED_OUTLINE_BINDING")
    request = scene_request(inputs)
    system, user = request.prompt.messages
    payload = json.loads(user.content)
    payload.pop("lease_epoch")
    payload["wire_protocol"] = SCENE_WIRE
    if fixed:
        payload["plan_source"] = "fixed_outline"
    return replace(request, prompt=replace(
        request.prompt, messages=(system, ChatMessage("user", canonical(payload).decode())),
    ))


def checked_scene(value: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Validate raw teaching and attach program-owned line metadata after the common gate."""
    if not isinstance(value, dict) or set(value) != {"raw_output", "generation_source"}:
        raise SnapshotError("STACK_SCENE_CONTENT")
    request = bound_scene_request(inputs)
    payload = json.loads(request.prompt.messages[1].content)
    scene = next(s for s in inputs["plan"]["scenes"] if s["scene_id"] == inputs["scene_id"])
    mat = payload["scene_material"]
    source = value["generation_source"]
    if (
        not isinstance(source, dict)
        or set(source) != {
            "origin", "batch", "model", "prompt_version", "plan_source", "plan_digest",
            "materials_digest", "candidate_digest", "review_sha256", "evidence_kind", "scene_key",
            "parent_digest", "source_request_sha256", "source_response_sha256",
        }
        or source["origin"] != "stack_boundaries_model_generation"
        or source["batch"] != inputs["request"]["stack_boundaries"]
        or source["model"] != "deepseek-flash"
        or source["prompt_version"] != SCENE_PROMPT
        or source["plan_source"] != payload.get("plan_source", "model_planned")
        or source["plan_digest"] != inputs["plan"]["digest"]
        or source["materials_digest"] != payload["materials_digest"]
        or source["scene_key"] != scene["scene_key"]
        or source["parent_digest"] is not None
        or source["evidence_kind"] not in ("offline_fixture", "actual_provider_response")
        or any(not isinstance(source[k], str) or len(source[k]) != 64
               or set(source[k]) - set("0123456789abcdef")
               for k in ("candidate_digest", "review_sha256",
                         "source_request_sha256", "source_response_sha256"))
    ):
        raise SnapshotError("STACK_SCENE_SCOPE")
    assembled = assemble(value["raw_output"], inputs)
    checked = check_scene(assembled, inputs)
    if checked["state"] != "accepted":
        raise SnapshotError(checked["reason_code"])
    blocks = checked["cleaned"]["content"]["blocks"]
    visual = next(block for block in blocks if block["kind"] == "visualization")
    lines = mat["source"].splitlines()
    for step, frame in zip(visual["steps"], mat["frames"], strict=True):
        line = frame["guard_line"] if frame.get("rejection") else frame["line"]
        if not 1 <= line <= len(lines):
            raise SnapshotError("STACK_FRAME_LINE")
        step["stack_frame"] = dict(
            frame_id=frame["frame_id"], code_anchor="demo-code", line=line,
            popped=frame["popped"],
            note=(
                "守卫成立，提前返回。保留调用者的旧 value，本步没有新出栈值。"
                if frame.get("rejection") else ""
            ),
        )
    checked["cleaned"]["content"]["generation_source"] = source
    return checked
