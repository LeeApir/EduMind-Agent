"""Offline-only equivalent union proposal. No HTTP, credentials, or workflow entry."""

import json
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from scripts.isolated_diagnostics.p15_schema_audit import schema_nodes

VERSION = "union-anyof-proposal-v1"


def propose_anyof(schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Preserve siblings; replace type:[t1,...] by anyOf:[{type:t1},...].

    JSON Schema evaluates siblings conjunctively. Both representations accept a
    value iff a listed type matches and every original sibling constraint holds.
    Existing anyOf at the same node is refused rather than overwritten.
    """
    Draft202012Validator.check_schema(schema)
    # Wire Schema is a JSON tree. Break Python aliases so each occurrence gets
    # its own path and no later visit observes a sibling's in-place conversion.
    result: dict[str, Any] = json.loads(json.dumps(schema))
    changes = []
    # Materialize before adding branches so traversal only visits original nodes.
    for pointer, node in list(schema_nodes(result)):
        if not isinstance(node, dict) or not isinstance(node.get("type"), list):
            continue
        if "anyOf" in node:
            raise ValueError("EXISTING_ANYOF_REQUIRES_SEPARATE_PROPOSAL")
        types = node.pop("type")
        node["anyOf"] = [{"type": value} for value in types]
        changes.append(pointer)
    Draft202012Validator.check_schema(result)
    return result, changes


def minimal_schemas() -> dict[str, dict[str, Any]]:
    """Proposed matched forms; these are not executable requests or permission."""
    union = {"type": "object", "properties": {"value": {
        "type": ["string", "number", "boolean", "null", "array", "object"]}},
        "required": ["value"], "additionalProperties": False}
    anyof, _ = propose_anyof(union)
    return {"S1_anyof_control": anyof, "S2_type_union": union}
