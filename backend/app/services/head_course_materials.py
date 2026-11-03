"""Finite T108 materials and exact prompt assembly; no I/O or model prose fallback."""

import json
from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.services.free_course_snapshots import SnapshotError, canonical, digest
from scripts.isolated_diagnostics import p15_minimal_contract as contract
from scripts.isolated_diagnostics.p15_head_insertion_engine import build_example

VERSION = "head-goal-course-v1"
ORIGIN = "head_goal_model_generation"
GOAL = (
    "我已了解 C 指针、struct、NULL 和函数返回值，希望通过头插示例，"
    "理解新节点如何连接旧链表，以及为什么调用者需要接收函数返回值。"
)
KNOWN = ["C 指针", "struct", "NULL", "函数返回值"]
SPECS: dict[str, dict[str, Any]] = {
    "head-new-A": dict(
        version="head-insertion-spec-v1",
        variant="normal",
        initial_values=[12],
        insert_values=[4, 7],
        allocation_success=[True, True],
    ),
    "head-new-B": dict(
        version="head-insertion-spec-v1",
        variant="normal",
        initial_values=[-8],
        insert_values=[6, 0],
        allocation_success=[True, True],
    ),
}
SUPPORT: dict[str, Any] = dict(
    version=VERSION,
    examples=SPECS,
    scene_count=1,
    required_forms=["text", "code", "visualization", "exercise"],
    selection=(
        "Use exactly one example ID as plan.shared_example. One complete "
        "scene; purposes must cover linking old head AND receiving "
        "return. Chinese model teaching, program code/trace/answers; "
        "unsupported scope must stop."
    ),
)
QKEYS = ("link_target", "normal_values", "discarded_values", "unreachable_count")


def closed(props: dict[str, Any]) -> dict[str, Any]:
    return dict(type="object", additionalProperties=False, properties=props, required=list(props))


TEXT = dict(type="string", minLength=1, maxLength=4000)
SCHEMA = closed(
    dict(
        prerequisites=TEXT,
        paragraphs=dict(
            type="array",
            minItems=3,
            maxItems=10,
            items=closed(
                dict(
                    text=TEXT,
                    fact_ids=dict(
                        type="array",
                        minItems=1,
                        maxItems=16,
                        uniqueItems=True,
                        items=dict(type="string"),
                    ),
                )
            ),
        ),
        step_notes=dict(
            type="array",
            minItems=1,
            maxItems=20,
            items=closed(
                dict(
                    frame_id=dict(type="string"),
                    title=dict(type="string", minLength=1, maxLength=100),
                    note=TEXT,
                )
            ),
        ),
        questions=closed({k: closed(dict(stem=TEXT, explanation=TEXT)) for k in QKEYS}),
        learning_summary=TEXT,
        lifecycle=TEXT,
        failure_scope=TEXT,
    )
)
INSTRUCTION = """[ROLE] Generate a complete Simplified Chinese lesson, not an echo or outline.
[OWNERSHIP] Program owns C code, snapshots, facts, frame IDs, scenarios and answer keys.
Generate ALL teaching text in the supplied Schema. Never change the program materials or
claim C was executed. No tools, HTML, links, external material or invented learner facts.
[GOAL] Preserve the exact original goal. Learner prerequisites are self reports, not demonstrated
mastery. Teach how p->next saves the old head, local head/p scope, return p, and why the caller
must assign the returned pointer. Explain successful NULL checks and uninitialized fields.
[BOUNDARY] Main allocations are assumed successful. The conditional mask can force no
allocation, but actual malloc failure is not animated here; explain return of old head.
Initial i nodes have automatic storage, t nodes are dynamically allocated. Explain lifetime,
free only dynamic nodes, save next before free, do not read freed nodes or free stack nodes.
No cleanup animation/code execution is supplied. Traversal reaches NULL: full order is known.
[STEPS] Exactly one step_notes per frame, exact frame_id order; title/note describe that state,
line and scope. No missing prose will be supplied by an assistant.
[QUESTIONS] Four questions use the provided NEW transfer scenario, distinct from the worked
example. Each stem must include its exact scenario code and the task in natural Chinese;
keep node IDs from scenario. link_target asks the first p->next target in normal code;
normal_values asks full normal caller traversal values; discarded_values asks caller traversal
when the return is discarded; unreachable_count asks number of dynamic nodes unreachable
from that caller. No answer in stems, no worked results, no answer-bearing format examples,
no leading question. State the input format without any concrete example: link_target takes
the targeted initial node's C variable name only (no & or prose); the two traversal questions
take a JSON integer array; unreachable_count takes one JSON integer. Do not put transfer
answers in teaching paragraphs or step notes.
Use private program answers to write accurate explanations, not to hint in stems.
[FACTS] paragraphs cite existing main fact IDs. IDs alone do not explain facts. Use natural
Chinese with enough reasoning for this goal. Include prerequisites, summary, failure boundary
and lifetime. Return exactly the supplied Schema, without fences or other fields."""
REPAIR_INSTRUCTION = INSTRUCTION + (
    "\n[REPAIR] Return complete new teaching JSON. Only fix the "
    "supplied minor wording issues; all facts, question scenarios and "
    "output structure are immutable. Preserve parent identity through "
    "the server, never invent it."
)


