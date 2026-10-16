"""Calibration evidence integrity; these tests do not claim semantic model accuracy."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.coverage_standard import reference_check  # noqa: E402
from acceptance_support.om_diagnostic import hash_bytes, stable  # noqa: E402
from prepare_coverage_review import BASE, build  # noqa: E402

from app.services.unit_material import restore_material  # noqa: E402


@pytest.fixture(scope="module")
def frozen():
    return build()


def content(case, role):
    return next(
        c["envelope"]["content"]
        for c in case["material"]["candidates"]
        if c["role"] == role
    )


def test_freeze_binds_exact_material_without_authorizing_any_execution(frozen):
    for name, value in frozen.items():
        assert json.loads((ROOT / BASE / name).read_text()) == value
    proposal = frozen["proposal.json"]
    assert proposal["requests_authorized"] == proposal["fees_authorized"] == 0
    for name, sha in proposal["artifacts"].items():
        assert stable(frozen[name]) == sha
    for slot in proposal["slots"]:
        case = frozen["cases.json"][slot["id"]]
        assert hash_bytes(bytes.fromhex(case["wire_hex"])) == slot["wire_sha256"]
        restore_material(case["material"])
        body = json.loads(bytes.fromhex(case["wire_hex"]))
        data = json.loads(body["input"][1]["content"])
        assert data["unit"] == case["material"]
        assert len(data["student_delivery"]["resources"]) == 3
    assert not (ROOT / BASE / "run-approval.json").exists()
    assert not (ROOT / "local-materials/phase-1-coverage-r04").exists()


def test_distributed_positive_preserves_process_support_outside_explanation(frozen):
    data = frozen["cases.json"]
    distributed, complete = data["trace-distributed"], data["trace-complete"]
    assert content(distributed, "explanation") != content(complete, "explanation")
    assert content(distributed, "code") == content(complete, "code")
    assert content(distributed, "exercise") == content(complete, "exercise")
    steps = " ".join(content(distributed, "code")["key_steps"])
    assert "2、7、16" in steps and "i=3" in steps and "不访问a[3]" in steps


def test_gap_pairs_do_not_introduce_an_implementation_defect(frozen):
    data = frozen["cases.json"]
    for name in ("plan-only-gap", "assessment-gap"):
        assert (
            content(data[name], "code")["source"]
            == content(data["trace-complete"], "code")["source"]
        )
        result = reference_check(content(data[name], "code")["source"])
        assert result["return"] == 16 and result["exit"]["i"] == 3
    assert "i=3" in str(data["plan-only-gap"]["material"]["plan"]["shared_example"])
    assert content(data["assessment-gap"], "explanation") == content(
        data["trace-complete"], "explanation"
    )
    assert content(data["assessment-gap"], "exercise") == content(
        data["plan-only-gap"], "exercise"
    )
    control = frozen["offline-implementation-control.json"]
    assert (
        not control["real_slot"]
        and "不承诺过程" in control["material"]["plan"]["objectives"][0]["text"]
    )


def test_reassessment_keeps_safety_and_fact_separate_from_coverage(frozen):
    rows = {r["id"]: r for r in frozen["reassessment.json"]["rows"]}
    assert rows["missing-unit-objective"]["expected_primary_semantics"] == "needs_human"
    assert not rows["missing-unit-objective"]["teaching_gap_is_severe_fact_error"]
    assert (
        rows["reachable-safety"]["reference_check"]["reachable_unsafe_access"] == "a[4]"
    )
    assert rows["fact-contradiction"]["reference_check"]["return"] == 16
    assert frozen["reassessment.json"]["independent_human_review_of_all_rows"] is False
    with pytest.raises(ValueError, match="UNSUPPORTED_REFERENCE_PROGRAM"):
        reference_check("arbitrary supplied C must never execute")
