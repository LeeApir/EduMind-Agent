"""Freeze repaired scope calibration separately; no credential bytes, approval or calls."""

# ruff: noqa: E402
import argparse
import json
import os
import stat
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.om_admission_r02 import BASE, SLOTS, cases
from acceptance_support.om_diagnostic import dump, hash_bytes, price, stable

ALLOWED_CHANGES = {
    "backend/app/agents/hybrid_resource_review.py",
    "backend/app/services/learning_policy.py",
    "scripts/tests/test_om_admission.py",
}


def build(root=ROOT):
    oldbase = root / "docs/acceptance/phase-1-om-admission-r01"
    old = json.loads((oldbase / "proposal.json").read_text())
    if (
        stable(old)
        != "28e25a016c1689c8b27ae52284edb91244fec85b4f24c19297673377a2b17057"
    ):
        raise ValueError("HISTORICAL_PROPOSAL_CHANGED")
    proof = deepcopy(json.loads((oldbase / "token-cost-proof.json").read_text()))
    for name, key in (
        ("cases.json", "cases_sha256"),
        ("proposed-labels.json", "labels_sha256"),
        ("token-cost-proof.json", "proof_sha256"),
    ):
        if stable(json.loads((oldbase / name).read_text())) != old[key]:
            raise ValueError("HISTORICAL_MATERIAL_CHANGED")
    proof["prior_proof_sha256"] = stable(proof)
    proof["scope"] = (
        "New r02 calibration; same checked-on day and price/window contract, not prior approval."
    )
    files = {p: hash_bytes((root / p).read_bytes()) for p in old["sources"]}
    changes = {
        p: {"before": h, "after": files[p]}
        for p, h in old["sources"].items()
        if h != files[p]
    }
    if set(changes) != ALLOWED_CHANGES:
        raise ValueError("UNEXPECTED_IMPLEMENTATION_CHANGE")
    extra = [
        "backend/tests/test_hybrid_review_scope.py",
        "scripts/acceptance_support/om_admission_r02.py",
        "scripts/prepare_om_admission_r02.py",
        "scripts/run_om_admission_r02.py",
        "scripts/tests/test_om_admission_r02.py",
        "docs/agents/review-scope-v4.1.md",
        "docs/acceptance/phase-1-om-admission-r01/proposal.json",
        "docs/acceptance/phase-1-om-admission-r01/cases.json",
        "docs/acceptance/phase-1-om-admission-r01/proposed-labels.json",
        "docs/acceptance/phase-1-om-admission-r01/token-cost-proof.json",
        "docs/acceptance/phase-1-om-admission-r01/run-approval.json",
        "docs/acceptance/phase-1-om-admission-r01/results/correct-unit-02.json",
        "docs/acceptance/phase-1-om-admission-r01/results/plan-01-human.json",
    ]
    files.update({p: hash_bytes((root / p).read_bytes()) for p in extra})
    st = (root / ".env").lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.geteuid():
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    data = cases(root)
    labels = {
        "status": "NEW_PROPOSALS_PENDING_INDEPENDENT_HUMAN_REVIEW",
        "correct-unit": "覆盖本次求和轨迹/边界目标与练习，应自动pass。未声称节点全面掌握，不要求补教所有图谱目标。",
        "missing-unit-objective": "计划明确承诺total逐步变化与停止边界，但讲解/练习缺直接轨迹教学/测量。应具体定位覆盖缺口并reject或needs_human；不强求fact或difficulty类别。",
        "reachable-safety": "调用sum时必达a[4]越界；须具体检出并说明合法下标0..2与影响，主类code_safety。",
        "fact-contradiction": "讲解声称返回18，实际sum及轨迹得16；须具体检出，主类fact，不凭空指控安全错误。",
        "note": "Failed-control calibration pairs; not independent holdout or formal score. Extra findings require individual evidence review.",
    }
    slots = [
        {
            "id": name,
            "wire_sha256": hash_bytes(bytes.fromhex(data[name]["wire_hex"])),
            "wire_bytes": len(bytes.fromhex(data[name]["wire_hex"])),
            "cost_micro_cny": price(len(bytes.fromhex(data[name]["wire_hex"]))),
        }
        for name in SLOTS
    ]
    proposal = {
        "version": "om-admission-r02-v1",
        "execution_root": str(root.resolve()),
        "sources": files,
        "prior_proposal_sha256": stable(old),
        "implementation_changes": changes,
        "cases_sha256": stable(data),
        "labels_sha256": stable(labels),
        "proof_sha256": stable(proof),
        "target": deepcopy(old["target"]),
        "credential_file_metadata": {
            k: getattr(st, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        },
        "slots": slots,
        "requests": 4,
        "cost_micro_cny": sum(s["cost_micro_cny"] for s in slots),
        "total_output_tokens_including_reasoning": 8192,
        "timeout_seconds": 60,
        "retries": 0,
        "fallback": False,
        "expiry_local": "2026-10-18T23:59:59+08:00",
        "status": "PREPARED_NOT_AUTHORIZED",
        "requests_authorized": 0,
        "fees_authorized": 0,
        "scope": "Scope repair calibration only; four fixed reviews, no plan or formal acceptance.",
        "advance": "One invocation/one request; independent exact receipt human continue before next.",
        "stop": deepcopy(old["stop"]),
        "prior_run": "r01 stopped after 2 requests; no old ledger/remaining requests/approvals reused; old results unchanged.",
        "remaining_formal_gates": deepcopy(old["remaining_formal_gates"]),
    }
    return {
        "proposal.json": proposal,
        "cases.json": data,
        "proposed-labels.json": labels,
        "token-cost-proof.json": proof,
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    values = build()
    base = ROOT / BASE
    if args.check:
        if any(json.loads((base / k).read_text()) != v for k, v in values.items()):
            raise SystemExit("FREEZE_CHANGED")
    else:
        base.mkdir(parents=True, exist_ok=True)
        if any((base / k).exists() for k in values):
            raise SystemExit("FREEZE_ALREADY_EXISTS")
        for k, v in values.items():
            dump(base / k, v)
    p = values["proposal.json"]
    print(
        json.dumps(
            {
                "root_sha256": stable(p),
                "requests_proposed": 4,
                "cost_cap_micro_cny": p["cost_micro_cny"],
                "provider_requests": 0,
                "requests_authorized": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
