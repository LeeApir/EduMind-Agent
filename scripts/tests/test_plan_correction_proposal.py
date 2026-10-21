"""Synthetic contract consistency and arithmetic; no semantic or live-model evidence."""

# ruff: noqa: E402
from copy import deepcopy
import itertools
import json
from pathlib import Path
import sys

import pytest
from jsonschema import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_plan_correction_proposal import BASE, budget_case, check, validate_record


def record():
    return json.loads((BASE / "synthetic-record.json").read_text())


def rebuild_record():
    x = record()
    x["model_result"]["verdict"] = "issue"
    x["model_result"]["unresolved"] = []
    x["model_result"]["findings"][0]["suggested_action"] = "consider_rebuild"
    x["server_assessment"].update(
        route="rebuild_once", verified_finding_ids=["f1"], proof_ids=["22222222-2222-4222-8222-222222222222"]
    )
    x["proofs"] = [
        dict(
            proof_id="22222222-2222-4222-8222-222222222222",
            verifier_id="synthetic-test",
            verifier_version="v1",
            plan_digest=x["binding"]["plan_digest"],
            input_digest=x["binding"]["input_digest"],
            reference_digest=x["binding"]["reference_digest"],
            finding_ids=["f1"],
            evidence_anchors=["p1"],
            premises_digest="1" * 64,
            conclusion="confirmed_local_plan_defect",
            machine_checked=True,
        )
    ]
    return x


def test_frozen_table_and_synthetic_shape():
    assert check()["cases_checked"] == 22
    validate_record(record())


@pytest.mark.parametrize(
    "m,r,allocation",
    [
        (m, r, a)
        for m in (0, 1)
        for r in (0, 1)
        for a in itertools.product(range(3), repeat=3)
    ],
)
def test_all_resource_allocations_share_budget(m, r, allocation):
    pairs = sum(allocation)
    if pairs > budget_case(m, r, 0)["pair_cap"]:
        with pytest.raises(ValueError, match="SHARED_PAIR"):
            budget_case(m, r, pairs)
    else:
        row = budget_case(m, r, pairs)
        assert row["total_calls"] == 9 + m + 2 * r + 2 * pairs <= 20
        assert row["generation_calls"] + row["review_calls"] == row["total_calls"]
        assert row["output_tokens_max"] <= 117248


@pytest.mark.parametrize(
    "args", [(True, 0, 0), (0, False, 0), (0, 2, 0), (0, 0, True), (0, 0, 6), (0, 1, 5)]
)
def test_invalid_or_excessive_budget(args):
    with pytest.raises(ValueError):
        budget_case(*args)


def test_proof_is_not_available_by_default():
    with pytest.raises(ValueError, match="VERIFIER_NOT_APPROVED"):
        validate_record(rebuild_record())
    # Synthetic consistency only: no verifier computation, authorization, or rebuild is performed.
    validate_record(rebuild_record(), allowed_verifiers={"synthetic-test"})


@pytest.mark.parametrize(
    "mutation",
    [
        "unresolved",
        "recheck",
        "reserved",
        "missingproof",
        "wrongsource",
        "binding",
        "unchecked",
        "extra",
        "otherfinding",
        "reject",
    ],
)
def test_evidence_and_route_guards(mutation):
    x = deepcopy(rebuild_record())
    if mutation == "unresolved":
        x["model_result"]["unresolved"] = ["unknown"]
    elif mutation == "recheck":
        x["request_stage"] = "plan_recheck"
    elif mutation == "reserved":
        x["server_assessment"]["rebuilds_already_reserved"] = 1
    elif mutation == "missingproof":
        x["proofs"] = []
    elif mutation == "wrongsource":
        x["model_result"]["findings"][0]["target_anchor"] = "g1"
    elif mutation == "binding":
        x["anchor_catalog"][0]["source_digest"] = "2" * 64
    elif mutation == "unchecked":
        x["model_result"]["coverage"]["unchecked"] = ["missing"]
    elif mutation == "extra":
        x["model_result"]["repair_allowed"] = True
    elif mutation == "otherfinding":
        x["proofs"][0]["finding_ids"].append("invented")
    elif mutation == "reject":
        x["model_result"]["verdict"] = "reject"
    with pytest.raises((ValueError, ValidationError)):
        validate_record(x, allowed_verifiers={"synthetic-test"})


def test_pass_cannot_hide_findings():
    x = record()
    x["server_assessment"]["route"] = "accept_plan"
    x["model_result"]["verdict"] = "pass"
    with pytest.raises(ValueError, match="UNRESOLVED_PLAN"):
        validate_record(x)
