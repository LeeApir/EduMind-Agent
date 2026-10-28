"""Forensic regressions: valid JSON is not a covered plan or a completed course test."""

# ruff: noqa: E402
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import check_p15_d02_d02_results as checker


def saved():
    return json.loads((checker.cli.BASE / "results.json").read_bytes())


def test_read_only_actual_evidence_distinguishes_json_and_local_validation():
    result = checker.check()
    assert result == saved() and result["json_schema_valid"]
    assert not result["local_planning_validation_passed"]
    assert result["uncovered_objective_ids"] == ["obj_two_scenes"]
    assert (
        not result["scene_v5_exercised"]
        and not result["review_protocol_exercised_live"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("requests", 5),
        ("review_requests", 1),
        ("unknown", 1),
        ("json_schema_valid", False),
        ("local_planning_validation_passed", True),
        ("uncovered_objective_ids", []),
        ("generated_scenes", 2),
        ("scene_v5_exercised", True),
        ("scene_quality_observed", True),
        ("T038_completed", True),
        ("route_reassessment_required", False),
        ("local_recheck_pass", True),
    ],
)
def test_fabricated_success_or_unobserved_quality_is_rejected(field, value):
    data = saved()
    data[field] = value
    with pytest.raises(ValueError, match="EXACT_FINAL_STOP_FACTS_CHANGED"):
        checker.validate_summary(data)


@pytest.mark.parametrize("target", ["request", "response", "diagnosis", "pg"])
def test_raw_wire_or_failure_diagnosis_tampering_is_rejected(
    tmp_path, monkeypatch, target
):
    original = checker.cli.OUTPUT
    for p in original.iterdir():
        if p.is_file() and not p.name.endswith(("-shm", "-wal")):
            shutil.copyfile(p, tmp_path / p.name)
    monkeypatch.setattr(checker.cli, "OUTPUT", tmp_path)
    if target in ("request", "response"):
        p = next(tmp_path.glob("*-" + target + ".json"))
        p.write_bytes(p.read_bytes() + b" ")
    elif target == "diagnosis":
        p = tmp_path / "planning-failure-diagnosis.json"
        v = json.loads(p.read_bytes())
        v["uncovered_objective_ids"] = []
        p.write_text(json.dumps(v))
    else:
        p = tmp_path / "pg-export.json"
        v = json.loads(p.read_bytes())
        v["tables"]["free_course_scene_versions"] = [dict(id="FAKE")]
        p.write_text(json.dumps(v))
    with pytest.raises((AssertionError, ValueError)):
        checker.check()
