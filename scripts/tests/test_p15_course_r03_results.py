"""Evidence mutation/path escapes and false quality claims are rejected offline."""

# ruff: noqa: E402
import hashlib
import sys
from pathlib import Path
from copy import deepcopy

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import check_p15_course_r03_results as checker


def test_private_directory_alias_accepts_same_directory_but_not_outside(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    evidence = real / "evidence.json"
    evidence.write_bytes(b"original")
    sha = hashlib.sha256(b"original").hexdigest()
    checker.verify_index({"sha256": {"evidence.json": sha}}, alias)
    evidence.write_bytes(b"modified")
    with pytest.raises(ValueError, match="PRIVATE_EVIDENCE_CHANGED"):
        checker.verify_index({"sha256": {"evidence.json": sha}}, alias)
    outside = tmp_path / "outside"
    outside.write_bytes(b"original")
    with pytest.raises(ValueError, match="PRIVATE_EVIDENCE_CHANGED"):
        checker.verify_index({"sha256": {"../outside": sha}}, alias)


def summary():
    return dict(
        state="stopped",
        stop_reason="threshold_unreachable",
        course_quality_pass=False,
        T038_completed=False,
        production_admission=False,
        independent_human_truth=False,
        legacy_standard_review_imported=False,
        requests=3,
        generation_requests=2,
        review_requests=1,
        workflow_requests=10,
        actual_fee_micros=None,
        input_tokens=9651,
        output_tokens_including_reasoning=3545,
        workflow_input_tokens=29006,
        workflow_output_tokens=11851,
    )


@pytest.mark.parametrize(
    "field",
    [
        "course_quality_pass",
        "T038_completed",
        "production_admission",
        "independent_human_truth",
        "legacy_standard_review_imported",
    ],
)
def test_compatibility_never_relabels_quality_or_reviewer_truth(field):
    value = summary()
    checker.validate_summary(value)
    value[field] = True
    with pytest.raises(ValueError, match="FALSE_SUCCESS_OR_PROVENANCE"):
        checker.validate_summary(value)


@pytest.mark.parametrize(
    "field",
    [
        "workflow_requests",
        "workflow_input_tokens",
        "workflow_output_tokens",
        "actual_fee_micros",
    ],
)
def test_prior_history_and_unknown_invoice_cannot_disappear(field):
    value = deepcopy(summary())
    value[field] = 0
    with pytest.raises(ValueError, match="HISTORY_OR_USAGE_CHANGED"):
        checker.validate_summary(value)
