"""Semantics-preserving review-only wire normalization; full original validation remains local."""

from copy import deepcopy
from dataclasses import replace

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.provider_gateway import (
    OutputFailureReason,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
)

PROFILE = "luna-review-explicit-string-types-reachable-defs-v1"
MAPS = ("properties", "$defs")
LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")
SINGLES = ("items", "additionalProperties", "not", "if", "then", "else")


def schema_nodes(schema, path=()):
    """Visit Schema nodes, never property-name maps or enum data as Schema."""
    if not isinstance(schema, dict):
        return
    yield path, schema
    for key in MAPS:
        for name, child in schema.get(key, {}).items():
            yield from schema_nodes(child, (*path, key, name))
    for key in LISTS:
        for index, child in enumerate(schema.get(key, [])):
            yield from schema_nodes(child, (*path, key, index))
    for key in SINGLES:
        if isinstance(schema.get(key), dict):
            yield from schema_nodes(schema[key], (*path, key))


def projection(schema):
    """Only fixed review schema: add redundant string types and prune unused local defs.

    No keywords/constraints, including uniqueItems, are removed from reachable schemas.
    Pure $ref nodes remain references, not incorrectly reported as missing types.
    """
    Draft202012Validator.check_schema(schema)
    source = deepcopy(schema)
    if (
        source.get("type") != "object"
        or source.get("properties", {}).get("schema_version") != {"const": "resource-review-v4"}
        or source.get("properties", {}).get("scope", {}).get("const") not in {"unit", "resource"}
    ):
        raise ValueError("NOT_REVIEW_SCHEMA")
    defs = source.pop("$defs", {})
    needed = set()

    def refs(node):
        for _, child in schema_nodes(node):
            if "$ref" not in child:
                continue
            ref = child["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/$defs/") or "/" in ref[8:]:
                raise ValueError("UNSUPPORTED_REFERENCE")
            name = ref[8:].replace("~1", "/").replace("~0", "~")
            if name not in defs:
                raise ValueError("MISSING_DEFINITION")
            needed.add(name)

    refs(source)
    kept = {}
    while needed - kept.keys():
        name = sorted(needed - kept.keys())[0]
        kept[name] = deepcopy(defs[name])
        refs(kept[name])
    if kept:
        source["$defs"] = kept
    changes = []
    for path, node in schema_nodes(source):
        if "type" in node or not ("const" in node or "enum" in node):
            continue
        values = [node["const"]] if "const" in node else node["enum"]
        if not values or not all(type(v) is str for v in values):
            raise ValueError("UNSUPPORTED_UNTYPED_ENUM")
        node["type"] = "string"
        changes.append(list(path))
    Draft202012Validator.check_schema(source)
    return source, {
        "profile": PROFILE,
        "added_string_type_paths": changes,
        "retained_definitions": sorted(kept),
        "pruned_definitions": sorted(set(defs) - set(kept)),
        "removed_reachable_constraints": [],
        "strict_parameter_changed": False,
    }


class ProjectedReviewAdapter(DeepSeekResponsesAdapter):
    """Actually sends normalized Schema via existing adapter; checks original on response."""

    async def generate_structured(self, request):
        original = deepcopy(dict(request.json_schema))
        wire_schema, _ = projection(original)
        result = await super().generate_structured(StructuredRequest(request.prompt, wire_schema))
        try:
            Draft202012Validator(original).validate(dict(result.value))
        except ValidationError as exc:
            keyword = (
                exc.validator
                if exc.validator
                in {
                    "type",
                    "required",
                    "additionalProperties",
                    "const",
                    "enum",
                    "minLength",
                    "maxLength",
                    "minItems",
                    "maxItems",
                    "uniqueItems",
                    "pattern",
                }
                else "other"
            )
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.STRUCTURED_SCHEMA_MISMATCH,
                schema_keyword=keyword,
                usage=result.usage,
            ) from None
        # The audit is emitted from the ACTUAL normalized request by _response, unchanged.
        return replace(result, value=deepcopy(dict(result.value)))
