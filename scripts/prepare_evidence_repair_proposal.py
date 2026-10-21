"""Bind a zero-call repair proposal to actual failures; not a semantic judge."""

# ruff: noqa: E402
import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.om_diagnostic import stable
from acceptance_support.phase1_budget import sha

BASE = "docs/acceptance/phase-1-evidence-repair-proposal-r01"
PRIOR = "docs/acceptance/phase-1-review-remaining-r01"


def read(path):
    return json.loads(path.read_text())


def anchor_witness(case, anchor_id):
    matches = [a for a in case["anchors"] if a["anchor_id"] == anchor_id]
    if len(matches) != 1:
        raise ValueError("ANCHOR_ID_INVALID")
    a = matches[0]
    resources = [
        c
        for c in case["material"]["candidates"]
        if c["resource_id"] == a["resource_id"]
    ]
    if len(resources) != 1 or resources[0]["content_digest"] != a["resource_digest"]:
        raise ValueError("ANCHOR_BINDING_INVALID")
    content = resources[0]["envelope"]["content"]
    pointer = a["json_pointer"]
    if not pointer.startswith("/"):
        raise ValueError("ANCHOR_POINTER_INVALID")
    for part in pointer[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        content = content[int(part)] if isinstance(content, list) else content[part]
    if type(content) is not str:
        raise ValueError("ANCHOR_FIELD_NOT_TEXT")
    raw = content.encode()
    start, end = a["start_utf8"], a["end_utf8"]
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start <= end <= len(raw)
    ):
        raise ValueError("ANCHOR_SPAN_INVALID")
    return {
        **deepcopy(a),
        "actual_excerpt": raw[start:end].decode(),
        "scope": "field/span only; semantic relevance requires claim-by-claim review",
    }


