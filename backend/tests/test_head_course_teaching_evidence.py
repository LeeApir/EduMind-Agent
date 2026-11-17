"""Limited evidence/citation regression; saved original is never revised."""

import json
from copy import deepcopy

import pytest

from app.services import head_course_materials as m
from app.services import head_course_teaching_evidence as e
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import prepare_head_course_evidence as prep


def original():
    return json.loads((prep.OLD / "candidate.json").read_text())


def test_displayed_success_and_counterfactual_are_separate():
    c = original()
    before = canonical(c)
    bundle = e.build(c["payload"])
    displayed, comparison = (bundle["facts"][k] for k in (e.DISPLAYED, e.DISCARDED))
    assert displayed["evidence_kind"] == "displayed_trace"
    assert displayed["displayed_in_main_player"] and not displayed["c_executed"]
    val = displayed["value"]
    assert val["frame_ids"] == [f"f{i:02d}" for i in range(13)]
    assert val["allocation_success_count"] == 2
    assert [v["frame_id"] for v in val["allocation_events"]] == ["f01", "f07"]
    checks = val["null_condition_evaluations"]
    assert [v["frame_id"] for v in checks] == ["f02", "f08"]
    assert [v["continues_to_frame"] for v in checks] == ["f03", "f09"]
    assert all(
        v["condition_evaluated"] and not v["condition_result"] and not v["early_return_taken"]
        for v in checks
    )
    assert val["no_allocation_frame_ids"] == [] and not val["mask_disabled_path_displayed"]
    assert not val["actual_malloc_failure_displayed"]
    assert comparison["evidence_kind"] == "computed_counterfactual"
    assert not comparison["displayed_in_main_player"] and comparison["main_frame_ids"] == []
    obs = comparison["value"]["observation"]
    assert obs["reachable_prefix"] == [-8] and obs["unreachable_allocated_ids"] == ["t0", "t1"]
    assert obs["caller_head"] == "i0" and obs["allocation_failures"] == 0
    assert all(
        v["caller_before"] == v["caller_after"] == "i0" and v["p_next"] == "i0"
        for v in comparison["value"]["calls"]
    )
    assert "insert(caller_head, 0, 1);" in comparison["source_code"]
    assert bundle["source"]["materials_digest"] == c["payload"]["materials"]["materials_digest"]
    assert canonical(c) == before


@pytest.mark.parametrize(
    "mutation", ["frames", "states", "basis", "fact", "origin", "boolean_type"]
)
def test_source_or_fact_tampering_refused(mutation):
    p = e.with_evidence(original()["payload"])
    if mutation == "frames":
        p["materials"]["frames"][2]["line"] = 8
    if mutation == "states":
        p["materials"]["catalog"]["example"]["trace"]["steps"][1]["p"] = None
    if mutation == "basis":
        p["planning_basis"]["evidence"]["ignore_return"]["observation"]["reachable_prefix"] = [
            0,
            6,
            -8,
        ]
    if mutation == "fact":
        p["teaching_evidence"]["facts"][e.DISCARDED]["value"]["observation"]["reachable_prefix"] = [
            0,
            6,
            -8,
        ]
    if mutation == "origin":
        p["teaching_evidence"]["facts"][e.DISCARDED]["displayed_in_main_player"] = True
    if mutation == "boolean_type":
        p["teaching_evidence"]["facts"][e.DISCARDED]["displayed_in_main_player"] = 0
    with pytest.raises(SnapshotError):
        m.body(p)
    with pytest.raises(SnapshotError):
        m.validate_content(p, original()["raw_output"])


def test_new_citations_opt_in_and_original_request_replay():
    c = original()
    assert m.body(c["payload"]) == json.loads((prep.OLD / "generate.request.json").read_text())
    p = e.with_evidence(c["payload"])
    assert p["materials"] == c["payload"]["materials"]
    assert p["planning_basis"] == c["payload"]["planning_basis"]
    raw = deepcopy(c["raw_output"])
    raw["paragraphs"][5]["fact_ids"] = [e.DISCARDED]
    with pytest.raises(SnapshotError, match="HEAD_FACT_REFERENCE"):
        m.validate_content(c["payload"], raw)
    m.validate_content(p, raw)
    request = m.body(p)
    assert request["text"]["format"]["schema"] == m.SCHEMA
    assert json.loads(request["input"][1]["content"])["teaching_evidence"] == p["teaching_evidence"]
    system = request["input"][0]["content"]
    assert "computed_counterfactual" in system and "Neither the mask-disabled" in system
    assert "paragraphs cite existing main fact IDs." not in system
    raw["paragraphs"][5]["fact_ids"] = ["invented"]
    with pytest.raises(SnapshotError, match="HEAD_FACT_REFERENCE"):
        m.validate_content(p, raw)
    values = prep.outputs()
    mapping = json.loads(values["claim-evidence-map.json"])
    assert mapping["original_replay_equal"] and not mapping["original_candidate_modified"]
    assert mapping["C01"]["usable_fact_ids"] == [e.DISCARDED]
    assert mapping["S01"]["shown_no_allocation_frames"] == []
