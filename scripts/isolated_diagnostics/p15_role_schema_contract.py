"""Schema-only fixtures and entailed literal types. No teaching prompt or production mutation."""

from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from scripts.isolated_diagnostics import p15_agent_pilot as pilot
from scripts.isolated_diagnostics.p15_schema_audit import schema_nodes
from scripts.isolated_diagnostics.p15_schema_probe_p02 import canonical, sha

VERSION = "role-schema-protocol-v1"
ORDER = ("S1", "S2", "S3")
ROLES = {"S1": "generation", "S2": "generation", "S3": "review"}
STAGES = {"S1": "C_plan", "S2": "C_content", "S3": "B_C_review"}
CAPS = {"S1": (8192, 2048), "S2": (8192, 2048), "S3": (8192, 4096)}
LIMITS = dict(requests=3, input_reservation=24576, output_reservation=8192, fee_cap=None,
              wall_seconds=300, per_request_seconds=90, dns_seconds=9,
              request_bytes=16384, response_bytes=65536)
INSTRUCTION = (
    "Synthetic protocol fixture only. Return exactly the JSON object in the user message, "
    "conforming to the supplied Schema. Do not evaluate teaching or infer learner facts. "
    "No tools, files, network, or course generation."
)

# Handwritten format examples, not courses or independently ratified teaching truth.
FIXTURES: dict[str, dict[str, Any]] = {
    "S1": {
        "objectives": ["trace_head", "trace_termination", "trace_values", "trace_failures"],
        "coverage": [
            {"objective": "trace_head", "observation_key": "caller_head"},
            {"objective": "trace_termination", "observation_key": "traversal_status"},
            {"objective": "trace_values", "observation_key": "reachable_prefix"},
            {"objective": "trace_failures", "observation_key": "allocation_failures"},
        ],
        "spec": {"version": "head-insertion-spec-v1", "initial_values": [], "insert_values": [0],
                 "variant": "normal", "allocation_success": [True]},
    },
    "S2": {
        "paragraphs": [{"key": "p1", "text": "Synthetic protocol fixture only.",
                        "fact_refs": [{"path": "/synthetic", "value": None}]}],
        "questions": [
            {"key": "q1", "stem": "Protocol fixture only.", "observation_key": "caller_head",
             "explanation": "No teaching evaluation.", "fact_refs": [{"path": "/synthetic", "value": None}]},
            {"key": "q2", "stem": "Protocol fixture only.", "observation_key": "traversal_status",
             "explanation": "No teaching evaluation.", "fact_refs": [{"path": "/synthetic", "value": None}]},
            {"key": "q3", "stem": "Protocol fixture only.", "observation_key": "reachable_prefix",
             "explanation": "No teaching evaluation.", "fact_refs": [{"path": "/synthetic", "value": None}]},
            {"key": "q4", "stem": "Protocol fixture only.", "observation_key": "allocation_failures",
             "explanation": "No teaching evaluation.", "fact_refs": [{"path": "/synthetic", "value": None}]},
        ],
    },
    "S3": {"source_digest": "0" * 64, "verdict": "unknown", "scope_status": "insufficient_evidence",
           "uncertain_reason": "Synthetic protocol fixture; no course was evaluated.", "issues": []},
}


def original_schemas() -> dict[str, dict[str, Any]]:
    return {"S1": deepcopy(pilot.PLAN_SCHEMA), "S2": deepcopy(pilot.CONTENT_SCHEMA),
            "S3": deepcopy(pilot.REVIEW_SCHEMA)}


def explicit_literal_types(schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Only add a string type already logically entailed by enum/const; remove nothing."""
    Draft202012Validator.check_schema(schema)
    result = deepcopy(schema)
    changed = []
    for pointer, node in schema_nodes(result):
        if not isinstance(node, dict) or any(k in node for k in ("type", "anyOf", "$ref")):
            continue
        string_enum = (isinstance(node.get("enum"), list) and bool(node["enum"])
                       and all(type(x) is str for x in node["enum"]))
        string_const = "const" in node and type(node["const"]) is str
        if string_enum or string_const:
            node["type"] = "string"
            changed.append(pointer + "/type")
    Draft202012Validator.check_schema(result)
    return result, changed


def bodies() -> dict[str, bytes]:
    from scripts.isolated_diagnostics.p15_pilot_wire import ROUTES
    result = {}
    for name, original in original_schemas().items():
        schema, _ = explicit_literal_types(original)
        Draft202012Validator(original).validate(FIXTURES[name])
        Draft202012Validator(schema).validate(FIXTURES[name])
        route = ROUTES[ROLES[name]]
        value = dict(model=route["model"], reasoning={"effort": route["reasoning"]},
                     temperature=0.2, stream=False, store=False, max_output_tokens=CAPS[name][1],
                     input=[dict(role="system", content=INSTRUCTION),
                            dict(role="user", content=canonical(FIXTURES[name]).decode())],
                     text={"format": dict(type="json_schema", name="edumind_agent_pilot", strict=True,
                                          schema=schema)})
        raw = canonical(value)
        if len(raw) > 16384:
            raise ValueError("ROLE_REQUEST_BYTES")
        result[name] = raw
    return result


def schema_manifest() -> dict[str, Any]:
    return {name: dict(stage=STAGES[name], role=ROLES[name],
                       original_sha256=sha(canonical(schema)),
                       wire_sha256=sha(canonical(explicit_literal_types(schema)[0])),
                       added_type_pointers=explicit_literal_types(schema)[1])
            for name, schema in original_schemas().items()}
