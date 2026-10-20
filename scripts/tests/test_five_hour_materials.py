"""No network: immutable inputs, scope routing and honest GPT evidence records."""

# ruff: noqa: E402
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import socket
import sys

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from prepare_five_hour_materials import BASE, build
from check_five_hour_materials import (
    check_materials,
    validate_evaluation,
    verify_freeze,
)
from acceptance_support.qwen_review_budget import canonical, sha


def read(name):
    return json.loads((BASE / name).read_text())


def test_all_inputs_reproduce_with_dns_forbidden(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: pytest.fail("No DNS in material prep")
    )
    actual = asyncio.run(build())
    assert all(value == read(name) for name, value in actual.items())
    assert check_materials()["live_authority"] == 0


def test_unrun_template_is_not_success_or_actual_output():
    value = read("evaluation-template.json")
    validate_evaluation(value)
    for section, key in (
        ("grades", "core_expected"),
        ("grades", "full_quality"),
        ("actual", "model_verdict"),
    ):
        invalid = deepcopy(value)
        invalid[section][key] = "pass"
        with pytest.raises((ValueError, ValidationError)):
            validate_evaluation(invalid)


def observed_record():
    # Pure test data; never a real receipt, semantic score or test run.
    value = read("evaluation-template.json")
    value["run_id"] = "TEST_ONLY_fake_run"
    value["evaluator"]["evaluated_at"] = "2026-10-20T00:00:00+08:00"
    value["actual"].update(
        status="observed",
        actual_call_count=8,
        model_verdict="pass",
        local_verdict="pass",
        course_state="completed",
        request_receipt_paths=["TEST_ONLY/receipt.json"],
        response_artifact_paths=["TEST_ONLY/response.json"],
    )
    value["grades"].update(
        technical_integrity="pass",
        core_expected="pass",
        all_claims="pass",
        all_citations="pass",
        full_quality="pass",
        impact="green",
        final_status="pass",
    )
    value["reviewed_all_candidates_and_audit_history"] = True
    value["evidence"] = [
        dict(
            id="test-evidence",
            kind="static_reasoning",
            artifact_path="TEST_ONLY/response.json",
            artifact_sha256="a" * 64,
            applies_to_digest=value["case_sha256"],
            scope_note="TEST ONLY semantic validator fixture, not evidence",
        )
    ]
    return value


@pytest.mark.parametrize(
    "mutation",
    [
        "contradiction",
        "missing_evidence",
        "human_signature",
        "executed_new_code",
        "wrong_case_hash",
        "not_automatic",
        "propagated_error",
    ],
)
def test_false_success_and_boundary_violations_rejected(mutation):
    value = observed_record()
    validate_evaluation(value)
    if mutation == "contradiction":
        value["claim_checks"] = [
            dict(
                review_artifact_path="TEST_ONLY/response.json",
                json_pointer="/unresolved/0",
                quoted_text="unsupported correction",
                result="contradicted",
                evidence_ids=["test-evidence"],
                reason="would index0 instead of1",
            )
        ]
    elif mutation == "missing_evidence":
        value["evidence"] = []
    elif mutation == "human_signature":
        value["product_human_decision"] = "approved"
    elif mutation == "executed_new_code":
        value["code_verification"]["new_code_executed"] = True
    elif mutation == "wrong_case_hash":
        value["case_sha256"] = "0" * 64
    elif mutation == "not_automatic":
        value["actual"]["course_state"] = "awaiting_human"
    else:
        value["corrections"]["unsupported_feedback_entered"] = True
    with pytest.raises((ValueError, ValidationError)):
        validate_evaluation(value)


def test_resource_routes_fixed_before_results_and_core_cannot_override():
    labels = read("labels.json")["labels"]
    assert (
        labels["R03"]["expected_verdicts"]
        == labels["R04"]["expected_verdicts"]
        == ["revise", "reject"]
    )
    assert (
        labels["U04"]["expected_verdicts"]
        == labels["U05"]["expected_verdicts"]
        == ["needs_human"]
    )
    budget = read("budget.json")
    assert budget["overall_request_budget_cap"] is None
    assert (
        budget["basic_package_requests_max"] == 60
        and budget["real_requests_authorized"] == 0
    )


@pytest.mark.parametrize(
    "bad",
    [
        "not_run_pass",
        "subgrade_fail",
        "unresolved",
        "unreviewed_history",
        "missing_receipts",
    ],
)
def test_standalone_schema_also_rejects_inconsistent_pass(bad):
    value = observed_record()
    if bad == "not_run_pass":
        value["actual"].update(status="not_run", actual_call_count=0)
    elif bad == "subgrade_fail":
        value["grades"]["all_claims"] = "fail"
    elif bad == "unresolved":
        value["unresolved"] = ["unverified claim"]
    elif bad == "unreviewed_history":
        value["reviewed_all_candidates_and_audit_history"] = False
    else:
        value["actual"]["request_receipt_paths"] = []
    with pytest.raises(ValidationError):
        Draft202012Validator(read("evaluation.schema.json")).validate(value)


def test_frozen_file_tampering_is_rejected(tmp_path):
    material = tmp_path / "fixture.json"
    material.write_text('{"frozen":true}')
    manifest = dict(
        kind="FROZEN_INPUTS_AND_GPT_RECORD_FORMAT_NOT_EXECUTION_AUTHORITY",
        real_requests_authorized=0,
        files={"fixture.json": sha(material.read_bytes())},
    )
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    verify_freeze(tmp_path, tmp_path)
    material.write_text('{"frozen":false}')
    with pytest.raises(ValueError, match="FREEZE_CHANGED"):
        verify_freeze(tmp_path, tmp_path)


def test_expected_needs_human_is_not_a_completed_course():
    value = observed_record()
    entry = next(e for e in read("case-index.json")["entries"] if e["id"] == "U04")
    value.update(
        case_id="U04",
        case_sha256=entry["case_sha256"],
        label_sha256=sha(canonical(read("labels.json")["labels"]["U04"])),
    )
    value["actual"].update(
        actual_call_count=1,
        model_verdict="needs_human",
        local_verdict="needs_human",
        course_state=None,
    )
    validate_evaluation(value)  # Diagnostic expected outcome; not a published course.
    value["actual"]["course_state"] = "completed"
    with pytest.raises(ValidationError):
        Draft202012Validator(read("evaluation.schema.json")).validate(value)
    with pytest.raises((ValidationError, ValueError)):
        validate_evaluation(value)
