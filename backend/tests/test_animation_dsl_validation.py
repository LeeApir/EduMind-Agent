"""Approved fixtures plus independent JSON, limits, state and hostile-input boundaries."""

import copy
import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.services.animation_dsl_validation import (
    CONTRACT,
    POLICY_SHA256,
    SCHEMA_SHA256,
    VALIDATOR_SHA256,
    DSLValidationError,
    validate_animation_dsl,
)

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "docs/agents/animation-dsl-v1"
BASE = json.loads((FIXTURES / "valid-all-actions.json").read_text())
CASES = json.loads((FIXTURES / "invalid-examples.json").read_text())["cases"]


def validate(candidate):
    return validate_animation_dsl(
        json.dumps(candidate, ensure_ascii=False), knowledge_point_id="arrays"
    )


def reject(candidate, code, index=None):
    with pytest.raises(DSLValidationError) as error:
        validate(candidate)
    assert error.value.code == code and str(error.value) == code
    if index is not None:
        assert error.value.action_index == index
    return error.value


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_all_approved_negative_examples_at_their_declared_layer(case):
    if case["expected_layer"] == "review":
        # Local validity cannot replace factual review; these must remain candidates.
        result = validate(case["candidate"])
        assert result.duration_ms == 30800
        assert not hasattr(result, "review_passed")
    else:
        reject(case["candidate"], case["expected_code"])


def test_nine_action_trajectory_and_source_provenance_are_immutable():
    result = validate(BASE)
    assert result.duration_ms == 30800 and len(result.frames) == 11
    assert len({frame.op for frame in result.frames}) == 9
    assert result.frames[5].comparison.result == "gt"
    assert result.frames[6].comparison is None
    before, after = result.frames[5], result.frames[6]
    assert [n.value for n in before.nodes] == [3, 1]
    assert [n.value for n in after.nodes] == [1, 3]
    assert [(n.id, n.column, n.row, n.style) for n in before.nodes] == [
        (n.id, n.column, n.row, n.style) for n in after.nodes
    ]
    assert before.edges == after.edges and before.pointers == after.pointers
    assert result.frames[7].nodes[1].visited
    assert not result.frames[8].edges
    assert result.frames[9].pointers[0].target is None
    assert result.frames[10].complexity == ("O(1)", "O(1)")
    assert [f.start_ms for f in result.frames[1:]] == [f.end_ms for f in result.frames[:-1]]
    manifest = json.loads((FIXTURES / "proposal-manifest.json").read_text())
    assert SCHEMA_SHA256 == manifest["files"]["docs/agents/animation-dsl-v1/schema.json"]
    assert POLICY_SHA256 == hashlib.sha256((CONTRACT / "policy.json").read_bytes()).hexdigest()
    assert (
        VALIDATOR_SHA256
        == hashlib.sha256(
            (ROOT / "backend/app/services/animation_dsl_validation.py").read_bytes()
        ).hexdigest()
    )
    assert result.dsl_sha256 == hashlib.sha256(result.canonical_json.encode()).hexdigest()
    assert result.trace_sha256 == hashlib.sha256(result.trace_json.encode()).hexdigest()
    changed = result.candidate
    changed["title"] = "changed"
    assert result.candidate == BASE
    with pytest.raises(FrozenInstanceError):
        result.frames[0].nodes[0].value = 9
    reordered = {k: BASE[k] for k in reversed(BASE)}
    assert validate(reordered) == result


@pytest.mark.parametrize(
    "raw",
    [
        b"\xef\xbb\xbf{}",
        b"\xff",
        '{"x":1,"x":2}',
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":-Infinity}',
        "{}{}",
        "[]",
        "null",
        "{} trailing",
        "{",
        '{"title":"\\ud800"}',
        '{"x":{"a":1,"a":2}}',
    ],
)
def test_strict_json_rejects_invalid_encoding_constants_duplicates_and_extra_values(raw):
    with pytest.raises(DSLValidationError, match="^DSL_SCHEMA_INVALID$"):
        validate_animation_dsl(raw, knowledge_point_id="arrays")


@pytest.mark.parametrize("field", ["value", "column", "row", "duration_ms", "hold_ms"])
@pytest.mark.parametrize("value", [True, False, 1.0, None, "1", [], {}])
def test_every_integer_field_has_strict_json_integer_type(field, value):
    candidate = copy.deepcopy(BASE)
    candidate["actions"][0][field] = value
    reject(candidate, "DSL_SCHEMA_INVALID", 0)


