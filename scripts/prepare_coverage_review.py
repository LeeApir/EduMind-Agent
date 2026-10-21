"""Freeze coverage rubric calibration offline; never authorize or send requests."""

# ruff: noqa: E402
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.coverage_standard import SLOTS, cases, reassess
from acceptance_support.om_diagnostic import dump, hash_bytes, price, stable

BASE = "docs/acceptance/phase-1-coverage-r04"
EXTRA = (
    "backend/app/agents/review_delivery.py",
    "backend/tests/test_review_delivery.py",
    "docs/ADR/0016-student-visible-objective-coverage.md",
    "scripts/acceptance_support/coverage_standard.py",
    "scripts/prepare_coverage_review.py",
    "scripts/tests/test_coverage_review.py",
)


def build(root=ROOT):
    oldbase = root / "docs/acceptance/phase-1-om-admission-r03"
    old = json.loads((oldbase / "proposal.json").read_text())
    if (
        stable(old)
        != "81d18bc3c0c166bb33c3ee200543d074930a1166011ec0111313cbec7ccd3238"
    ):
        raise ValueError("HISTORICAL_PROPOSAL_CHANGED")
    paths = set(old["sources"]) | set(EXTRA)
    paths |= {str(p.relative_to(root)) for p in oldbase.rglob("*") if p.is_file()}
    sources = {p: hash_bytes((root / p).read_bytes()) for p in sorted(paths)}
    data = cases(root)
    control = data.pop("implementation-only-offline")
    labels = {
        "status": "PROPOSED_NOT_INDEPENDENT_HUMAN_SIGNOFF",
        "rows": [
            {
                "id": name,
                "expected_route": "pass"
                if name.startswith("trace-")
                else "needs_human",
                "pure_gap_must_not_be_fabricated_fact": not name.startswith("trace-"),
                "actual_semantic_finding_requires_independent_review": True,
            }
            for name in SLOTS
        ],
    }
    slots = [
        {
            "id": name,
            "wire_sha256": hash_bytes(bytes.fromhex(data[name]["wire_hex"])),
            "wire_bytes": len(bytes.fromhex(data[name]["wire_hex"])),
            "conditional_cost_micro_cny": price(
                len(bytes.fromhex(data[name]["wire_hex"]))
            ),
        }
        for name in SLOTS
    ]
    artifacts = {
        "cases.json": data,
        "offline-implementation-control.json": control,
        "reassessment.json": reassess(root),
        "proposed-labels.json": labels,
    }
    artifacts["proposal.json"] = {
        "version": "student-visible-coverage-r04-v1",
        "sources": sources,
        "artifacts": {p: stable(v) for p, v in artifacts.items()},
        "prior_proposal_sha256": stable(old),
        "slots": slots,
        "proposed_requests": 4,
        "requests_authorized": 0,
        "fees_authorized": 0,
        "provider_requests_this_preparation": 0,
        "conditional_budget_micro_cny": sum(
            s["conditional_cost_micro_cny"] for s in slots
        ),
        "output_token_cap_total": 8192,
        "price_basis": (
            "Historical r03 token-cost-proof.json; not newly verified pricing. "
            "Recheck before execution."
        ),
        "execution_status": "PLAN_ONLY_NO_EXECUTOR_ADMISSION_OR_CREDENTIAL_SNAPSHOT",
        "required_before_execution": [
            "independent labels review of exact new material",
            "recheck official model/window/CNY pricing/output contract on execution day",
            (
                "bind an independently tested executor, fresh credentials metadata "
                "and a new exact budget approval"
            ),
            "send one slot at a time; stop on any failure or need for human adjudication",
        ],
        "old_ledgers_results_labels": "read only; no halt cleared or unused allowance inherited",
        "formal_t040": "blocked; calibration is not formal acceptance or severe-error recall",
    }
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    values = build()
    base = ROOT / BASE
    if args.write:
        if base.exists():
            raise SystemExit(
                "Refuse overwriting an existing freeze; create a new revision."
            )
        base.mkdir(parents=True)
        for name, value in values.items():
            dump(base / name, value)
    else:
        for name, value in values.items():
            if json.loads((base / name).read_text()) != value:
                raise SystemExit("FREEZE_CHANGED: " + name)
    print("coverage proposal root=" + stable(values["proposal.json"]))


if __name__ == "__main__":
    main()
