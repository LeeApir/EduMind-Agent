"""Offline checks for a DRAFT contract and arithmetic budget; no rebuild implementation."""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1-plan-correction-proposal-r01"


def budget_case(mapping: int, rebuild: int, pairs: int) -> dict[str, int]:
    if (
        type(mapping) is not int
        or type(rebuild) is not int
        or mapping not in (0, 1)
        or rebuild not in (0, 1)
    ):
        raise ValueError("INVALID_PROPOSED_STAGE_COUNTS")
    baseline = 9 + mapping + 2 * rebuild
    cap = min(6, (20 - baseline) // 2)
    if type(pairs) is not int or not 0 <= pairs <= cap:
        raise ValueError("SHARED_PAIR_BUDGET_EXCEEDED")
    generation = 4 + mapping + rebuild + pairs
    review = 5 + rebuild + pairs
    output = mapping * 512 + (1 + rebuild) * 2048 + (3 + pairs) * 4096 + review * 8192
    return dict(
        mapping=mapping,
        rebuild=rebuild,
        pairs=pairs,
        pair_cap=cap,
        baseline_calls=baseline,
        generation_calls=generation,
        review_calls=review,
        total_calls=generation + review,
        output_tokens_max=output,
    )


def validate_record(
    value: dict[str, Any], *, allowed_verifiers: set[str] | None = None
) -> None:
    """Validate proposed record consistency only; does not execute/authorize any route."""
    schema = json.loads((BASE / "contract.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    model = value["model_result"]
    decision = value["server_assessment"]
    binding = value["binding"]
    anchors = {a["anchor_id"]: a for a in value["anchor_catalog"]}
    if len(anchors) != len(value["anchor_catalog"]) or any(
        a["end_utf8"] <= a["start_utf8"] for a in anchors.values()
    ):
        raise ValueError("ANCHOR_SET_INVALID")
    source_bindings = {
        "user_request": "input_digest",
        "plan": "plan_digest",
        "reference": "reference_digest",
    }
    if any(
        a["source_digest"] != binding[source_bindings[a["source_kind"]]]
        for a in anchors.values()
    ):
        raise ValueError("ANCHOR_BINDING_CHANGED")
    finding_ids = {f["finding_id"] for f in model["findings"]}
    if len(finding_ids) != len(model["findings"]):
        raise ValueError("DUPLICATE_FINDING")
    for f in model["findings"]:
        if not {f["target_anchor"], *f["evidence_anchors"]} <= anchors.keys():
            raise ValueError("UNKNOWN_ANCHOR")
    if (
        set(model["coverage"]["checked"])
        != set(
            [
                "goal_fidelity",
                "internal_consistency",
                "scope",
                "reference_support",
                "downstream_feasibility",
            ]
        )
        or model["coverage"]["unchecked"]
    ):
        if decision["route"] in ["accept_plan", "rebuild_once"]:
            raise ValueError("INCOMPLETE_CHECKS")
    if decision["route"] == "accept_plan" and (
        model["verdict"] != "pass" or model["findings"] or model["unresolved"]
    ):
        raise ValueError("UNRESOLVED_PLAN_CANNOT_PASS")
    if model["verdict"] == "reject" and decision["route"] in [
        "accept_plan",
        "rebuild_once",
    ]:
        raise ValueError("REJECT_CANNOT_BE_AUTO_REPAIRED")
    if decision["route"] == "rebuild_once":
        if (
            decision["rebuilds_already_reserved"]
            or value["request_stage"] != "plan_check"
            or model["verdict"] != "issue"
        ):
            raise ValueError("ONE_INITIAL_PLAN_REBUILD_ONLY")
        if model["unresolved"] or set(decision["verified_finding_ids"]) != finding_ids:
            raise ValueError("ALL_FINDINGS_MUST_BE_RESOLVED")
        proofs = {p["proof_id"]: p for p in value["proofs"]}
        if len(proofs) != len(value["proofs"]):
            raise ValueError("DUPLICATE_PROOF")
        if (
            not decision["proof_ids"]
            or not decision["verified_finding_ids"]
            or not set(decision["proof_ids"]) <= proofs.keys()
        ):
            raise ValueError("INDEPENDENT_PROOF_REQUIRED")
        if not set(decision["verified_finding_ids"]) <= finding_ids:
            raise ValueError("UNKNOWN_VERIFIED_FINDING")
        confirmed = set()
        for pid in decision["proof_ids"]:
            proof = proofs[pid]
            if (
                proof["verifier_id"] not in (allowed_verifiers or set())
                or not proof["machine_checked"]
                or proof["conclusion"] != "confirmed_local_plan_defect"
            ):
                raise ValueError("VERIFIER_NOT_APPROVED")
            if any(
                proof[k] != binding[k]
                for k in ["plan_digest", "input_digest", "reference_digest"]
            ):
                raise ValueError("PROOF_BINDING_CHANGED")
            if not set(proof["evidence_anchors"]) <= anchors.keys():
                raise ValueError("UNKNOWN_PROOF_ANCHOR")
            if not set(proof["finding_ids"]) <= finding_ids:
                raise ValueError("UNKNOWN_PROOF_FINDING")
            confirmed.update(proof["finding_ids"])
        if not set(decision["verified_finding_ids"]) <= confirmed:
            raise ValueError("FINDING_NOT_VERIFIED")
        for f in model["findings"]:
            if f["finding_id"] in decision["verified_finding_ids"] and (
                anchors[f["target_anchor"]]["source_kind"] != "plan"
                or f["suggested_action"] != "consider_rebuild"
                or f["category"]
                not in [
                    "plan_internal_conflict",
                    "unsupported_commitment",
                    "coverage_plan_gap",
                ]
            ):
                raise ValueError("WRONG_REPAIR_TARGET")


def check() -> dict[str, Any]:
    Draft202012Validator.check_schema(
        json.loads((BASE / "contract.schema.json").read_text())
    )
    validate_record(json.loads((BASE / "synthetic-record.json").read_text()))
    rows = [
        budget_case(m, r, k)
        for m in [0, 1]
        for r in [0, 1]
        for k in range(budget_case(m, r, 0)["pair_cap"] + 1)
    ]
    table = json.loads((BASE / "budget.json").read_text())
    if (
        rows != table["enumerated_cases"]
        or max(x["total_calls"] for x in rows) != 20
        or max(x["output_tokens_max"] for x in rows) != 117248
    ):
        raise ValueError("PROPOSED_BUDGET_CHANGED")
    if table["real_requests_authorized"] != 0:
        raise ValueError("PROPOSAL_NOT_EXECUTION_AUTHORITY")
    manifest_path = BASE / "manifest.json"
    if manifest_path.exists():
        import hashlib

        manifest = json.loads(manifest_path.read_text())
        for path, digest in manifest["files"].items():
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
                raise ValueError("PROPOSAL_FILE_CHANGED: " + path)
        if manifest["real_requests_authorized"] != 0:
            raise ValueError("PROPOSAL_AUTHORITY_CHANGED")
    return dict(
        status="draft consistent; NOT approved or implemented",
        cases_checked=len(rows),
        requests_max=20,
        output_tokens_max=117248,
        provider_calls=0,
    )


if __name__ == "__main__":
    print(json.dumps(check()))
