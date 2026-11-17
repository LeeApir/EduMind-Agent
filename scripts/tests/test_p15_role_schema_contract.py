"""Handwritten positive/negative literal examples and schema-only fixture checks."""

from copy import deepcopy
import json

import pytest
from jsonschema import Draft202012Validator

from scripts.isolated_diagnostics import p15_agent_pilot as teaching
from scripts.isolated_diagnostics import p15_role_schema_contract as c
from scripts.isolated_diagnostics.p15_head_insertion_engine import build_example
from scripts.isolated_diagnostics.p15_schema_audit import audit_schema


@pytest.mark.parametrize("schema", [{"enum": ["a", "b"]}, {"const": "a"},
    {"enum": ["a", "b"], "pattern": "^a$"},
    {"enum": ["a", 1], "const": "a"}])
@pytest.mark.parametrize("value", ["a", "b", "c", None, False, 1, 0.5, [], {}, ["a"]])
def test_explicit_string_type_preserves_acceptance(schema, value):
    frozen = deepcopy(schema)
    result, changes = c.explicit_literal_types(schema)
    assert schema == frozen
    assert result == {**schema, "type": "string"}
    assert changes == ["/type"]
    assert Draft202012Validator(schema).is_valid(value) == Draft202012Validator(result).is_valid(value)


@pytest.mark.parametrize("schema", [{"enum": ["a", None]}, {"const": 1}, {"const": False},
    {"type": "string", "enum": ["a"]}, {"anyOf": [{"enum": ["a"]}]}])
def test_no_other_rewrite_or_keyword_removal(schema):
    result, changes = c.explicit_literal_types(schema)
    if "anyOf" in schema:
        assert changes == ["/anyOf/0/type"]
        del result["anyOf"][0]["type"]
    else:
        assert changes == []
    assert result == schema


@pytest.mark.parametrize("name,count", [("S1", 5), ("S2", 1), ("S3", 4)])
def test_every_role_fixture_satisfies_original_and_only_type_additions(name, count):
    original = c.original_schemas()[name]
    frozen = deepcopy(original)
    wire, changes = c.explicit_literal_types(original)
    assert original == frozen and len(changes) == count
    assert Draft202012Validator(original).is_valid(c.FIXTURES[name])
    assert Draft202012Validator(wire).is_valid(c.FIXTURES[name])
    for pointer in changes:
        parts = pointer.split("/")[1:]
        value = wire
        for part in parts[:-1]:
            decoded = part.replace("~1", "/").replace("~0", "~")
            value = value[int(decoded)] if isinstance(value, list) else value[decoded]
        assert value.pop(parts[-1]) == "string"
    assert wire == original  # Every bound, keyword, enum and data-type union remains unchanged.
    assert not [x for x in audit_schema(c.explicit_literal_types(original)[0])["findings"]
                if x["code"] == "NO_TYPE_ANYOF_REF"]


def test_protocol_content_is_not_a_teaching_candidate():
    fixture = c.FIXTURES["S2"]
    teaching.check_schema(fixture, teaching.CONTENT_SCHEMA)
    example = build_example(c.FIXTURES["S1"]["spec"])
    with pytest.raises(teaching.PilotError, match="FACT_REFERENCE"):
        teaching.validate_content(fixture, example)
    with pytest.raises(teaching.PilotError, match="REVIEW_SOURCE"):
        teaching.validate_review(c.FIXTURES["S3"], {"synthetic": True})


def test_body_roles_models_reasoning_fixture_and_budget_are_frozen():
    bodies = c.bodies()
    assert set(bodies) == {"S1", "S2", "S3"}
    for name, raw in bodies.items():
        body = json.loads(raw)
        assert len(raw) <= 16384
        assert body["input"][0] == {"role": "system", "content": c.INSTRUCTION}
        assert json.loads(body["input"][1]["content"]) == c.FIXTURES[name]
        assert body["text"]["format"]["strict"] is True
        assert body["max_output_tokens"] == c.CAPS[name][1]
        assert body["reasoning"] == {"effort": "low" if name == "S3" else "none"}
        assert body["model"] == ("gpt-6.1-sol" if name == "S3" else "deepseek-flash")
        assert not ({"tools", "previous_response_id", "metadata", "instructions"} & set(body))
    assert sum(v[0] for v in c.CAPS.values()) == 24576
    assert sum(v[1] for v in c.CAPS.values()) == 8192


def test_all_changes_and_original_digests_have_explicit_inventory():
    inventory = c.schema_manifest()
    assert [len(inventory[n]["added_type_pointers"]) for n in c.ORDER] == [5, 1, 4]
    assert len({row["original_sha256"] for row in inventory.values()}) == 3
    assert all(row["original_sha256"] != row["wire_sha256"] for row in inventory.values())