@pytest.mark.parametrize(
    "value", ["", "  ", "x\n", "x\t", "x\x00", "x\u200b", "x\u202e", "e\u0301"]
)
@pytest.mark.parametrize("location", ["title", "label", "caption", "id"])
def test_text_normalization_controls_and_empty_strings(value, location):
    candidate = copy.deepcopy(BASE)
    if location == "title":
        candidate["title"] = value
    elif location == "label":
        candidate["pointers"][0]["label"] = value
    else:
        candidate["actions"][0][location] = value
    reject(candidate, "DSL_SCHEMA_INVALID")


def action(op="show_complexity", **values):
    result = dict(
        op=op, time="O(1)", space="O(1)", duration_ms=2000, hold_ms=3000, caption="固定步骤"
    )
    if op != "show_complexity":
        result.pop("time")
        result.pop("space")
    result.update(values)
    return result


def candidate(actions, pointers=None):
    return {**BASE, "actions": actions, "pointers": pointers or []}


@pytest.mark.parametrize(
    "milliseconds,valid", [(29800, False), (30000, True), (90000, True), (90200, False)]
)
def test_exact_total_duration_boundaries(milliseconds, valid):
    actions = [action() for _ in range(milliseconds // 5000)]
    rest = milliseconds % 5000
    if rest:
        actions.append(action(duration_ms=min(rest, 2000), hold_ms=max(0, rest - 2000)))
    data = candidate(actions)
    if valid:
        assert validate(data).duration_ms == milliseconds
    else:
        reject(data, "DSL_RESOURCE_LIMIT")


def test_byte_and_depth_limits_before_parsing_and_quoted_brackets():
    raw = json.dumps(BASE, ensure_ascii=False).encode()
    assert validate_animation_dsl(raw + b" " * (65536 - len(raw)), knowledge_point_id="arrays")
    with pytest.raises(DSLValidationError, match="DSL_RESOURCE_LIMIT"):
        validate_animation_dsl(raw + b" " * (65537 - len(raw)), knowledge_point_id="arrays")
    with pytest.raises(DSLValidationError, match="DSL_RESOURCE_LIMIT"):
        validate_animation_dsl("[" * 13 + "0" + "]" * 13, knowledge_point_id="arrays")
    data = copy.deepcopy(BASE)
    data["title"] = '{"literal":"\\\\"}' * 3
    assert validate(data)
    data["title"] = "🧠" * 80
    assert validate(data)
    data["title"] += "🧠"
    reject(data, "DSL_SCHEMA_INVALID")


def test_ids_types_active_edges_cycles_and_cumulative_edge_limit():
    nodes = [
        action("create_node", id="a", value=0, column=0, row=0),
        action("create_node", id="b", value=1, column=1, row=0),
    ]
    connect = action("connect", id="e", source="a", target="b")
    disconnect = action("disconnect", edge="e")
    prefix = nodes + [connect, action("connect", id="back", source="b", target="a")]
    assert validate(candidate(prefix + [action(), action()])).frames[3].edges[1].target == "a"
    reject(candidate(nodes + [connect, connect] + [action(), action()]), "DSL_REFERENCE_INVALID", 3)
    reject(candidate(nodes + [connect, disconnect, connect, action()]), "DSL_REFERENCE_INVALID", 4)
    reject(
        candidate(nodes + [action("connect", id="e", source="a", target="a")] + [action()] * 3),
        "DSL_REFERENCE_INVALID",
        2,
    )
    reject(
        candidate(
            nodes + [action("visit", node="p")] + [action()] * 3, [{"id": "p", "label": "p"}]
        ),
        "DSL_REFERENCE_INVALID",
        2,
    )
    # Disconnecting never replenishes the lifetime quota. Distinct historical IDs.
    actions = [action("create_node", id="a", value=0, column=0, row=0)]
    for i in range(17):
        actions.extend(
            [
                action("connect", id=f"e{i}", source="a", target=None),
                action("disconnect", edge=f"e{i}"),
            ]
        )
    for a in actions:
        a.update(duration_ms=1000, hold_ms=0)
    reject(candidate(actions), "DSL_RESOURCE_LIMIT", 33)
    assert validate(candidate(actions[:-2])).duration_ms == 33000


def test_node_pointer_action_limits_and_schema_error_priority():
    nodes = [action("create_node", id=f"n{i}", value=i, column=i, row=0) for i in range(8)]
    assert len(validate(candidate(nodes)).frames[-1].nodes) == 8
    reject(
        candidate(nodes + [action("create_node", id="n8", value=0, column=0, row=1)]),
        "DSL_RESOURCE_LIMIT",
        8,
    )
    pointers = [{"id": f"p{i}", "label": "p"} for i in range(4)]
    assert len(validate(candidate([action()] * 6, pointers)).frames[0].pointers) == 4
    reject(candidate([action()] * 6, pointers + [{"id": "p4", "label": "p"}]), "DSL_RESOURCE_LIMIT")
    actions = [action(duration_ms=200, hold_ms=200) for _ in range(120)]
    assert len(validate(candidate(actions)).frames) == 120
    reject(candidate(actions + [actions[0]]), "DSL_RESOURCE_LIMIT")
    invalid = candidate(actions + [actions[0]])
    invalid["unknown"] = "SECRET_SENTINEL"
    error = reject(invalid, "DSL_SCHEMA_INVALID")
    assert "SECRET_SENTINEL" not in repr(error) and error.args == ("DSL_SCHEMA_INVALID",)


def test_target_mismatch_and_literal_code_are_not_executed(tmp_path, monkeypatch):
    data = copy.deepcopy(BASE)
    marker = tmp_path / "must-not-exist"
    monkeypatch.chdir(tmp_path)
    data["actions"][5]["caption"] = '__import__("pathlib").Path("must-not-exist").touch()'
    assert validate(data).frames[5].caption == data["actions"][5]["caption"]
    assert not marker.exists()
    with pytest.raises(DSLValidationError, match="DSL_REFERENCE_INVALID"):
        validate_animation_dsl(json.dumps(data), knowledge_point_id="linked-lists")
    data["actions"][0]["path"] = "../../secret"
    reject(data, "DSL_SCHEMA_INVALID", 0)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("value", -1000),
        ("value", 1000),
        ("column", -1),
        ("column", 8),
        ("row", -1),
        ("row", 3),
        ("duration_ms", 0),
        ("duration_ms", 2200),
        ("duration_ms", 300),
        ("hold_ms", -200),
        ("hold_ms", 3200),
        ("hold_ms", 100),
        ("caption", "x" * 161),
    ],
)
def test_scalar_ranges_and_time_quantization(field, bad):
    data = copy.deepcopy(BASE)
    data["actions"][0][field] = bad
    reject(data, "DSL_SCHEMA_INVALID", 0)


