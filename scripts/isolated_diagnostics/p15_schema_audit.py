"""Offline schema inventory; findings are not a provider validator or a wire adapter."""

from copy import deepcopy
from typing import Any, Iterator

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

VERSION = "p15-schema-audit-v1"
MAP_CHILDREN = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")
SINGLE_CHILDREN = (
    "items", "additionalProperties", "unevaluatedProperties", "unevaluatedItems",
    "contains", "propertyNames", "not", "if", "then", "else", "contentSchema",
)
LIST_CHILDREN = ("allOf", "anyOf", "oneOf", "prefixItems")


def token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def schema_nodes(schema: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Visit schema locations only, never enum/default/example instance data."""
    yield path, schema
    if not isinstance(schema, dict):
        return
    for key in MAP_CHILDREN:
        for name, child in schema.get(key, {}).items():
            yield from schema_nodes(child, path + "/" + key + "/" + token(name))
    for key in SINGLE_CHILDREN:
        if key in schema:
            yield from schema_nodes(schema[key], path + "/" + key)
    for key in LIST_CHILDREN:
        for index, child in enumerate(schema.get(key, [])):
            yield from schema_nodes(child, path + "/" + key + "/" + str(index))


def audit_schema(schema: Any, path: str = "") -> dict[str, Any]:
    Draft202012Validator.check_schema(schema)
    nodes = list(schema_nodes(schema, path))
    findings: list[dict[str, Any]] = []

    def add(pointer: str, code: str, evidence: Any, certainty: str) -> None:
        findings.append(dict(pointer=pointer, code=code, evidence=evidence, certainty=certainty))

    for pointer, node in nodes:
        if isinstance(node, bool):
            # additionalProperties:false is a schema position, not a missing-type error.
            continue
        if not any(k in node for k in ("type", "anyOf", "$ref")):
            add(pointer, "NO_TYPE_ANYOF_REF", sorted(node), "observed_form_not_server_cause")
        types = node.get("type", [])
        if isinstance(types, str):
            types = [types]
        elif types:
            add(pointer, "TYPE_ARRAY", types, "responses_subset_undocumented")
        for key in ("minLength", "maxLength", "minItems", "maxItems"):
            if key in node:
                add(pointer + "/" + key, "TOOL_STRICT_UNSUPPORTED_BOUND", node[key],
                    "tool_beta_doc_only_not_a_responses_rule")
        for key in ("patternProperties", "maxProperties"):
            if key in node:
                add(pointer + "/" + key, "DYNAMIC_OBJECT_KEYWORD", node[key],
                    "responses_subset_undocumented")
        if "object" in types and not any(k in node for k in ("properties", "patternProperties")):
            add(pointer, "OPEN_OBJECT_BRANCH", types, "observed_form_strict_scope_unverified")
        if "array" in types and "items" not in node:
            add(pointer, "OPEN_ARRAY_BRANCH", types, "observed_form_strict_scope_unverified")
    return dict(
        draft202012_schema_valid=True,
        schema_node_count=len(nodes),
        findings=findings,
        provider_acceptance_verified=False,
        server_rejection_path_known=False,
    )


def explicit_string_enum_proposal(schema: Any) -> tuple[Any, list[str]]:
    """Proof-limited copy: enum of strings already entails string type. Never used at runtime."""
    Draft202012Validator.check_schema(schema)
    proposal = deepcopy(schema)
    changes = []
    for pointer, node in schema_nodes(proposal):
        if (
            isinstance(node, dict)
            and "type" not in node
            and isinstance(node.get("enum"), list)
            and node["enum"]
            and all(type(value) is str for value in node["enum"])
        ):
            node["type"] = "string"
            changes.append(pointer + "/type")
    Draft202012Validator.check_schema(proposal)
    return proposal, changes
