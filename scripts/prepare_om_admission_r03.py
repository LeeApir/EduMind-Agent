"""Prepare fixed-ID calibration only; keeps all stopped rounds and approvals immutable."""

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
from acceptance_support.om_admission_r02 import SLOTS, cases
from acceptance_support.om_diagnostic import dump, hash_bytes, price, stable
from run_om_admission_r03 import BASE

ALLOWED_CHANGES = {
    "backend/app/agents/hybrid_resource_review.py",
    "backend/app/services/learning_policy.py",
    "backend/tests/test_hybrid_review_scope.py",
    "scripts/tests/test_om_admission_r02.py",
}


def build(root=ROOT):
    oldbase = root / "docs/acceptance/phase-1-om-admission-r02"
    old = json.loads((oldbase / "proposal.json").read_text())
    if (
        stable(old)
        != "858b485f68d889c5aa224185ecdd940c47fbe05e4a6f3876428658d370697101"
    ):
        raise ValueError("HISTORICAL_PROPOSAL_CHANGED")
    for name, key in (
        ("cases.json", "cases_sha256"),
        ("proposed-labels.json", "labels_sha256"),
        ("token-cost-proof.json", "proof_sha256"),
    ):
        if stable(json.loads((oldbase / name).read_text())) != old[key]:
            raise ValueError("HISTORICAL_MATERIAL_CHANGED")
    files = {p: hash_bytes((root / p).read_bytes()) for p in old["sources"]}
    changes = {
        p: {"before": h, "after": files[p]}
        for p, h in old["sources"].items()
        if h != files[p]
    }
    if set(changes) != ALLOWED_CHANGES:
        raise ValueError("UNEXPECTED_IMPLEMENTATION_CHANGE")
    extras = [
        "backend/tests/test_hybrid_review_check_ids.py",
        "scripts/prepare_om_admission_r03.py",
        "scripts/run_om_admission_r03.py",
        "scripts/tests/test_om_admission_r03.py",
        "docs/agents/review-check-ids-v4.2.md",
        "docs/acceptance/phase-1-om-admission-r02/proposal.json",
        "docs/acceptance/phase-1-om-admission-r02/cases.json",
        "docs/acceptance/phase-1-om-admission-r02/proposed-labels.json",
        "docs/acceptance/phase-1-om-admission-r02/token-cost-proof.json",
        "docs/acceptance/phase-1-om-admission-r02/run-approval.json",
        "docs/acceptance/phase-1-om-admission-r02/results/correct-unit-01.json",
    ]
    files.update({p: hash_bytes((root / p).read_bytes()) for p in extras})
    data = cases(root)
    labels = deepcopy(json.loads((oldbase / "proposed-labels.json").read_text()))
    labels["status"] = (
        "R03_PROPOSALS_REQUIRE_INDEPENDENT_REVIEW_NOT_FORMAL_GROUND_TRUTH"
    )
    proof = deepcopy(json.loads((oldbase / "token-cost-proof.json").read_text()))
    proof["prior_proof_sha256"] = stable(proof)
    proof["scope"] = (
        "New r03 fixed-ID calibration only; no old approval inherited. Recheck prices on execution day."
    )
    st = (root / ".env").lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.geteuid():
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
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
        **deepcopy(old),
        "version": "om-admission-r03-v1",
        "execution_root": str(root.resolve()),
        "sources": files,
        "prior_proposal_sha256": stable(old),
        "implementation_changes": changes,
        "cases_sha256": stable(data),
        "labels_sha256": stable(labels),
        "proof_sha256": stable(proof),
        "credential_file_metadata": {
            k: getattr(st, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        },
        "slots": slots,
        "cost_micro_cny": sum(s["cost_micro_cny"] for s in slots),
        "status": "PREPARED_NOT_AUTHORIZED",
        "requests_authorized": 0,
        "fees_authorized": 0,
        "scope": "Fixed-check-ID repair calibration; same paired authored cases, NOT independent holdout or formal acceptance.",
        "prior_run": "r02 stopped after 1 request; r01 stopped after 2. No remaining slots, ledger or approval reused.",
        "schema_policy": "coverage.checked exact own-scope enum/unique; actual finding anchor IDs enum; partial coverage/uncertainty still allowed, not forced pass.",
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
                "requests_proposed": p["requests"],
                "cost_cap_micro_cny": p["cost_micro_cny"],
                "provider_requests": 0,
                "requests_authorized": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
