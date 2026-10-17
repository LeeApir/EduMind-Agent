"""Versioned Qwen strict wire projection; full business validation stays local."""

from copy import deepcopy
from typing import Any

QWEN_SCHEMA_PROFILE = "qwen-strict-20261017-v1"
# Alibaba Model Studio strict-schema keyword table, checked 2026-10-17.
SUPPORTED = frozenset(
    "type enum const $defs $ref anyOf oneOf allOf not if then else title description "
    "default examples $schema $id $comment deprecated readOnly writeOnly minLength "
    "maxLength pattern format contentMediaType contentEncoding minimum maximum "
    "exclusiveMinimum exclusiveMaximum items prefixItems minItems maxItems "
    "unevaluatedItems properties required additionalProperties minProperties "
    "maxProperties dependentRequired dependentSchemas unevaluatedProperties".split()
)
MAPS = {"properties", "$defs", "dependentSchemas"}
SINGLES = {
    "items",
    "additionalProperties",
    "unevaluatedItems",
    "unevaluatedProperties",
    "not",
    "if",
    "then",
    "else",
}
LISTS = {"anyOf", "oneOf", "allOf", "prefixItems"}


def qwen_wire_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove only known local-only constraint; fail closed on unknown keywords/refs."""
    source = deepcopy(schema)
    definitions = source.pop("$defs", {})
    used: set[str] = set()

    def visit(node: Any) -> Any:
        if isinstance(node, bool):
            return node
        if not isinstance(node, dict):
            raise ValueError("INVALID_SCHEMA_NODE")
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key == "uniqueItems":
                continue  # Enforced by the original local Schema, never removed there.
            if key not in SUPPORTED:
                raise ValueError("UNSUPPORTED_SCHEMA_KEYWORD")
            if key == "$ref":
                if not isinstance(value, str) or not value.startswith("#/$defs/"):
                    raise ValueError("UNSUPPORTED_SCHEMA_REF")
                name = value[len("#/$defs/") :].split("/", 1)[0]
                name = name.replace("~1", "/").replace("~0", "~")
                if name not in definitions:
                    raise ValueError("MISSING_SCHEMA_DEFINITION")
                used.add(name)
            if key in MAPS:
                result[key] = {name: visit(child) for name, child in value.items()}
            elif key in SINGLES:
                result[key] = visit(value)
            elif key in LISTS:
                result[key] = [visit(child) for child in value]
            else:
                result[key] = deepcopy(value)
        return result

    output: dict[str, Any] = visit(source)
    kept: dict[str, Any] = {}
    while used - kept.keys():
        name = sorted(used - kept.keys())[0]
        # Mark before traversal so recursive references terminate.
        kept[name] = None
        kept[name] = visit(definitions[name])
    if kept:
        output["$defs"] = kept
    return output
