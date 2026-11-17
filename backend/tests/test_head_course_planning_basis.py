"""T108 candidate evidence and request bindings only; no Provider or handwritten real plan."""

import json
from copy import deepcopy

import pytest

from app.agents import head_course_planning_wire as wire
from app.services import head_course_materials as m
from app.services import head_course_planning_basis as basis
from app.services.free_course_snapshots import SnapshotError, digest
from scripts import head_course_goal as entry
from scripts import head_course_goal_fixture as fixture
from tests.test_head_course_planning_wire import inputs


@pytest.mark.parametrize("key,expected", [("head-new-A", [7, 4, 12]), ("head-new-B", [0, 6, -8])])
def test_program_basis_matches_code_scope_and_independent_state_expectations(key, expected):
    all_evidence = basis.build_basis()
    evidence = all_evidence["examples"][key]
    mat = m.materials_for_example(key)
    code = mat["catalog"]["example"]["code"]
    assert evidence["materials_digest"] == mat["materials_digest"]
    assert evidence["code_digest"] == digest("head-planning-code", source=code["source"])
    assert evidence["function_code"] in code["source"]
    assert (
        evidence["function_interface"]
        == "Node *insert(Node *head, int value, int allocation_success)"
    )
    scopes = {row["name"]: row["scope"] for row in evidence["variable_scopes"]}
    assert scopes == dict(
        head="insert.parameter",
        p="insert.local",
        value="insert.parameter",
        allocation_success="insert.parameter",
        caller_head="main.local",
        i0="main.local",
    )
    assert evidence["receive_return"]["observation"]["reachable_prefix"] == expected
    assert evidence["ignore_return"]["observation"]["reachable_prefix"] == [expected[-1]]
    assert evidence["ignore_return"]["observation"]["unreachable_allocated_ids"] == ["t0", "t1"]
    for received, ignored in zip(
        evidence["receive_return"]["calls"], evidence["ignore_return"]["calls"], strict=True
    ):
        assert received["local_head_at_return"] == received["caller_before"]
        assert received["p_next"] == received["caller_before"]
        assert received["caller_after"] == received["returned"] == received["p"]
        assert ignored["caller_before"] == ignored["caller_after"] == "i0"
        assert ignored["returned"] != ignored["caller_after"]
    for row in evidence["key_code"]:
        assert row["statement"] == code["source"].splitlines()[row["line"] - 1].strip()
    assert not {"objectives", "scenes", "paragraphs", "step_notes"} & set(evidence)


@pytest.mark.parametrize("key", list(m.SPECS))
def test_actual_plan_teaching_repair_and_review_materials_share_exact_basis(key):
    original = inputs()
    before = deepcopy(original)
    request = entry.planning_body(original)
    payload = json.loads(request["input"][1]["content"])
    sent = payload["planning_example_basis"]
    assert sent == basis.build_basis()
    assert payload["prompt_version"] == wire.PROMPT_VERSION
    assert payload["wire_protocol"] == wire.VERSION
    assert request["text"]["format"]["schema"] == wire.SCHEMA
    assert original == before
    assert "[PLANNING RESPONSIBILITY]" in request["input"][0]["content"]
    plan = fixture.plan(key)["plan"]  # Explicit offline fixture, not a planning result.
    teaching = m.content_payload(original, plan)
    binding = teaching["planning_basis"]["binding"]
    assert teaching["planning_basis"]["evidence"] == sent["examples"][key]
    assert binding["basis_digest"] == sent["basis_digest"]
    assert binding["materials_digest"] == teaching["materials"]["materials_digest"]
    assert binding["example_basis_digest"] == sent["examples"][key]["example_basis_digest"]
    parent = fixture.record(teaching)["candidate"]
    for body, field in [(m.body(teaching), None), (m.body(teaching, parent, []), "original_input")]:
        transmitted = json.loads(body["input"][1]["content"])
        assert (transmitted if field is None else transmitted[field])["planning_basis"] == teaching[
            "planning_basis"
        ]
        assert body["text"]["format"]["schema"] == m.SCHEMA
    mapping = wire.mapping_record(fixture.wire_plan(key), original)
    assert mapping["planning_basis_digest"] == binding["basis_digest"]
    assert mapping["planning_prompt_version"] == wire.PROMPT_VERSION
    assert len(entry.canonical(request)) <= 131072


@pytest.mark.parametrize("mutation", ["code", "main", "local_head", "outcome"])
def test_evidence_extraction_refuses_code_or_state_disagreement(monkeypatch, mutation):
    original = m.materials_for_example

    def broken(key):
        result = original(key)
        example = result["catalog"]["example"]
        if mutation == "code":
            example["code"]["source"] = example["code"]["source"].replace(
                "return p;", "return head;"
            )
        elif mutation == "main":
            example["code"]["source"] = example["code"]["source"].replace(
                "caller_head = &i0", "caller_head = NULL"
            )
        elif mutation == "local_head":
            next(s for s in example["trace"]["steps"] if s["phase"] == "return")["local_head"] = (
                "t0"
            )
        else:
            example["observation"]["reachable_prefix"] = []
        return result

    monkeypatch.setattr(m, "materials_for_example", broken)
    with pytest.raises(SnapshotError, match="HEAD_PLANNING_BASIS_MISMATCH"):
        entry.planning_body(inputs())


@pytest.mark.parametrize("mutation", ["materials_digest", "code"])
def test_selected_teaching_material_cannot_drift_from_planning_basis(mutation):
    mat = m.materials_for_example("head-new-A")
    if mutation == "materials_digest":
        mat["materials_digest"] = "bad"
    else:
        mat["catalog"]["example"]["code"]["source"] += " /* changed */"
    with pytest.raises(SnapshotError, match="HEAD_PLANNING_BASIS_MISMATCH"):
        basis.selected_basis(mat)


@pytest.mark.parametrize("mutation", ["code", "observation"])
def test_ignored_return_comparison_is_checked_not_assumed(monkeypatch, mutation):
    original = basis.build_example

    def broken(spec):
        result = original(spec)
        if mutation == "code":
            result["code"]["source"] = result["code"]["source"].replace("return p;", "return head;")
        else:
            result["observation"]["reachable_prefix"] = []
        return result

    monkeypatch.setattr(basis, "build_example", broken)
    with pytest.raises(SnapshotError, match="HEAD_PLANNING_BASIS_MISMATCH"):
        basis.build_basis()
