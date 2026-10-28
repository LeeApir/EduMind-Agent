"""Hand-derived expectations plus metamorphic boundaries, not engine-generated truth."""

import copy
import itertools
import json
from pathlib import Path

import pytest

from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    SpecError,
    answer,
    build_actions,
    build_example,
    digest,
    validate_spec,
)

ROOT = Path(__file__).resolve().parents[2]
SEEDS = json.loads(
    (
        ROOT / "docs/acceptance/phase-1.5-agent-pilot/contract-r01/examples.json"
    ).read_text()
)["cases"]


def spec(initial=None, values=None, variant="normal", mask=None):
    values = [1, 2] if values is None else values
    return dict(
        version="head-insertion-spec-v1",
        initial_values=initial or [],
        insert_values=values,
        variant=variant,
        allocation_success=[True] * len(values) if mask is None else mask,
    )


@pytest.mark.parametrize("case", SEEDS, ids=[s["id"] for s in SEEDS])
def test_hand_calculated_seeds(case):
    assert build_example(case["spec"])["observation"] == case["expected"]


@pytest.mark.parametrize(
    "initial,values",
    [
        ([], [1]),
        ([], [3, 2, 1]),
        ([5], [5, 5]),
        ([-1, -2], [-3, 0]),
        ([1, 2, 3], [4, 5, 6, 7]),
    ],
)
def test_normal_reverse_successful_values(initial, values):
    for mask in itertools.product((True, False), repeat=len(values)):
        e = build_example(spec(initial, values, mask=list(mask)))
        successful = [v for v, ok in zip(values, mask) if ok]
        assert e["observation"]["reachable_prefix"] == successful[::-1] + initial
        assert e["observation"]["traversal_status"] == "terminated"
        assert not e["observation"]["unreachable_allocated_ids"]


@pytest.mark.parametrize(
    "variant", ["normal", "reversed_assignment", "discard_return", "uninitialized_next"]
)
def test_all_failed_preserves_original(variant):
    e = build_example(spec([7, 8], [1, 2, 3, 4], variant, [False] * 4))
    assert e["observation"] == dict(
        caller_head="i0",
        reachable_prefix=[7, 8],
        traversal_status="terminated",
        cycle_entry=None,
        allocation_failures=4,
        unreachable_allocated_ids=[],
    )
    assert not any(s["phase"] == "data" for s in e["trace"]["steps"])


@pytest.mark.parametrize(
    "variant", ["normal", "reversed_assignment", "discard_return", "uninitialized_next"]
)
def test_value_renaming_preserves_topology(variant):
    a = build_example(spec([2], [3, 3], variant))
    b = build_example(spec([12], [13, 13], variant))
    assert b["observation"]["caller_head"] == a["observation"]["caller_head"]
    assert b["observation"]["traversal_status"] == a["observation"]["traversal_status"]
    assert b["observation"]["reachable_prefix"] == [
        x + 10 for x in a["observation"]["reachable_prefix"]
    ]
    assert b["spec_digest"] != a["spec_digest"]


def test_golden_microsteps_normal_no_callers_head_until_return():
    e = build_example(spec([9], [4]))
    steps = e["trace"]["steps"]
    assert [s["phase"] for s in steps] == [
        "initial",
        "allocate",
        "data",
        "link",
        "return",
        "caller",
    ]
    assert steps[1]["nodes"]["t0"] == {"data": "indeterminate", "next": "indeterminate"}
    assert steps[2]["nodes"]["t0"] == {"data": 4, "next": "indeterminate"}
    assert steps[3]["nodes"]["t0"] == {"data": 4, "next": "i0"}
    assert all(s["caller_head"] == "i0" for s in steps[:-1])
    assert steps[-1]["caller_head"] == "t0"
    assert steps[-1]["local_head"] == "i0"


def test_discard_return_local_and_caller_different():
    e = build_example(spec([9], [4, 5], "discard_return"))
    assert e["trace"]["steps"][-1]["returned"] == "t1"
    assert e["trace"]["steps"][-1]["caller_head"] == "i0"
    assert e["trace"]["steps"][-1]["nodes"]["t1"]["next"] == "i0"


def test_indeterminate_is_not_a_finite_exact_traversal_answer():
    e = build_example(spec([], [4, 5], "uninitialized_next"))
    assert e["observation"]["traversal_status"] == "indeterminate"
    assert e["observation"]["reachable_prefix"] == [5]
    assert e["observation"]["unreachable_allocated_ids"] == ["t0"]
    with pytest.raises(SpecError, match="unsupported_question"):
        answer(e, "exact_traversal")
    assert answer(e, "traversal_status") == "indeterminate"


@pytest.mark.parametrize(
    "change",
    [
        {"code": "evil"},
        {"variant": "arbitrary"},
        {"version": "v2"},
        {"initial_values": [1, 2, 3, 4]},
        {"insert_values": []},
        {"insert_values": [1] * 5},
        {"insert_values": [True]},
        {"insert_values": [100]},
        {"insert_values": [-100]},
        {"insert_values": ["1"]},
        {"insert_values": [1.0]},
        {"allocation_success": [1, 1]},
        {"allocation_success": [True]},
        {"allocation_success": "yes"},
        {"initial_values": None},
    ],
)
def test_invalid_input_rejected(change):
    value = spec()
    value.update(change)
    with pytest.raises(SpecError):
        validate_spec(value)


@pytest.mark.parametrize("value", [None, [], 3, {"version": "head-insertion-spec-v1"}])
def test_wrong_shape(value):
    with pytest.raises(SpecError):
        build_example(value)


def test_snapshot_and_actions_bind_original_version():
    value = spec([1], [2, 3])
    original = copy.deepcopy(value)
    e = build_example(value)
    value["insert_values"][0] = 8
    assert e["spec"] == original
    payload = copy.deepcopy(e)
    sha = payload.pop("payload_digest")
    assert digest(payload) == sha
    actions = build_actions(e, "slot:code")
    shows = [a for a in actions if a["kind"] == "show_state"]
    assert len(shows) == len(e["trace"]["steps"])
    for a in shows:
        assert a["state_digest"] == digest(e["trace"]["steps"][a["step"]])
    source = e["code"]["source"].splitlines()
    for a in actions:
        if a["kind"] == "highlight_code":
            assert 1 <= a["line"] <= len(source)
    with pytest.raises(SpecError):
        build_actions(e, "")


@pytest.mark.parametrize(
    "variant", ["normal", "reversed_assignment", "discard_return", "uninitialized_next"]
)
def test_fixed_template_binding(variant):
    e = build_example(spec([9], [3], variant))
    c = e["code"]["source"]
    assert "if (p == NULL) return head;" in c
    assert e["code"]["executed"] is False
    assert ("    p->next = head;" in c) == (variant != "uninitialized_next")
    if variant == "reversed_assignment":
        assert c.index("    head = p;") < c.index("    p->next = head;")
    assert ("    caller_head = insert(" in c) == (variant != "discard_return")
    for s in e["trace"]["steps"]:
        if s["code_line"] is not None:
            assert s["code_line"] in e["code"]["line_anchors"].values()


@pytest.mark.parametrize("field", ["observation", "code", "trace", "payload_digest"])
def test_derived_outputs_refuse_tampering(field):
    e = build_example(spec())
    e[field] = "tampered"
    with pytest.raises(SpecError, match="EXAMPLE_BINDING"):
        answer(e, "caller_head")
    with pytest.raises(SpecError, match="EXAMPLE_BINDING"):
        build_actions(e, "code")
