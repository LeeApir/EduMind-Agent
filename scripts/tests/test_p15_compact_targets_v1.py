"""Exact offline target projection and review alias tests."""

from copy import deepcopy

import pytest

from scripts.isolated_diagnostics import p15_compact_targets_v1 as compact
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact
from scripts.isolated_diagnostics import p15_reference_review_v1 as review
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC


@pytest.mark.parametrize("arm", ["B", "C"])
def test_all_targets_preserved_and_revise_alias_maps_to_exact_original(arm):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    value["paragraphs"][0]["text"] = (
        '`c` [甲"乙][a] [](https://example.test)\n\n[a]: https://example.test'
    )
    course = artifact.assemble(
        value,
        c.identity("dev", "slot", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    binding = review.make_binding(course)
    wire, local = compact.project(binding)
    compact.verify(binding, wire, local)
    assert set(local["aliases"].values()) == set(binding["targets"])
    original_id, row = next(
        (key, row) for key, row in binding["targets"].items() if row["text"] == '甲"乙'
    )
    short = next(key for key, old in local["aliases"].items() if old == original_id)
    result = dict(
        candidate_id=binding["candidate_id"],
        verdict="revise",
        uncertainty="",
        issues=[
            dict(
                severity="minor",
                area="difficulty",
                target_id=short,
                evidence_quote='甲"乙',
                reason="补充解释。",
            )
        ],
    )
    translated = compact.translate(result, binding, wire, local)
    assert translated["issues"][0]["target_id"] == original_id
    assert binding["targets"][original_id] == row
    result["issues"][0]["evidence_quote"] = "无关文字"
    with pytest.raises(c.ContractError, match="QUOTE_BINDING"):
        compact.translate(result, binding, wire, local)


@pytest.mark.parametrize("change", ["missing", "alias", "candidate"])
def test_target_map_tampering_and_wrong_candidate_rejected(change):
    catalog = c.make_catalog(SPEC)
    value = content()
    course = artifact.assemble(
        value, c.identity("dev", "slot", "C", 0, SPEC, None), catalog
    )
    binding = review.make_binding(course)
    wire, local = compact.project(binding)
    wire, local = deepcopy(wire), deepcopy(local)
    if change == "missing":
        wire["other"].pop(next(iter(wire["other"])))
    elif change == "alias":
        local["aliases"].pop(next(iter(local["aliases"])))
    else:
        wire["candidate_id"] = "candidate_wrong"
    with pytest.raises(c.ContractError, match="COMPACT_TARGET_BINDING"):
        compact.verify(binding, wire, local)


def test_dense_references_target_projection_is_complete_and_smaller():
    from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

    text = "[](a)" * 800
    value = content()
    template = value["paragraphs"][0]
    value["paragraphs"] = [dict(template, key=f"p{i}", text=text) for i in range(8)]
    for question in value["questions"].values():
        question.update(stem=text, explanation=text)
    catalog = c.make_catalog(SPEC)
    course = artifact.assemble(
        value, c.identity("dev", "dense", "C", 0, SPEC, None), catalog
    )
    binding = review.make_binding(course)
    wire, local = compact.project(binding)
    old = {key: row["path"] for key, row in binding["targets"].items()}
    assert len(local["aliases"]) == len(old)
    assert len({target for target in local["aliases"].values()}) == len(old)
    assert len(canonical(wire)) < len(canonical(old))
    assert sum(len(rows) for rows in wire["occurrences"].values()) == 12800
    print(
        f"old target catalog={len(canonical(old))} bytes; compact={len(canonical(wire))}; artifact={len(canonical(course))}"
    )
