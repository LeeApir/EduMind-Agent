"""Freeze one byte-identical plan-gap request after a zero-call contract audit."""

# ruff: noqa: E402
import argparse
import json
import os
import stat
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.om_diagnostic import stable
from acceptance_support.phase1_budget import sha
from audit_plan_gap_contract import audit, BASE as AUDIT_BASE
from run_plan_gap_location import BASE, SLOT_IDS, REQUESTS, OUTPUT_LIMIT

PRIOR = "docs/acceptance/phase-1-review-suite-r01"
PRIOR_ROOT = "d932bb269cd4a9aaa6038d2c50cc6f4b9fa395516784d08bb46f9862921958f3"
SLOT = SLOT_IDS[0]


def read(p):
    return json.loads(p.read_text())


def review_document(data):
    c = data[SLOT]
    return "\n".join(
        [
            "# plan-only-gap单次定位：材料与判据",
            "",
            "未绑定本包真实预算/标签批准。最多一次，成功或失败后停止。",
            "预期needs_human，具体说明学生可见循环状态与退出边界支持不足；内部计划不算交付；不得虚构缺调用示例fact。",
            "目标：" + c["input_snapshot"]["metadata"]["goal"],
            "材料摘要：" + stable(c["material"]),
            "```json",
            json.dumps(c["material"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )


def build(root=ROOT):
    original = read(root / PRIOR / "proposal.json")
    old = read(root / PRIOR / "cases.json")
    if stable(original) != PRIOR_ROOT or stable(old) != original["cases_sha256"]:
        raise ValueError("HISTORICAL_PACKAGE_CHANGED")
    report = audit(root)
    if (
        report["clear_contract_conflict_found"]
        or read(root / AUDIT_BASE / "audit.json") != report
    ):
        raise ValueError("CONTRACT_AUDIT_REQUIRED")
    sources = deepcopy(original["sources"])
    for name, h in sources.items():
        if sha((root / name).read_bytes()) != h:
            raise ValueError("V44_SOURCE_BASELINE_CHANGED")
    case = deepcopy(old[SLOT])
    wire = bytes.fromhex(case["wire_hex"])
    body = json.loads(wire)
    prior = next(s for s in original["slots"] if s["id"] == SLOT)
    if (
        sha(wire) != prior["wire_sha256"]
        or body["max_output_tokens"] != OUTPUT_LIMIT
        or body["reasoning"] != {"effort": "low"}
    ):
        raise ValueError("ORIGINAL_REQUEST_CHANGED")
    data = {SLOT: case}
    labels = {
        "status": "PROPOSED_NOT_HUMAN_SIGNED",
        "rows": [
            {
                "id": SLOT,
                "kind": "pure_gap",
                "expected_route": "needs_human",
                "findings": [],
                "material_sha256": stable(case["material"]),
                "specific_evidence": "Missing explicit student-visible loop states and exit; no invented callsite fact.",
                "human_specific_evidence_required": True,
            }
        ],
    }
    proof = read(root / BASE / "official-terms.json")
    if (
        proof["model"],
        proof["context_input_ceiling"],
        proof["input_micro_cny_per_million"],
        proof["output_micro_cny_per_million"],
        proof["output_ceiling_per_request_including_reasoning"],
    ) != ("deepseek-flash", 1048576, 2000000, 8000000, 8192):
        raise ValueError("TERMS_CHANGED_REDESIGN_REQUIRED")
    extra = [
        "scripts/run_plan_gap_location.py",
        "scripts/prepare_plan_gap_location.py",
        "scripts/tests/test_plan_gap_location.py",
        "scripts/audit_plan_gap_contract.py",
        "scripts/acceptance_support/schema_failure_observation.py",
        "scripts/tests/test_schema_failure_observation.py",
        AUDIT_BASE + "/audit.json",
        BASE + "/README.md",
        BASE + "/official-terms.json",
        PRIOR + "/proposal.json",
        PRIOR + "/cases.json",
        PRIOR + "/results/plan-only-gap-01.json",
    ]
    sources.update({n: sha((root / n).read_bytes()) for n in extra})
    meta = (root / ".env").lstat()
    if (
        not stat.S_ISREG(meta.st_mode)
        or meta.st_mode & 0o077
        or meta.st_uid != os.geteuid()
    ):
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    cost = 2 * (1048576 + len(wire)) + 8 * OUTPUT_LIMIT
    p = {
        "version": "plan-gap-location-r01",
        "execution_root": str(root.resolve()),
        "expiry_local": "2026-10-18T23:59:59+08:00",
        "requests": REQUESTS,
        "output_token_limit": OUTPUT_LIMIT,
        "requests_authorized": 0,
        "fees_authorized": 0,
        "cost_micro_cny": cost,
        "sources": sources,
        "slots": [deepcopy(prior)],
        "cases_sha256": stable(data),
        "labels_sha256": stable(labels),
        "proof_sha256": stable(proof),
        "credential_file_metadata": {
            k: getattr(meta, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        },
        "contract_audit_sha256": stable(report),
        "historical_source": {
            "package": PRIOR,
            "proposal_sha256": PRIOR_ROOT,
            "slot": SLOT,
            "wire_sha256": sha(wire),
        },
        "unchanged": [
            "entire case and exact HTTP wire",
            "Prompt/Schema/input/examples (none sent)",
            "model/low/8192/temperature0/60s/rubric",
            "production defaults and old stopped ledgers",
        ],
        "changes": [
            "independent one-slot executor/approval/ledger",
            "safe schema-location failure diagnosis only",
        ],
        "stop_rule": "At most one reservation/send. Success exhausts quota; any failure halts. No retries/corrections/fallback. Stop and inspect actual evidence; no guessing old schema field or automatic repair.",
    }
    assert p["slots"][0]["cost_micro_cny"] == cost
    return {
        "proposal.json": p,
        "cases.json": data,
        "proposed-labels.json": labels,
        "token-cost-proof.json": proof,
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    values = build()
    if args.write:
        rendered = {
            k: json.dumps(v, ensure_ascii=False, indent=2) + "\n"
            for k, v in values.items()
        }
        rendered["human-review.md"] = review_document(values["cases.json"])
        for n, s in rendered.items():
            path = ROOT / BASE / n
            if path.exists() and path.read_text() != s:
                raise ValueError("REFUSE_OVERWRITE_FROZEN_PACKAGE")
        for n, s in rendered.items():
            (ROOT / BASE / n).write_text(s)
    p = values["proposal.json"]
    print(
        json.dumps(
            {
                "proposal_sha256": stable(p),
                "requests": REQUESTS,
                "cost_micro_cny": p["cost_micro_cny"],
                "wire_sha256": p["slots"][0]["wire_sha256"],
                "authorized": False,
            }
        )
    )


if __name__ == "__main__":
    main()
