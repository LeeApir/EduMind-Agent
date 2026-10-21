"""Offline 20-case route matrix and full-denominator reporting; no semantic quality score."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from acceptance_support.om_preparation import (  # noqa: E402
    ROUTE_SCENARIOS,
    audit_metrics,
    generation_metrics,
    preparation,
)
from test_hybrid_resource_review import answer, candidate_workspace  # noqa: E402
from test_planned_scene_generation import fill, workspace  # noqa: E402

from app.agents.hybrid_resource_review import UNIT_CHECKS, hard_checks, route_review  # noqa: E402
from app.services.learning_contract import LearningContractError  # noqa: E402
from app.services.teaching_actions import (  # noqa: E402
    anchor_catalog,
    assemble_actions,
    validate_actions,
)

EXPECTED = {
    "clean_pass": "pass",
    "explicit_uncertainty": "needs_human",
    "unchecked_scope": "needs_human",
    "missing_required_check": "needs_human",
    "label_only_condition": "needs_human",
    "label_only_impact": "needs_human",
    "whitespace_condition": "needs_human",
    "unknown_anchor": "failed",
    "old_protocol": "failed",
    "pass_with_finding": "failed",
    "reject_without_finding": "failed",
    "human_without_unknown": "failed",
    "unit_revise": "failed",
    "unit_uncertainty": "needs_human",
    "unit_serious_reject": "reject",
    "local_eval": "failed",
    "local_file_io": "failed",
    "open_exercise": "failed",
    "stale_actions": "failed",
    "changed_content": "failed",
}


@pytest.mark.parametrize("scenario", ROUTE_SCENARIOS)
def test_twenty_route_scenarios_use_real_gates(scenario):
    def perform():
        w = candidate_workspace()
        candidate = w.candidates()[0]
        a = answer()
        scope = "resource"
        if scenario == "explicit_uncertainty":
            a = answer("needs_human")
        if scenario == "unchecked_scope":
            a["coverage"]["unchecked"] = ["code_safety"]
        if scenario == "missing_required_check":
            a["coverage"]["checked"] = ["facts"]
        if scenario in ("label_only_condition", "label_only_impact", "whitespace_condition"):
            a = answer("revise")
            key = "impact" if scenario == "label_only_impact" else "condition_or_counterexample"
            a["findings"][0][key] = " " if scenario == "whitespace_condition" else "fact"
        if scenario == "unknown_anchor":
            a = answer("revise")
            a["findings"][0]["anchors"] = ["foreign"]
        if scenario == "old_protocol":
            a["schema_version"] = "resource-review-v3"
        if scenario == "pass_with_finding":
            a = answer("revise")
            a["verdict"] = "pass"
        if scenario == "reject_without_finding":
            a["verdict"] = "reject"
        if scenario == "human_without_unknown":
            a["verdict"] = "needs_human"
        if scenario.startswith("unit_"):
            scope = "unit"
            verdict = {
                "unit_revise": "revise",
                "unit_uncertainty": "needs_human",
                "unit_serious_reject": "reject",
            }[scenario]
            a = answer(verdict, "unit")
            a["coverage"]["checked"] = sorted(UNIT_CHECKS)
        if scenario in ("local_eval", "local_file_io", "open_exercise"):
            full = workspace()
            candidates = fill(full)
            role = "exercise" if scenario == "open_exercise" else "code"
            envelope = deepcopy(next(c.envelope for c in candidates if c.role == role))
            if role == "code":
                envelope["content"]["source"] = (
                    'eval("1")' if scenario == "local_eval" else 'open("/tmp/x")'
                )
            else:
                envelope["content"]["items"][0]["question"] = "请写一段开放解释。"
            changed = full.stage(role, envelope)
            hard_checks(changed)
            return "pass"
        if scenario in ("stale_actions", "changed_content"):
            candidates = fill(workspace())
            actions = assemble_actions(candidates)
            if scenario == "stale_actions":
                actions["actions"][0]["resource_id"] = candidates[1].id
            else:
                candidates[0].envelope["content"]["markdown"] = "modified candidate"
            validate_actions(actions, candidates)
            return "pass"
        return route_review(a, scope=scope, catalog=anchor_catalog((candidate,)))["verdict"]

    if EXPECTED[scenario] == "failed":
        with pytest.raises(LearningContractError):
            perform()
    else:
        assert perform() == EXPECTED[scenario]


def test_full_denominators_and_humans_never_fill_automatic_numerator():
    slots = [f"new-target-{i + 1:03}" for i in range(100)]
    rows = [
        {
            "id": id,
            "status": "auto" if i < 94 else "human_approved",
            "first_schema": i < 98,
            "independent_fact_pass": True,
            "provider_requests": 8,
        }
        for i, id in enumerate(slots)
    ]
    report = generation_metrics(rows, slots)
    assert report["denominator"] == 100 and report["automatic_success"] == 94
    assert report["human_approved"] == 6 and report["mixed_publishable"] == 100
    assert report["first_schema"] == 98 and report["automatic_gate_passed"] is False
    sparse = generation_metrics(rows[:1], slots)
    assert sparse["not_run"] == 99 and sparse["denominator"] == 100
    with pytest.raises(ValueError):
        generation_metrics([rows[0], rows[0]], slots)
    with pytest.raises(ValueError):
        generation_metrics([dict(rows[0], id="old-r11-slot")], slots)


def test_audit_detected_classification_control_and_completion_are_separate():
    severe = audit_metrics(
        "severe",
        [
            {
                "id": "new-severe-01",
                "concrete_detected": True,
                "classification_correct": False,
                "unsupported_findings": 1,
            }
        ],
    )
    assert severe["denominator"] == 20 and severe["concrete_detected"] == 1
    assert severe["classification_correct"] == 0 and severe["unsupported_findings"] == 1
    assert (
        audit_metrics(
            "correct",
            [
                {
                    "id": "new-correct-01",
                    "automatic_verdict": "needs_human",
                    "independent_fact_pass": True,
                }
            ],
        )["correct_auto_pass"]
        == 0
    )
    assert (
        audit_metrics("long", [{"id": "new-long-01", "completed": True, "schema_valid": False}])[
            "long_complete"
        ]
        == 0
    )


def test_preparation_has_new_slots_no_run_authority_and_frozen_sources():
    value = preparation()
    assert len(value["targets"]) == 100 and len({s["id"] for s in value["targets"]}) == 100
    assert len(value["diagnostics"]) == 8 and len(value["offline_route_scenarios"]) == 20
    assert {k: len(v) for k, v in value["benchmarks"].items()} == {
        "severe": 20,
        "correct": 20,
        "long": 10,
    }
    budget = value["budget"]
    assert budget["total_request_ceiling"] == 160 + 2000 + 200 == 2360
    assert budget["cost_ceiling_micro_cny"] is None and budget["fee_authorized_micro_cny"] == 0
    assert budget["provider_requests_authorized"] == 0
    assert all(
        ".env" not in s["path"] and "local-materials" not in s["path"] for s in value["sources"]
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare_om_redesign_acceptance.py"), "--run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "NOT_AUTHORIZED"
    assert json.loads(result.stdout)["provider_requests"] == 0


def test_concrete_fifty_materials_are_schema_valid_separate_from_unapproved_labels():
    from acceptance_support.om_benchmarks import benchmark_materials

    from app.agents.learning_resource_schema import validate_learning_resource
    from app.services.learning_contract import canonical, validate_contract

    materials, labels = benchmark_materials()
    assert {k: len(v) for k, v in materials.items()} == {"severe": 20, "correct": 20, "long": 10}
    assert len(labels) == 50
    for kind, items in materials.items():
        for item in items:
            unit = item["unit"]
            validate_contract(unit["plan_draft"], "plan_generation")
            assert sum(len(canonical(r["content"])) for r in unit["resources"]) <= 48 * 1024
            for resource in unit["resources"]:
                validate_learning_resource(resource, expected_type=resource["resource_type"])
            assert "expected_automatic_result" not in unit
    assert all(label["status"].endswith("PENDING_INDEPENDENT_HUMAN_REVIEW") for label in labels)
    assert all(
        len(item["unit"]["resources"][0]["content"]["markdown"].encode()) > 10000
        for item in materials["long"]
    )
