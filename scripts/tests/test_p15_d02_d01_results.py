"""Offline stop-result regressions: no synthetic success or hidden unknowns."""

# ruff: noqa: E402
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import check_p15_d02_d01_results as checker


def saved():
    return json.loads((checker.cli.BASE / "results.json").read_bytes())


def test_saved_summary_matches_original_evidence_read_only():
    assert checker.check() == saved()


@pytest.mark.parametrize(
    "key,value",
    [
        ("state", "completed"),
        ("requests", 5),
        ("unknown", 0),
        ("complete", 4),
        ("reported_input", 11842),
        ("reported_output", 4221),
        ("review_scenes_unrun", 0),
        ("model_reviews_accepted", 1),
        ("standard_assistant_reports", 1),
        ("T038_completed", True),
        ("local_recheck_pass", True),
        ("blind_answers_fail", 0),
        ("blind_answers_pass", 4),
        ("consistency_false_alarms", 0),
        ("workflow_requests", 25),
        ("protocol_rejection", "REASONING_ITEM_MISSING"),
    ],
)
def test_unknown_missing_reviews_bad_answers_and_actual_protocol_cannot_be_hidden(
    key, value
):
    value_map = saved()
    value_map[key] = value
    with pytest.raises(ValueError, match="EXACT_STOP_FACTS_CHANGED"):
        checker.validate_summary(value_map)
