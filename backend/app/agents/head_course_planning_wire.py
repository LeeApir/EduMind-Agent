"""Finite head planning with explicit wire v2 to business plan v1 mapping."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.agents import free_course_planning as local
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from app.services.head_course_materials import EMPTY_GOAL, FIXED_VERSION
from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest

VERSION = "head-goal-planning-wire-v2"
PROMPT_VERSION = "head-goal-plan-grounded-v3"
SCHEMA = json.loads(Path(__file__).with_suffix(".schema.json").read_text())
INSTRUCTION = """[WIRE FORMAT head-goal-planning-wire-v2]
Return protocol_version exactly head-goal-planning-wire-v2. All fields are required.
Normal plan: needs_clarification=false, plans contains exactly one complete plan,
questions=[], reason="", source_keys=[].
Clarification: needs_clarification=true, plans=[], questions has 1–3 questions,
reason is requirements_conflict, required_material_missing or out_of_scope,
source_keys cites actual request sources. Do not output an empty or invented plan.
Objective user_requirement: source_key and source_excerpt are exact nonempty evidence.
Objective planner_suggestion: source_key="" and source_excerpt=""; no invented evidence.
These empty strings/empty plans are wire markers only. Do not omit fields or use null.
All original coverage, source, reference, support and clarification rules still apply.
Return only the supplied wire schema, without commentary or code fences."""
RESPONSIBILITY = """[PLANNING RESPONSIBILITY]
Plan learning objectives, choose one supplied example ID, and organize teaching order.
planning_example_basis is program-owned evidence from the exact shared code/trace version.
Use its function interface, variable names/scopes and receive/ignore-return state differences.
Do not design another implementation, invent algorithm steps, rename pointers, or add head=p.
If you mention operations or outcomes in objectives/conventions/purposes, they must agree with
the selected evidence. The local parameter head and main's caller_head are distinct variables.
Ignoring a returned new head preserves the old list entry in this nonempty example; explain
new allocated nodes' unreachability without claiming the old entry disappears.
Program supplies code, states and answers. You still generate the actual plan; these facts
are not an outline or teaching prose. Do not ask the learner to approve an internal plan.
Independent review checks semantic consistency; do not invent references or facts to pass."""


def build_request(inputs: dict[str, Any]) -> StructuredRequest:
    if "head_support" not in inputs:
        raise SnapshotError("HEAD_PLANNING_SCOPE_INVALID")
    original = local.build_request(inputs)
    fixed = inputs["head_support"]["version"] == FIXED_VERSION
    if fixed and (
        inputs["learner_evidence"]
        or inputs["profile_id"] is not None
        or inputs["profile_version"] is not None
    ):
        raise SnapshotError("HEAD_FIXED_PROFILE_NOT_EMPTY")
    from app.services.head_course_planning_basis import build_basis

    instruction = original.prompt.messages[0].content.replace(
        "Planner suggestions have null source_key/source_excerpt.",
        "Planner suggestions have empty-string source_key/source_excerpt on this wire.",
    )
    payload = json.loads(original.prompt.messages[1].content)
    payload["prompt_version"] = PROMPT_VERSION
    payload["wire_protocol"] = VERSION
    empty = inputs["original_goal"] == EMPTY_GOAL
    payload["planning_example_basis"] = build_basis(fixed=fixed, empty=empty)
    responsibility = RESPONSIBILITY
    if empty:
        responsibility = responsibility.replace(
            "Ignoring a returned new head preserves the old list entry in this nonempty example; "
            "explain\n"
            "new allocated nodes' unreachability without claiming the old entry disappears.",
            "The only supported example starts with caller_head=NULL and no initial node. Cover\n"
            "the first link to NULL, the second link to the first new node when returns are\n"
            "received, and the unchanged NULL caller entry when both returns are ignored.\n"
            "Do not describe lost references as automatic deallocation.",
        )
    return StructuredRequest(
        prompt=TextRequest(
            messages=(
                ChatMessage("system", instruction + "\n" + INSTRUCTION + "\n" + responsibility),
                ChatMessage("user", canonical(payload).decode()),
            ),
            task_profile=original.prompt.task_profile,
            max_output_tokens=original.prompt.max_output_tokens,
            temperature=original.prompt.temperature,
        ),
        json_schema=deepcopy(SCHEMA),
        stage=original.stage,
    )


def to_local(raw: Any, inputs: dict[str, Any]) -> dict[str, Any]:
    """Only map explicit representation markers; reject rather than discard active data."""
    local.snapshot_input(inputs)
    if "head_support" not in inputs:
        raise SnapshotError("HEAD_PLANNING_SCOPE_INVALID")
    try:
        if len(canonical(raw)) > 16384:
            raise ValueError()
        Draft202012Validator(SCHEMA).validate(raw)
        value = deepcopy(raw)
        plans = value["plans"]
        if value["needs_clarification"]:
            if plans:
                raise ValueError()
            plan = None
        else:
            if len(plans) != 1:
                raise ValueError()
            plan = plans[0]
            for objective in plan["objectives"]:
                if objective["source"] == "planner_suggestion":
                    if objective["source_key"] != "" or objective["source_excerpt"] != "":
                        raise ValueError()
                    objective["source_key"] = None
                    objective["source_excerpt"] = None
        result = dict(
            needs_clarification=value["needs_clarification"],
            plan=plan,
            questions=value["questions"],
            reason=None if value["reason"] == "" else value["reason"],
            source_keys=value["source_keys"],
        )
        # The full local schema + source/coverage/scope/reference checks remain authoritative.
        return local.validate_response(result, inputs)
    except Exception:
        raise SnapshotError("SCHEMA_INVALID") from None


def mapping_record(raw: Any, inputs: dict[str, Any]) -> dict[str, Any]:
    from app.services.head_course_planning_basis import build_basis

    value = to_local(raw, inputs)
    return dict(
        wire_version=VERSION,
        planning_prompt_version=PROMPT_VERSION,
        planning_basis_digest=build_basis(
            fixed=inputs["head_support"]["version"] == FIXED_VERSION,
            empty=inputs["original_goal"] == EMPTY_GOAL,
        )["basis_digest"],
        local_schema_version=local.SCHEMA_VERSION,
        wire_digest=digest("head-plan-wire", value=raw),
        local_digest=digest("head-plan-local", value=value),
        value=value,
    )
