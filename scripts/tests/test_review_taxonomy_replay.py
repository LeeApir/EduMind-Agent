"""Offline evidence replay, not a semantic classifier or new provider evaluation."""

import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]

from acceptance_support.coverage_standard import reference_check  # noqa: E402
from acceptance_support.om_diagnostic import stable  # noqa: E402
from acceptance_support.phase1_budget import GateFailure  # noqa: E402
from run_coverage_v44 import runtime  # noqa: E402

from app.agents.hybrid_resource_review import route_review  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1-coverage-r05"


def evidence():
    case = json.loads((BASE / "cases.json").read_text())["plan-only-gap"]
    receipt = json.loads((BASE / "results/plan-only-gap-03.json").read_text())
    assert stable(case["material"]) == receipt["material_sha256"]
    return case, receipt


def test_actual_response_still_fails_original_pure_gap_gate():
    case, receipt = evidence()
    value = receipt["review_result"]
    before = deepcopy(value)
    assert (
        route_review(value, scope="unit", catalog=case["anchors"])
        == receipt["local_routing"]
    )
    with pytest.raises(GateFailure, match="PURE_COVERAGE_FINDING_INVALID"):
        asyncio.run(runtime().assess(case, value, "plan-only-gap"))
    assert value == before
    assert receipt["ledger"] == {
        "attempts": 3,
        "complete": 2,
        "failed": 1,
        "halted": "INVALID_OUTPUT",
    }
    assert receipt["requests_not_sent"] == ["assessment-gap"]


def test_actual_claim_anchor_and_closed_function_semantics():
    case, receipt = evidence()
    anchor = next(a for a in case["anchors"] if a["anchor_id"] == "a1")
    resource = next(
        c
        for c in case["material"]["candidates"]
        if c["resource_id"] == anchor["resource_id"]
    )
    content = resource["envelope"]["content"]["markdown"]
    anchored = content.encode()[anchor["start_utf8"] : anchor["end_utf8"]].decode()
    assert "sum()返回16，不直接打印。" in anchored
    code = next(c for c in case["material"]["candidates"] if c["role"] == "code")
    # Frozen display text escapes its newline; only the exact closed fixture is accepted.
    check = reference_check(code["envelope"]["content"]["source"].replace("\\n", "\n"))
    assert check["return"] == 16
    assert check["trace"] == [
        {"i": 0, "total": 2},
        {"i": 1, "total": 7},
        {"i": 2, "total": 16},
    ]
    assert check["exit"]["i"] == 3
    assert receipt["review_result"]["findings"][0]["category"] == "fact"
    # Arithmetic validates this fixed example only, not arbitrary natural-language findings.


@pytest.mark.parametrize("category", ["fact", "code_safety"])
def test_serious_finding_with_coverage_gap_keeps_reject_priority(category):
    case, receipt = evidence()
    value = deepcopy(receipt["review_result"])
    value["verdict"] = "reject"
    value["findings"] = [
        {
            "category": category,
            "severity": "severe",
            "anchors": ["a1"],
            "condition_or_counterexample": "Synthetic protocol replay: concrete counterexample supplied.",
            "impact": "Synthetic protocol replay: incorrect result or unsafe access.",
        }
    ]
    assert value[
        "unresolved"
    ]  # Mixed issues must not erase a supported serious reject.
    route = route_review(value, scope="unit", catalog=case["anchors"])
    assert route["verdict"] == "reject"
    assert value["findings"][0]["category"] == category
    # This tests routing only; synthetic findings are not truth labels for the real material.


def test_historical_fact_and_safety_controls_retain_concrete_counterexamples():
    controls = json.loads(
        (ROOT / "docs/acceptance/phase-1-om-admission-r03/cases.json").read_text()
    )
    for name in ("fact-contradiction", "reachable-safety"):
        roles = {c["role"]: c for c in controls[name]["material"]["candidates"]}
        check = reference_check(roles["code"]["envelope"]["content"]["source"])
        if name == "fact-contradiction":
            assert "18" in roles["explanation"]["envelope"]["content"]["markdown"]
            assert check["return"] == 16
        else:
            assert check["reachable_unsafe_access"] == "a[4]"
            assert 4 not in check["valid_indices"]