def frames(example: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for i, state in enumerate(example["trace"]["steps"]):
        result.append(
            dict(
                frame_id=f"f{len(result):02d}",
                state_index=i,
                line=state["code_line"],
                kind=state["phase"],
                fact_id=f"trace_step_{i:02d}",
            )
        )
        if state["phase"] == "allocate" and state["p"] is not None:
            result.append(
                dict(
                    frame_id=f"f{len(result):02d}",
                    state_index=i,
                    line=example["code"]["line_anchors"]["allocation_failed"],
                    kind="success_null_check",
                    fact_id=f"trace_step_{i:02d}",
                )
            )
    return result


def selected(plan: dict[str, Any]) -> str:
    key = plan.get("shared_example")
    scenes = plan.get("scenes", [])
    if (
        key not in SPECS
        or len(scenes) != 1
        or set(scenes[0]["forms"]) != set(SUPPORT["required_forms"])
    ):
        raise SnapshotError("HEAD_PLAN_UNSUPPORTED")
    return key


def materials(plan: dict[str, Any]) -> dict[str, Any]:
    key = selected(plan)
    catalog = contract.make_catalog(SPECS[key])
    # New transfer materials; no answer-bearing formatting examples are sent to the learner.
    spec = dict(
        version="head-insertion-spec-v1",
        variant="normal",
        initial_values=[30, 40],
        insert_values=[11],
        allocation_success=[True],
    )
    normal = build_example(spec)
    discarded = build_example(dict(spec, variant="discard_return"))
    # Independent, closed-form expectations; never take the engine as its own oracle.
    assert (
        catalog["example"]["observation"]["reachable_prefix"]
        == list(reversed(SPECS[key]["insert_values"])) + SPECS[key]["initial_values"]
    )
    assert normal["observation"]["reachable_prefix"] == [11, 30, 40]
    assert discarded["observation"]["reachable_prefix"] == [30, 40]
    assert discarded["observation"]["unreachable_allocated_ids"] == ["t0"]
    data = dict(
        version=VERSION,
        selected_example=key,
        catalog=catalog,
        frames=frames(catalog["example"]),
        transfer=dict(normal=normal, discarded=discarded),
        answers=dict(
            link_target=next(s for s in normal["trace"]["steps"] if s["phase"] == "link")["nodes"][
                "t0"
            ]["next"],
            normal_values=json.dumps(
                normal["observation"]["reachable_prefix"], separators=(",", ":")
            ),
            discarded_values=json.dumps(
                discarded["observation"]["reachable_prefix"], separators=(",", ":")
            ),
            unreachable_count=str(len(discarded["observation"]["unreachable_allocated_ids"])),
        ),
    )
    assert data["answers"] == dict(
        link_target="i0",
        normal_values="[11,30,40]",
        discarded_values="[30,40]",
        unreachable_count="1",
    )
    return dict(**data, materials_digest=digest("head-materials", data=data))


def content_payload(inputs: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    return dict(
        original_goal=inputs["original_goal"],
        source_binding={key: inputs[key] for key in ("course_id", "operation_id", "request_id")},
        prerequisite_evidence=dict(
            source="request_1",
            excerpt="我已了解 C 指针、struct、NULL 和函数返回值",
            self_reported=KNOWN,
            demonstrated_mastery=None,
        ),
        plan=plan,
        materials=materials(plan),
        unknown_learner_fields="all others",
    )


def body(
    payload: dict[str, Any], parent: dict[str, Any] | None = None, issues: list | None = None
) -> dict[str, Any]:
    return dict(
        model="deepseek-flash",
        stream=False,
        store=False,
        reasoning=dict(effort="none"),
        max_output_tokens=8000,
        temperature=0.2,
        input=[
            dict(role="system", content=INSTRUCTION if parent is None else REPAIR_INSTRUCTION),
            dict(
                role="user",
                content=canonical(
                    payload
                    if parent is None
                    else dict(original_input=payload, parent=parent, issues=issues)
                ).decode(),
            ),
        ],
        text=dict(
            format=dict(
                type="json_schema", name="edumind_head_goal_course", strict=True, schema=SCHEMA
            )
        ),
    )


def validate_content(payload: dict[str, Any], value: dict[str, Any]) -> None:
    Draft202012Validator(SCHEMA).validate(value)
    if len(canonical(value)) > 48000:
        raise SnapshotError("HEAD_CONTENT_TOO_LARGE")
    facts = (
        {f["id"] for f in payload["materials"]["catalog"]["facts"]}
        if isinstance(payload["materials"]["catalog"]["facts"], list)
        else set(payload["materials"]["catalog"]["facts"])
    )
    if any(not set(p["fact_ids"]) <= facts for p in value["paragraphs"]):
        raise SnapshotError("HEAD_FACT_REFERENCE")
    if [s["frame_id"] for s in value["step_notes"]] != [
        f["frame_id"] for f in payload["materials"]["frames"]
    ]:
        raise SnapshotError("HEAD_FRAME_BINDING")
    for k in QKEYS:
        code = payload["materials"]["transfer"][
            "discarded" if k in ("discarded_values", "unreachable_count") else "normal"
        ]["code"]["source"]
        if code not in value["questions"][k]["stem"]:
            raise SnapshotError("HEAD_QUESTION_SCENARIO")


def assemble(
    payload: dict[str, Any], raw: dict[str, Any], source: dict[str, Any]
) -> dict[str, Any]:
    validate_content(payload, raw)
    mat = payload["materials"]
    blocks: list[dict[str, Any]] = []

    def prose(text):
        blocks.append(dict(kind="text", anchor_id=f"text-{len(blocks)}", markdown=text))

    prose(raw["prerequisites"])
    for p in raw["paragraphs"]:
        prose(p["text"])
    blocks.append(
        dict(
            kind="code",
            anchor_id="head-code",
            language="c",
            source=mat["catalog"]["example"]["code"]["source"],
        )
    )
    steps = []
    for f, note in zip(mat["frames"], raw["step_notes"], strict=True):
        state = mat["catalog"]["example"]["trace"]["steps"][f["state_index"]]
        steps.append(
            dict(
                caption=note["title"],
                head_frame=dict(
                    **f,
                    title=note["title"],
                    note=note["note"],
                    code_anchor="head-code",
                    locals_scope="inactive"
                    if state["phase"] in ("initial", "caller")
                    else "active",
                    state=deepcopy(state),
                ),
            )
        )
    blocks.append(
        dict(
            kind="visualization",
            anchor_id="head-state",
            visualization_type="head_insertion_replay_v1",
            text_alternative=raw["learning_summary"],
            steps=steps,
        )
    )
    for k in ("failure_scope", "lifecycle", "learning_summary"):
        prose(raw[k])
    blocks.append(
        dict(
            kind="exercise",
            anchor_id="head-questions",
            exercise_key="head-questions",
            question="迁移练习",
            items=[
                dict(
                    question_id=k,
                    question=raw["questions"][k]["stem"],
                    input_type="short_text"
                    if k == "link_target"
                    else "integer"
                    if k == "unreachable_count"
                    else "json_integer_array",
                    answer_key=mat["answers"][k],
                    solution=raw["questions"][k]["explanation"],
                )
                for k in QKEYS
            ],
        )
    )
    return dict(
        blocks=blocks,
        actions=[
            dict(type="show_step", anchor_id="head-state", step_index=i) for i in range(len(steps))
        ],
        generation_source=source,
    )