def build(root=ROOT):
    proposal = read(root / PRIOR / "proposal.json")
    cases = read(root / PRIOR / "cases.json")
    if (
        stable(proposal)
        != "7b7d495f9fd7d64ad0db40e5b03cc55c01ce804de61f82a99348691186b90d8f"
        or stable(cases) != proposal["cases_sha256"]
    ):
        raise ValueError("HISTORICAL_PACKAGE_CHANGED")
    for n, h in proposal["sources"].items():
        if sha((root / n).read_bytes()) != h:
            raise ValueError("PRODUCTION_OR_FROZEN_SOURCE_CHANGED")
    fact = read(root / PRIOR / "results/fact-contradiction-02.json")
    safety = read(root / PRIOR / "results/reachable-safety-03.json")
    for value, slot in [
        (fact, "fact-contradiction:candidate"),
        (safety, "reachable-safety:candidate"),
    ]:
        if value["material_sha256"] != stable(cases[slot]["material"]):
            raise ValueError("MATERIAL_BINDING_CHANGED")
    fc, sc = cases["fact-contradiction:candidate"], cases["reachable-safety:candidate"]
    rows = [
        {
            "id": "actual-ub-overclaim",
            "origin": "actual_unchanged_finding",
            "material_sha256": stable(sc["material"]),
            "original_finding_index": 2,
            "original_finding": deepcopy(safety["structured_review"]["findings"][2]),
            "anchors": [
                anchor_witness(sc, x)
                for x in safety["structured_review"]["findings"][2]["anchors"]
            ],
            "expected": {
                "overall_review_acceptable": False,
                "core_safety_reject_retained": True,
                "violation": "CONCLUSION_STRONGER_THAN_EVIDENCE",
                "note": "No guaranteed16 does not entail a result unequal16. Do not erase original statement or predict a UB runtime.",
            },
        },
        {
            "id": "actual-fact-secondary-anchor",
            "origin": "actual_unchanged_finding",
            "material_sha256": stable(fc["material"]),
            "original_finding_index": 0,
            "original_finding": deepcopy(fact["structured_review"]["findings"][0]),
            "anchors": [
                anchor_witness(fc, x)
                for x in fact["structured_review"]["findings"][0]["anchors"]
            ],
            "expected": {
                "core_fact_detection": True,
                "every_citation_supports_claim": False,
                "violation": "SECONDARY_ANCHOR_DOES_NOT_SUPPORT_NUMERIC_CLAIM",
                "note": "a1 locates actual18/16 contradiction; a15 is F, not evidence of return16. Historical human continue does not erase this limitation.",
            },
        },
        {
            "id": "synthetic-ub-bounded-conclusion",
            "origin": "authored_proposed_contrast_not_model_output",
            "material_sha256": stable(sc["material"]),
            "proposed_conclusion": "长度3却在源代码可达路径读取a[4]，构成未定义行为，不能保证返回16或正常返回。",
            "anchors": [anchor_witness(sc, "a6")],
            "expected": {
                "evidence_kind": "DEMONSTRATED_SAFETY_DEFECT_WITH_NO_NUMERIC_GUARANTEE",
                "route": "reject",
                "category": "code_safety",
                "severity": "severe",
                "forbidden_inference": "fixed value, guaranteed unequal16 or guaranteed crash",
            },
        },
        {
            "id": "synthetic-defined-sum-fact",
            "origin": "authored_proposed_contrast_not_model_output",
            "material_sha256": stable(fc["material"]),
            "proposed_conclusion": "固定的定义良好求和循环返回16，讲解声明返回18，与代码及讲解自身total16相矛盾。",
            "anchors": [anchor_witness(fc, "a1"), anchor_witness(fc, "a6")],
            "expected": {
                "evidence_kind": "DEMONSTRATED_CONTRADICTION",
                "route": "reject",
                "category": "fact",
                "severity": "severe",
            },
        },
        {
            "id": "synthetic-F-valid-role",
            "origin": "authored_proposed_contrast_not_model_output",
            "material_sha256": stable(fc["material"]),
            "proposed_conclusion": "该题所列答案是F。",
            "anchors": [anchor_witness(fc, "a15")],
            "expected": {
                "supports_this_atomic_claim": True,
                "does_not_prove": "function return value16",
                "note": "Same ID is valid for another claim; never blacklist IDa15 or textF.",
            },
        },
        {
            "id": "logic-no-guarantee-not-negation",
            "origin": "abstract_logic_countermodel_not_C_execution",
            "possible_states": [{"P": True}, {"P": False}],
            "expected": {
                "guaranteed_P": False,
                "guaranteed_not_P": False,
                "invalid_implication": "not(guaranteed P) => guaranteed(not P)",
                "note": "This two-state logical counterexample is not a model of actual UB program outputs.",
            },
        },
        {
            "id": "synthetic-insufficient-evidence",
            "origin": "authored_reasoning_boundary_not_model_output",
            "evidence": "未提供判断外部断言P所需的来源或前提。",
            "expected": {
                "evidence_kind": "INSUFFICIENT_PREMISES",
                "route": "needs_human",
                "findings": [],
                "unresolved": ["明确缺少的来源或前提，不能据此断言非P。"],
            },
        },
    ]
    for name, route in [
        ("trace-complete", "pass"),
        ("gap-and-safety", "reject"),
        ("assessment-gap", "needs_human"),
    ]:
        slot = name + ":candidate"
        c = cases[slot]
        rows.append(
            {
                "id": "retained-" + name,
                "origin": "unchanged_authored_material_control_not_real_result",
                "slot": slot,
                "material_sha256": stable(c["material"]),
                "expected": {
                    "route": route,
                    "note": "Original criterion retained; no real response generated here.",
                },
            }
        )
    # Also retain the separately frozen distributed/support-gap positive/negative material.
    extra_base = root / "docs/acceptance/phase-1-review-suite-r01"
    extra_proposal = read(extra_base / "proposal.json")
    extra_cases = read(extra_base / "cases.json")
    if (
        stable(extra_proposal)
        != "d932bb269cd4a9aaa6038d2c50cc6f4b9fa395516784d08bb46f9862921958f3"
        or stable(extra_cases) != extra_proposal["cases_sha256"]
    ):
        raise ValueError("HISTORICAL_EXTRA_CONTROLS_CHANGED")
    for name, route in [
        ("trace-distributed", "pass"),
        ("plan-only-gap", "needs_human"),
    ]:
        c = extra_cases[name + ":candidate"]
        rows.append(
            {
                "id": "retained-" + name,
                "origin": "unchanged_authored_material_control_not_real_result",
                "slot": name + ":candidate",
                "material_sha256": stable(c["material"]),
                "expected": {
                    "route": route,
                    "note": "Distributed student-visible support counts; internal plan alone does not.",
                },
            }
        )
    matrix = {
        "version": "evidence-repair-regression-spec-v1",
        "status": "PROPOSED_NOT_HUMAN_APPROVED",
        "provider_requests": 0,
        "not_a_semantic_classifier": True,
        "not_a_new_real_acceptance_run": True,
        "cases": rows,
    }
    names = [
        "docs/acceptance/phase-1-review-suite-r01/proposal.json",
        "docs/acceptance/phase-1-review-suite-r01/cases.json",
        PRIOR + "/proposal.json",
        PRIOR + "/cases.json",
        PRIOR + "/results/fact-contradiction-02.json",
        PRIOR + "/results/fact-contradiction-02-human.json",
        PRIOR + "/results/reachable-safety-03.json",
        "backend/app/agents/hybrid_resource_review.py",
        "backend/app/services/learning_policy.py",
        "scripts/prepare_evidence_repair_proposal.py",
        "scripts/tests/test_evidence_repair_proposal.py",
        BASE + "/README.md",
        BASE + "/prompt-candidate.txt",
    ]
    manifest = {
        "version": "evidence-repair-proposal-v1",
        "status": "ZERO_CALL_PROPOSAL_NOT_IMPLEMENTED",
        "baseline": "7319f23",
        "provider_requests": 0,
        "requests_authorized": 0,
        "fees_authorized": 0,
        "sources": {n: sha((root / n).read_bytes()) for n in names},
        "prior_frozen_source_closure_sha256": stable(proposal["sources"]),
        "regression_spec_sha256": stable(matrix),
        "candidate_prompt_sha256": sha(
            (root / BASE / "prompt-candidate.txt").read_bytes()
        ),
        "proposed_versions": {
            "prompt": "evidence-resource-review-v4.5 NOT_ACTIVE",
            "input": "authoritative-review-input-v1 unchanged",
            "output": "resource-review-v4 unchanged",
            "mandatory_check_ids": "unchanged",
        },
        "implementation_approved": False,
        "real_validation_approved": False,
        "old_run": "review-remaining-r01 ADMISSION_FAILED,3/5; last2 NOT_RUN; no budget reuse",
        "semantic_effectiveness": "NOT_TESTED",
        "reader_review": "same-assistant document self-check only; no blind model or human signoff",
        "T040": "blocked",
        "production_mode": "catalog_only",
    }
    return {"proposal.json": manifest, "regression-cases.json": matrix}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    values = build()
    if args.write:
        for n, v in values.items():
            (ROOT / BASE / n).write_text(
                json.dumps(v, ensure_ascii=False, indent=2) + "\n"
            )
    print(
        json.dumps(
            {
                "proposal_sha256": stable(values["proposal.json"]),
                "regression_cases": len(values["regression-cases.json"]["cases"]),
                "provider_requests": 0,
                "active": False,
            }
        )
    )


if __name__ == "__main__":
    main()
