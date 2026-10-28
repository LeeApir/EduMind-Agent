"""Handwritten schema forms, preserving the distinction between standards and endpoint evidence."""

from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest
from jsonschema import Draft202012Validator, SchemaError

from scripts.check_p15_schema_compatibility import PINS, verified_originals
from scripts.isolated_diagnostics.p15_schema_audit import (
    audit_schema, explicit_string_enum_proposal, schema_nodes,
)


def test_enum_only_is_standard_valid_but_not_proven_provider_accepted():
    result = audit_schema({"enum": ["a", "b"]})
    assert result["draft202012_schema_valid"] is True
    assert result["findings"] == [dict(
        pointer="", code="NO_TYPE_ANYOF_REF", evidence=["enum"],
        certainty="observed_form_not_server_cause",
    )]
    assert result["provider_acceptance_verified"] is False
    assert result["server_rejection_path_known"] is False


def test_boolean_schemas_are_leaves_not_missing_types():
    schema = {"type": "object", "additionalProperties": False}
    assert list(schema_nodes(schema)) == [("", schema), ("/additionalProperties", False)]
    assert audit_schema(schema)["findings"][0]["code"] == "OPEN_OBJECT_BRANCH"
    assert audit_schema(False)["findings"] == []


def test_walk_only_schema_positions_and_escape_json_pointer():
    schema = {"properties": {"a/b~": {"enum": ["x"]}},
              "enum": [{"properties": {"fake": {"enum": ["q"]}}}],
              "default": {"properties": {"fake": {}}}, "examples": [{"items": {}}]}
    assert [p for p, _ in schema_nodes(schema)] == ["", "/properties/a~1b~0"]


def test_structural_keywords_not_instance_values_are_visited():
    schema = {"$defs": {"x": {"type": "string"}},
              "anyOf": [{"$ref": "#/$defs/x"}, {"type": "null"}]}
    assert [p for p, _ in schema_nodes(schema)] == ["", "/$defs/x", "/anyOf/0", "/anyOf/1"]


@pytest.mark.parametrize("key,value", [("minLength", 1), ("maxLength", 8),
                                     ("minItems", 1), ("maxItems", 4)])
def test_tool_doc_rules_are_not_claimed_as_responses_rules(key, value):
    kind = "string" if "Length" in key else "array"
    schema = {"type": kind, key: value}
    if kind == "array":
        schema["items"] = {"type": "string"}
    result = audit_schema(schema)
    assert result["findings"] == [dict(pointer="/" + key,
        code="TOOL_STRICT_UNSUPPORTED_BOUND", evidence=value,
        certainty="tool_beta_doc_only_not_a_responses_rule")]


def test_open_branches_dynamic_keys_and_type_union_are_uncertain():
    schema = {"type": ["array", "object", "null"]}
    result = audit_schema(schema)
    assert [x["code"] for x in result["findings"]] == [
        "TYPE_ARRAY", "OPEN_OBJECT_BRANCH", "OPEN_ARRAY_BRANCH"]
    dynamic = {"type": "object", "patternProperties": {"^x/$": {"type": "string"}},
               "maxProperties": 2, "additionalProperties": False}
    assert [x["code"] for x in audit_schema(dynamic)["findings"]] == [
        "DYNAMIC_OBJECT_KEYWORD", "DYNAMIC_OBJECT_KEYWORD"]


@pytest.mark.parametrize("bad", [{"type": "mystery"}, {"enum": "a"}, {"properties": []}])
def test_invalid_standard_schema_does_not_produce_false_success(bad):
    with pytest.raises(SchemaError):
        audit_schema(bad)


def test_empty_enum_has_no_accepted_values_and_is_not_normalized():
    schema = {"enum": []}
    assert audit_schema(schema)["provider_acceptance_verified"] is False
    assert explicit_string_enum_proposal(schema) == (schema, [])
    assert not any(Draft202012Validator(schema).is_valid(v) for v in (None, "", 0, [], {}))


@pytest.mark.parametrize("value", ["a", "b", "other", "", None, 0, 1.5, True, [], {}, ["a"]])
def test_string_enum_type_addition_preserves_all_listed_values_and_negative_examples(value):
    original = {"enum": ["a", "b"], "description": "unchanged"}
    proposal, changes = explicit_string_enum_proposal(original)
    assert proposal == {**original, "type": "string"}
    assert original == {"enum": ["a", "b"], "description": "unchanged"}
    assert changes == ["/type"]
    assert Draft202012Validator(original).is_valid(value) == Draft202012Validator(proposal).is_valid(value)


@pytest.mark.parametrize("schema", [{"enum": ["a", None]}, {"enum": [1, 2]},
                                   {"const": "a"}, {"type": "string", "enum": ["a"]},
                                   True, False])
def test_proposal_does_not_rewrite_other_forms(schema):
    proposal, changes = explicit_string_enum_proposal(schema)
    assert proposal == schema
    assert changes == []


def test_proposal_preserves_bounds_and_never_walks_enum_object_data():
    original = {"type": "object", "properties": {"k": {"enum": ["a"]}},
                "required": ["k"], "additionalProperties": False,
                "$defs": {"data": {"enum": [{"properties": {"f": {"enum": ["x"]}}}]}},
                "maxProperties": 1}
    frozen = deepcopy(original)
    proposal, changes = explicit_string_enum_proposal(original)
    assert original == frozen
    assert changes == ["/properties/k/type"]
    del proposal["properties"]["k"]["type"]
    assert proposal == original


def test_frozen_request_has_exact_two_enum_locations_and_proposal_is_only_additive():
    original = verified_originals()["call-000-request.json"]["text"]["format"]["schema"]
    result = audit_schema(original, "/text/format/schema")
    assert result["schema_node_count"] == 36
    assert {x["pointer"] for x in result["findings"] if x["code"] == "NO_TYPE_ANYOF_REF"} == {
        "/text/format/schema/properties/actions/items/properties/kind",
        "/text/format/schema/properties/questions/items/properties/observation_key",
    }
    proposal, changes = explicit_string_enum_proposal(original)
    assert set(changes) == {"/properties/actions/items/properties/kind/type",
                            "/properties/questions/items/properties/observation_key/type"}
    del proposal["properties"]["actions"]["items"]["properties"]["kind"]["type"]
    del proposal["properties"]["questions"]["items"]["properties"]["observation_key"]["type"]
    assert proposal == original


def test_original_drift_refused_without_loading_credentials_or_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setenv("EDUMIND_DEEPSEEK_COMPAT_API_KEY", "never-read")
    for name in PINS:
        (tmp_path / name).write_text(json.dumps({}))
    with pytest.raises(ValueError, match="ORIGINAL_DRIFT"):
        verified_originals(tmp_path)


def test_symlink_original_refused(tmp_path):
    (tmp_path / "call-000-request.json").symlink_to(Path(__file__))
    with pytest.raises(ValueError, match="ORIGINAL_PATH_OR_SIZE"):
        verified_originals(tmp_path)
