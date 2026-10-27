"""No invented compatibility pass, hidden summaries, missing history or unknown refund."""

# ruff: noqa: E402
import sys
import json
from pathlib import Path
from copy import deepcopy

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import check_p15_full_r04_results as c
from test_p15_sol_compatibility_proposal import sample


def test_exact_missing_echo_and_nonempty_summary_are_not_rewritten_as_actual_pass():
    req, res, source, _ = sample()
    res.pop("instructions")
    res["output"][0]["summary"] = [
        {"type": "summary_text", "text": "SYNTHETIC_DO_NOT_FORWARD"}
    ]
    before = deepcopy(res)
    out = c.protocol_observation(req, res, source)
    assert out["actual_rejection"] == "UNRECOGNIZED_INSTRUCTION_ECHO"
    assert (
        out["additional_counterfactual_rejection"]
        == "NONEMPTY_OR_UNKNOWN_REASONING_ITEM"
    )
    assert (
        not out["actual_protocol_pass"]
        and out["counterfactual_only_verdict"] == "revise"
    )
    assert "SYNTHETIC_DO_NOT_FORWARD" not in json.dumps(out) and res == before


def test_counterfactual_edits_cannot_hide_an_invalid_source_digest():
    req, res, source, opinion = sample()
    res.pop("instructions")
    res["output"][0]["summary"] = [{"type": "summary_text", "text": "synthetic"}]
    opinion["source_sha256"] = "f" * 64
    res["output"][-1]["content"][0]["text"] = json.dumps(opinion)
    with pytest.raises(ValueError):
        c.protocol_observation(req, res, source)


def baseline():
    return dict(
        state="stopped",
        stop_reason="UNKNOWN_SEND",
        actual_contract_pass=False,
        formal_quality_pass=False,
        T038_completed=False,
        independent_human_truth=False,
        unknown_attempts=1,
        actual_fee_micros=None,
        remaining_unrun=33,
        standard_assistant_reviews=0,
        requests=4,
        workflow_requests=14,
        reported_all_input_tokens=52884,
        reported_all_output_tokens=3107,
        workflow_reported_input_tokens=81890,
        workflow_reported_output_tokens=14958,
        http_statuses=[200] * 4,
        primary_schema_valid=[True, False],
    )


@pytest.mark.parametrize(
    "field",
    [
        "actual_contract_pass",
        "formal_quality_pass",
        "T038_completed",
        "independent_human_truth",
    ],
)
def test_counterfactual_or_model_pass_never_becomes_quality_success(field):
    result = baseline()
    result[field] = True
    with pytest.raises(ValueError, match="FALSE_SUCCESS"):
        c.validate_summary(result)


@pytest.mark.parametrize(
    "field",
    [
        "unknown_attempts",
        "remaining_unrun",
        "actual_fee_micros",
        "workflow_requests",
        "workflow_reported_input_tokens",
        "workflow_reported_output_tokens",
    ],
)
def test_all_usage_unknown_and_old_failures_stay_visible(field):
    result = baseline()
    result[field] = 0
    with pytest.raises(ValueError):
        c.validate_summary(result)
