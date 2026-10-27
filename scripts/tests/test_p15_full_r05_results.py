"""Stopped r05 cannot be rewritten as complete, paid-zero, or content-correct."""

# ruff: noqa: E402
import json
import socket
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import check_p15_full_r05_results as c
from isolated_diagnostics.p15_course_sol_bridge import review_request
from test_p15_sol_compatibility_proposal import sample


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(
        socket.socket, "connect", lambda *args: pytest.fail("Offline only")
    )
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: pytest.fail("No DNS"))


def variant():
    _, response, source, opinion = sample()
    request = review_request("development_scene_review", source)
    response["instructions"] = request["input"][0]["content"] + c.compat.SUFFIX
    response["output"] = response["output"][1:]
    return request, response, source, opinion


def test_nonzero_reported_reasoning_without_item_remains_actual_rejection_without_edits():
    req, res, source, _ = variant()
    before = deepcopy((req, res, source))
    observation = c.protocol_observation(req, res, source)
    assert observation["actual_rejection"] == "REASONING_ITEM_MISSING"
    assert observation["actual_protocol_pass"] is False
    assert observation["counterfactual_edits"] is False
    assert observation["reported_reasoning_tokens"] == 11
    assert observation["reported_output_tokens_including_reasoning"] == 100
    assert observation["final_json_schema_and_source_valid"] is True
    assert (req, res, source) == before


@pytest.mark.parametrize("fault", ["sha", "quote", "pass_with_issue"])
def test_static_final_json_or_source_errors_cannot_hide_behind_metadata_failure(fault):
    req, res, source, opinion = variant()
    if fault == "sha":
        opinion["source_sha256"] = "f" * 64
    if fault == "quote":
        opinion["issues"][0]["evidence_quote"] = "not in original"
    if fault == "pass_with_issue":
        opinion["verdict"] = "pass"
    res["output"][0]["content"][0]["text"] = json.dumps(opinion)
    with pytest.raises(ValueError):
        c.protocol_observation(req, res, source)


def test_absent_item_with_zero_reasoning_is_not_mislabelled_this_failure():
    req, res, source, _ = variant()
    res["usage"]["output_tokens_details"]["reasoning_tokens"] = 0
    with pytest.raises(ValueError, match="EXPECTED_PROTOCOL_REJECTION_MISSING"):
        c.protocol_observation(req, res, source)


@pytest.mark.parametrize(
    "fault",
    [
        "complete",
        "contract_pass",
        "quality_pass",
        "human",
        "invoice_zero",
        "unknown_removed",
        "unrun_removed",
        "history_removed",
        "severity_hidden",
        "blind_as_standard",
        "schema_failure_hidden",
        "content_pass",
        "protocol_pass",
    ],
)
def test_saved_counts_unknown_history_and_actual_quality_failure_are_not_optional(
    fault,
):
    baseline = json.loads((c.cli.BASE / "results.json").read_bytes())
    c.validate_summary(baseline)
    if fault == "complete":
        baseline["T038_completed"] = True
    if fault == "contract_pass":
        baseline["actual_contract_pass"] = True
    if fault == "quality_pass":
        baseline["formal_quality_pass"] = True
    if fault == "human":
        baseline["independent_human_truth"] = True
    if fault == "invoice_zero":
        baseline["actual_fee_micros"] = 0
    if fault == "unknown_removed":
        baseline["unknown_attempts"] = 0
    if fault == "unrun_removed":
        baseline["remaining_unrun"] = 0
    if fault == "history_removed":
        baseline["workflow_requests"] = 10
    if fault == "severity_hidden":
        baseline["natural_severe_errors_observed"] = 0
    if fault == "blind_as_standard":
        baseline["standard_assistant_reviews"] = 3
    if fault == "schema_failure_hidden":
        baseline["primary_schema_valid"][0] = False
    if fault == "content_pass":
        baseline["all_observed_content_quality_pass"] = True
    if fault == "protocol_pass":
        baseline["observation"]["actual_protocol_pass"] = True
    with pytest.raises(ValueError):
        c.validate_summary(baseline)


@pytest.mark.parametrize("fault", ["changed", "escape"])
def test_public_result_manifest_checks_bytes_and_project_boundary(tmp_path, fault):
    p = tmp_path / "report.json"
    p.write_text("{}")
    import hashlib

    manifest = {"sha256": {"report.json": hashlib.sha256(p.read_bytes()).hexdigest()}}
    c.verify_public_manifest(tmp_path, manifest)
    if fault == "changed":
        p.write_text('{"forged":true}')
    else:
        manifest["sha256"] = {"../outside.json": "a" * 64}
    with pytest.raises(ValueError):
        c.verify_public_manifest(tmp_path, manifest)
