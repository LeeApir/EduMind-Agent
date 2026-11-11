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
