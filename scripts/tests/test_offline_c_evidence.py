"""Synthetic repackaging for evidence checks; does not rerun C or rewrite originals."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from offline_c_evidence import check_report, seal_report  # noqa: E402
from offline_c_fixtures import AdmissionError  # noqa: E402


@pytest.fixture
def example(tmp_path):
    # Historical execution is only a synthetic tape for validator regressions.
    report = copy.deepcopy(
        json.loads(
            (ROOT / "docs/acceptance/offline-c-t068/ownership.json").read_bytes()
        )
    )
    report["execution_baseline_commit"] = report["cases"][0]["bindings"][
        "baseline_commit"
    ]
    seal_report(report, tmp_path)
    return report, tmp_path


def test_valid_complete_evidence_keeps_defects_and_publication_boundary(example):
    _, directory = example
    value = check_report(directory / "report.json")
    assert value["integrity_valid"] and value["execution_complete"]
    assert value["sample_checks_fail"] == 6 and value["not_run"] == 4
    assert value["publication_qualified"] is False and value["provider_calls"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "source_binding",
        "driver_binding",
        "wrong_status",
        "wrong_state",
        "wrong_memory",
        "wrong_compiler",
        "missing_case",
        "duplicate_case",
        "extra_field",
        "lsan_claim",
        "mixed_baseline",
    ],
)
def test_semantic_or_binding_tampering_is_rejected_even_if_resealed(example, mutation):
    report, directory = example
    case = report["cases"][0]
    if mutation == "source_binding":
        case["bindings"]["source"] = "a" * 64
    elif mutation == "driver_binding":
        case["bindings"]["driver"] = "a" * 64
    elif mutation == "wrong_status":
        case["status"] = "fail"
    elif mutation == "wrong_state":
        case["observations"]["per_insert_states"][0]["values"] = [99]
    elif mutation == "wrong_memory":
        case["isolation"]["effective"]["Memory"] = 0
    elif mutation == "wrong_compiler":
        case["commands"][0]["argv"].append("-Wno-everything")
    elif mutation == "missing_case":
        report["cases"].pop()
    elif mutation == "duplicate_case":
        report["cases"][-1] = copy.deepcopy(case)
    elif mutation == "extra_field":
        case["explanation"] = "synthetic unsupported claim"
    elif mutation == "lsan_claim":
        case["observations"]["lsan"] = "passed"
    elif mutation == "mixed_baseline":
        case["bindings"]["baseline_commit"] = "a" * 40
    seal_report(report, directory)
    with pytest.raises((AdmissionError, AssertionError, ValueError)):
        check_report(directory / "report.json")


def test_missing_or_byte_tampered_case_file_rejected(example):
    report, directory = example
    target = directory / report["evidence_index"][0]["path"]
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(AdmissionError):
        check_report(directory / "report.json")
    target.unlink()
    with pytest.raises(AdmissionError):
        check_report(directory / "report.json")
