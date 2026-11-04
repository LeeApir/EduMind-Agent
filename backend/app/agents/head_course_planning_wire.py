"""T108-only, explicit wire v2 -> unchanged business plan v1; never repair content."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.agents import free_course_planning as local
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest

VERSION = "head-goal-planning-wire-v2"
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


def build_request(inputs: dict[str, Any]) -> StructuredRequest:
    if "head_support" not in inputs:
        raise SnapshotError("HEAD_PLANNING_SCOPE_INVALID")
    original = local.build_request(inputs)
    instruction = original.prompt.messages[0].content.replace(
        "Planner suggestions have null source_key/source_excerpt.",
        "Planner suggestions have empty-string source_key/source_excerpt on this wire.",
    )
    payload = json.loads(original.prompt.messages[1].content)
    payload["prompt_version"] = VERSION
    payload["wire_protocol"] = VERSION
    return StructuredRequest(
        prompt=TextRequest(
            messages=(
                ChatMessage("system", instruction + "\n" + INSTRUCTION),
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
    value = to_local(raw, inputs)
    return dict(
        wire_version=VERSION,
        local_schema_version=local.SCHEMA_VERSION,
        wire_digest=digest("head-plan-wire", value=raw),
        local_digest=digest("head-plan-local", value=value),
        value=value,
    )
