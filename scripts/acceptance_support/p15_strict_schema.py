"""Versioned wire projection. The unchanged complete local schema remains authoritative.

The wire schema is deliberately an over-approximation, not an equivalent replacement.
Every delegated constraint is recorded, supplied as trusted guidance and validated locally.
Only known keywords and local definition refs are admitted; unknown constructs fail closed.
"""

import json
import re
from copy import deepcopy

from jsonschema import Draft202012Validator

VERSION = "p15-strict-wire-v1"
WIRE = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "anyOf",
    "items",
    "$defs",
    "$ref",
    "description",
    "minItems",
    "maxItems",
}
LOCAL = {
    "allOf",
    "if",
    "then",
    "else",
    "contains",
    "minContains",
    "uniqueItems",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
}
ANNOTATIONS = {"$schema", "x-internal"}
KNOWN = WIRE | LOCAL | ANNOTATIONS | {"oneOf", "const"}
SINGLE = {"items", "contains", "if", "then", "else"}
MULTI = {"anyOf", "oneOf", "allOf"}
MAPS = {"properties", "$defs"}


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def pointer(path, key):
    return path + "/" + str(key).replace("~", "~0").replace("/", "~1")


def audit_original(node, definitions):
    if not isinstance(node, dict) or set(node) - KNOWN:
        raise ValueError("UNSUPPORTED_SCHEMA_CONSTRUCT")
    for key, value in node.items():
        if key == "$ref":
            if not isinstance(value, str) or not re.fullmatch(
                r"#/\$defs/[A-Za-z][A-Za-z0-9_]*", value
            ):
                raise ValueError("LOCAL_DEFINITION_REF_REQUIRED")
            if value.removeprefix("#/$defs/") not in definitions:
                raise ValueError("UNKNOWN_DEFINITION")
        elif key in MAPS:
            for child in value.values():
                audit_original(child, definitions)
        elif key in MULTI:
            for child in value:
                audit_original(child, definitions)
        elif key in SINGLE:
            audit_original(value, definitions)


def json_type(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is str:
        return "string"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    raise ValueError("ONLY_SCALAR_ENUMS_SUPPORTED")


def project(original):
    """Return wire schema and exhaustive projection/delegation map without mutation."""
    Draft202012Validator.check_schema(original)
    audit_original(original, original.get("$defs", {}))
    if original.get("type") != "object" or "anyOf" in original or "oneOf" in original:
        raise ValueError("ROOT_OBJECT_REQUIRED")
    changes = []

    def visit(node, path):
        out = {}
        for key, value in node.items():
            here = pointer(path, key)
            if key in LOCAL or key in ANNOTATIONS:
                changes.append(
                    dict(
                        path=here,
                        action="local_validation" if key in LOCAL else "annotation_only",
                        original=value,
                    )
                )
            elif key in MAPS:
                out[key] = {
                    name: visit(child, pointer(here, name)) for name, child in value.items()
                }
            elif key in {"anyOf", "oneOf"}:
                if "anyOf" in out:
                    raise ValueError("AMBIGUOUS_UNION")
                out["anyOf"] = [visit(child, pointer(here, i)) for i, child in enumerate(value)]
                if key == "oneOf":
                    changes.append(
                        dict(path=here, action="union_projection_local_oneOf", original=value)
                    )
            elif key == "const":
                if "enum" in node or "type" in node:
                    raise ValueError("UNSUPPORTED_CONST_SIBLINGS")
                out.update(type=json_type(value), enum=[deepcopy(value)])
                changes.append(dict(path=here, action="equivalent_scalar_enum", original=value))
            elif key == "items":
                out[key] = visit(value, here)
            else:
                out[key] = deepcopy(value)
        if "enum" in out and "type" not in out:
            types = sorted({json_type(v) for v in out["enum"]}, key=lambda t: (t == "null", t))
            out["type"] = types[0] if len(types) == 1 else types
        if out.get("type") == "object":
            if out.get("additionalProperties") is not False or set(
                out.get("properties", {})
            ) != set(out.get("required", [])):
                raise ValueError("ALL_OBJECT_FIELDS_REQUIRED_AND_CLOSED")
        return out

    wire = visit(original, "")
    Draft202012Validator.check_schema(wire)
    validate_wire(wire)
    return wire, changes


def validate_wire(schema):
    """Offline admission for our conservative documented subset, not a relay guarantee."""

    def visit(node, root=False):
        if not isinstance(node, dict) or set(node) - WIRE:
            raise ValueError("WIRE_KEYWORD_OUTSIDE_FROZEN_SUBSET")
        if root and (node.get("type") != "object" or "anyOf" in node):
            raise ValueError("WIRE_ROOT_OBJECT_REQUIRED")
        if node.get("type") == "object":
            if node.get("additionalProperties") is not False or set(
                node.get("properties", {})
            ) != set(node.get("required", [])):
                raise ValueError("WIRE_OBJECT_NOT_CLOSED_REQUIRED")
        for key, value in node.items():
            if key in MAPS:
                for child in value.values():
                    visit(child)
            elif key == "anyOf":
                for child in value:
                    visit(child)
            elif key == "items":
                visit(value)

    visit(schema, True)


def guidance(original):
    return (
        "Wire projection version " + VERSION + ". The complete original JSON Schema below is "
        "binding, including conditionals, lengths, uniqueness, required text, "
        "and action constraints. The wire subset does not replace it. "
        "Return only an object satisfying the original schema. "
        "All original request evidence and safety rules still apply. Original schema:\n"
        + canonical(original)
    )