@pytest.mark.parametrize("op", sorted({a["op"] for a in BASE["actions"]}))
def test_all_action_shapes_reject_extra_code_and_missing_caption(op):
    data = copy.deepcopy(BASE)
    index = next(i for i, a in enumerate(data["actions"]) if a["op"] == op)
    data["actions"][index]["python"] = "SECRET_SENTINEL"
    error = reject(data, "DSL_SCHEMA_INVALID", index)
    assert "SECRET_SENTINEL" not in str(error)
    del data["actions"][index]["python"]
    del data["actions"][index]["caption"]
    reject(data, "DSL_SCHEMA_INVALID", index)


def test_global_ids_duplicate_active_pairs_and_dead_edges():
    data = copy.deepcopy(BASE)
    data["pointers"].append(dict(data["pointers"][0]))
    reject(data, "DSL_REFERENCE_INVALID")
    data = copy.deepcopy(BASE)
    data["actions"][0]["id"] = "p"
    reject(data, "DSL_REFERENCE_INVALID", 0)
    data = copy.deepcopy(BASE)
    data["actions"].insert(3, action("connect", id="other", source="n0", target="n1"))
    reject(data, "DSL_REFERENCE_INVALID", 3)
    data = copy.deepcopy(BASE)
    data["actions"].insert(9, action("highlight", object="e0", style="focus"))
    reject(data, "DSL_REFERENCE_INVALID", 9)
    data = copy.deepcopy(BASE)
    data["actions"][2]["source"] = "p"
    reject(data, "DSL_REFERENCE_INVALID", 2)


@pytest.mark.parametrize("left,right,result", [(1, 2, "lt"), (2, 2, "eq"), (3, 1, "gt")])
def test_comparison_is_derived_and_swap_keeps_identity_marks_and_pointers(left, right, result):
    data = copy.deepcopy(BASE)
    data["actions"][0]["value"] = left
    data["actions"][1]["value"] = right
    data["actions"].insert(5, action("visit", node="n0"))
    validated = validate(data)
    before, after = validated.frames[6:8]
    assert before.comparison.result == result and after.comparison is None
    assert before.nodes[0].visited and after.nodes[0].visited
    assert after.nodes[0].style == "focus"
    assert [node.value for node in after.nodes] == [right, left]
    assert before.pointers == after.pointers and before.edges == after.edges
