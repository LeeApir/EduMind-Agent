"""Handwritten accept/reject examples. No model calls or teaching truth labels."""

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from scripts.isolated_diagnostics import p15_role_schema_contract as roles
from scripts.isolated_diagnostics.p15_schema_audit import schema_nodes
from scripts.isolated_diagnostics.p15_union_schema_proposal import minimal_schemas, propose_anyof


@pytest.mark.parametrize("types,siblings,value,expected", [
    (["string", "null"], {"maxLength": 2}, None, True),
    (["string", "null"], {"maxLength": 2}, "ok", True),
    (["string", "null"], {"maxLength": 2}, "long", False),
    (["string", "null"], {}, False, False),
    (["integer", "boolean"], {"minimum": 0}, True, True),
    (["integer", "boolean"], {"minimum": 0}, 1.0, True),
    (["integer", "boolean"], {"minimum": 0}, 0.5, False),
    (["integer", "boolean"], {"minimum": 0}, -1, False),
    (["number", "null"], {"maximum": 2}, 2, True),
    (["number", "null"], {"maximum": 2}, 3, False),
    (["number", "null"], {}, False, False),
    (["number", "integer"], {}, 1, True),
    (["array", "null"], {"minItems": 1, "maxItems": 2,
                            "items": {"type": "integer"}}, [], False),
    (["array", "null"], {"minItems": 1, "maxItems": 2,
                            "items": {"type": "integer"}}, [1], True),
    (["array", "null"], {"maxItems": 2}, [1, 2, 3], False),
    (["array", "null"], {"items": {"type": "integer"}}, [True], False),
    (["array", "null"], {"uniqueItems": True}, [1, 1], False),
    (["object", "null"], {"properties": {"x": {"type": "integer"}},
                             "required": ["x"], "additionalProperties": False}, {"x": 1}, True),
    (["object", "null"], {"required": ["x"]}, {}, False),
    (["object", "null"], {"properties": {}, "additionalProperties": False}, {"x": 1}, False),
    (["object", "array"], {}, {"nested": [False, {"x": None}]}, True),
    (["object", "array"], {}, [None, {"nested": [1, "a"]}], True),
    (["object", "array"], {}, "text", False),
    (["string", "null"], {"enum": [None]}, "text", False),
    (["string", "null"], {"not": {"type": "null"}}, None, False),
])
def test_union_rewrite_preserves_handwritten_semantics(types, siblings, value, expected):
    original = {"type": types, **siblings}
    frozen = deepcopy(original)
    proposal, changes = propose_anyof(original)
    assert original == frozen and changes == [""]
    assert proposal == {**siblings, "anyOf": [{"type": t} for t in types]}
    assert Draft202012Validator(original).is_valid(value) is expected
    assert Draft202012Validator(proposal).is_valid(value) is expected


@pytest.mark.parametrize("name,count", [("S1", 0), ("S2", 2), ("S3", 1)])
def test_exact_role_constraints_reconstruct_original(name, count):
    original = roles.explicit_literal_types(roles.original_schemas()[name])[0]
    frozen = deepcopy(original)
    proposed, changes = propose_anyof(original)
    assert original == frozen and len(changes) == count
    assert Draft202012Validator(proposed).is_valid(roles.FIXTURES[name])
    for pointer in changes:
        node = proposed
        for part in pointer.split("/")[1:]:
            part = part.replace("~1", "/").replace("~0", "~")
            node = node[int(part)] if isinstance(node, list) else node[part]
        branches = node.pop("anyOf")
        assert all(set(branch) == {"type"} for branch in branches)
        node["type"] = [branch["type"] for branch in branches]
    assert proposed == original  # No keyword/bound/property/required/type removed.


@pytest.mark.parametrize("value", [None, "text", 2, 0.5, False, [], [None, {"x": [1]}],
                                 {}, {"x": [None, True, {"a": "b"}]}])
def test_real_content_open_values_stay_open(value):
    original = roles.explicit_literal_types(roles.original_schemas()["S2"])[0]
    proposed, _ = propose_anyof(original)
    candidate = deepcopy(roles.FIXTURES["S2"])
    candidate["paragraphs"][0]["fact_refs"][0]["value"] = value
    candidate["questions"][0]["fact_refs"][0]["value"] = value
    assert Draft202012Validator(original).is_valid(candidate)
    assert Draft202012Validator(proposed).is_valid(candidate)


@pytest.mark.parametrize("mutation", ["missing_questions", "short_questions", "long_questions",
                                      "extra_property", "bad_reference", "empty_text"])
def test_real_content_still_rejects_original_violations(mutation):
    original = roles.explicit_literal_types(roles.original_schemas()["S2"])[0]
    proposed, _ = propose_anyof(original)
    candidate = deepcopy(roles.FIXTURES["S2"])
    if mutation == "missing_questions":
        del candidate["questions"]
    elif mutation == "short_questions":
        candidate["questions"].pop()
    elif mutation == "long_questions":
        candidate["questions"].append(deepcopy(candidate["questions"][0]))
    elif mutation == "extra_property":
        candidate["extra"] = 1
    elif mutation == "bad_reference":
        del candidate["paragraphs"][0]["fact_refs"][0]["value"]
    else:
        candidate["paragraphs"][0]["text"] = ""
    assert not Draft202012Validator(original).is_valid(candidate)
    assert not Draft202012Validator(proposed).is_valid(candidate)


def test_existing_anyof_is_never_overwritten():
    original = {"type": ["string", "null"], "anyOf": [{"const": "ok"}, {"const": None}]}
    frozen = deepcopy(original)
    with pytest.raises(ValueError, match="EXISTING_ANYOF"):
        propose_anyof(original)
    assert original == frozen


def test_minimal_comparison_changes_only_equivalent_type_representation():
    examples = minimal_schemas()
    control = deepcopy(examples["S1_anyof_control"])
    union = examples["S2_type_union"]
    value_schema = control["properties"]["value"]
    value_schema["type"] = [x["type"] for x in value_schema.pop("anyOf")]
    assert control == union
    for schema in examples.values():
        validator = Draft202012Validator(schema)
        assert validator.is_valid({"value": None})
        assert validator.is_valid({"value": [None, {"arbitrary": [1, True]}]})
        assert not validator.is_valid({"value": None, "extra": 1})


def test_schema_traversal_never_rewrites_instance_data():
    original = {"type": "object", "const": {"type": ["array", "object"]}}
    assert propose_anyof(original) == (original, [])
    assert not [p for p, n in schema_nodes(original) if p.startswith("/const")]
