"""Evidence binding and logical counterexample checks, not model quality scoring."""

# ruff: noqa: E402
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from prepare_evidence_repair_proposal import build, anchor_witness, PRIOR
from app.services.learning_policy import POLICY
from app.agents.hybrid_resource_review import REVIEW_V4_PROMPT


def rows():
    return {x["id"]: x for x in build()["regression-cases.json"]["cases"]}


def test_actual_ub_answer_preserved_as_negative_not_silently_repaired():
    source = json.loads((ROOT / PRIOR / "results/reachable-safety-03.json").read_text())
    row = rows()["actual-ub-overclaim"]
    assert row["original_finding"] == source["structured_review"]["findings"][2]
    assert (
        "其值不等于 16 且不确定"
        in row["original_finding"]["condition_or_counterexample"]
    )
    assert not row["expected"]["overall_review_acceptable"]
    assert row["expected"]["core_safety_reject_retained"]
    assert (
        rows()["synthetic-ub-bounded-conclusion"]["origin"]
        == "authored_proposed_contrast_not_model_output"
    )


def test_each_anchor_resolves_actual_text_including_wrong_secondary():
    r = rows()["actual-fact-secondary-anchor"]
    w = {a["anchor_id"]: a for a in r["anchors"]}
    assert (
        "sum()返回18" in w["a1"]["actual_excerpt"]
        and "total=16" in w["a1"]["actual_excerpt"]
    )
    assert (
        w["a15"]["json_pointer"] == "/items/2/answer"
        and w["a15"]["actual_excerpt"] == "F"
    )
    assert not r["expected"]["every_citation_supports_claim"]
    assert rows()["synthetic-F-valid-role"]["anchors"][0]["actual_excerpt"] == "F"
    assert rows()["synthetic-F-valid-role"]["expected"]["supports_this_atomic_claim"]
    assert (
        rows()["synthetic-defined-sum-fact"]["anchors"][1]["json_pointer"] == "/source"
    )


def test_logical_countermodel_disproves_only_the_bad_implication():
    states = rows()["logic-no-guarantee-not-negation"]["possible_states"]
    guaranteed_P = all(s["P"] for s in states)
    guaranteed_not_P = all(not s["P"] for s in states)
    assert not guaranteed_P and not guaranteed_not_P
    assert (not guaranteed_P) and not guaranteed_not_P
    # Abstract witnesses only; never execute or infer a concrete unsafe-C output.


@pytest.mark.parametrize("change", ["digest", "resource", "bounds", "pointer"])
def test_anchor_binding_or_location_tamper_is_rejected(change):
    cases = json.loads((ROOT / PRIOR / "cases.json").read_text())
    c = deepcopy(cases["fact-contradiction:candidate"])
    a = next(a for a in c["anchors"] if a["anchor_id"] == "a15")
    if change == "digest":
        a["resource_digest"] = "0" * 64
    elif change == "resource":
        a["resource_id"] = "not-the-same-resource"
    elif change == "bounds":
        a["end_utf8"] = 500000
    else:
        a["json_pointer"] = "/items/9000/answer"
    with pytest.raises((ValueError, KeyError, IndexError)):
        anchor_witness(c, "a15")


def test_retained_controls_and_no_production_or_authorization_change():
    values = build()
    p = values["proposal.json"]
    r = rows()
    assert len(r) == 12
    for name, route in [
        ("trace-complete", "pass"),
        ("trace-distributed", "pass"),
        ("gap-and-safety", "reject"),
        ("assessment-gap", "needs_human"),
        ("plan-only-gap", "needs_human"),
    ]:
        assert r["retained-" + name]["expected"]["route"] == route
    assert not p["implementation_approved"] and not p["real_validation_approved"]
    assert (
        p["provider_requests"] == p["requests_authorized"] == p["fees_authorized"] == 0
    )
    assert (
        REVIEW_V4_PROMPT
        == POLICY["resource_review_prompt"]
        == "evidence-resource-review-v4.4"
    )
    assert build() == values
    assert not (
        ROOT / "docs/acceptance/phase-1-evidence-repair-proposal-r01/run-approval.json"
    ).exists()
