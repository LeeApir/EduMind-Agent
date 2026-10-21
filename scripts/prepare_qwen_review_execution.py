"""Bind the approved zero-call Qwen design to its real execution code; no credentials read."""

# ruff: noqa: E402
import argparse
import json
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.om_diagnostic import stable
from acceptance_support.qwen_review_budget import sha
from run_qwen_review import BASE, DESIGN, DATABASE
from app.services.learning_policy import active_policy_digest


def build():
    design = json.loads((ROOT / DESIGN / "proposal.json").read_text())
    if (
        stable(design)
        != "7907116b32fe2b086d467e1287fcfb66ef1ed91704950906991b27107fa52ed8"
    ):
        raise ValueError("DESIGN_CHANGED")
    sources = dict(design["sources"])
    for n, h in sources.items():
        if sha((ROOT / n).read_bytes()) != h:
            raise ValueError("SOURCE_CHANGED")
    names = [
        DESIGN + "/" + n
        for n in [
            "proposal.json",
            "candidate-config.json",
            "cases.json",
            "proposed-labels.json",
            "offline-capture.json",
            "official-terms.json",
            "validation.json",
        ]
    ] + [
        "scripts/acceptance_support/qwen_review_budget.py",
        "scripts/acceptance_support/qwen_review_attempt.py",
        "scripts/run_qwen_review.py",
        "scripts/verify_qwen_review_execution.py",
        "scripts/prepare_qwen_review_execution.py",
        "scripts/tests/test_qwen_review_execution.py",
        "scripts/tests/test_qwen_review_attempt.py",
        "scripts/tests/test_qwen_review_budget.py",
        BASE + "/README.md",
        BASE + "/implementation-approval.json",
    ]
    sources.update({n: sha((ROOT / n).read_bytes()) for n in names})
    cases = json.loads((ROOT / DESIGN / "cases.json").read_text())
    labels = json.loads((ROOT / DESIGN / "proposed-labels.json").read_text())
    meta = (ROOT / ".env").lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077:
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    p = {
        "version": "qwen-review-execution-r01",
        "design_sha256": stable(design),
        "implementation_baseline": "0bfab25",
        "execution_root": str(ROOT.resolve()),
        "expiry_local": "2026-10-20T23:59:59+08:00",
        "database_name": DATABASE,
        "endpoint_sha256": design["config"]["endpoint_sha256"],
        "policy_digest": active_policy_digest(),
        "sources": sources,
        "cases_sha256": stable(cases),
        "labels_sha256": stable(labels),
        "slots": design["slots"],
        "cost_micro_cny": design["exact_slot_reserve_micro_cny"],
        "requests": 12,
        "candidate_count": 1,
        "global_ceiling_micro_cny": 164000000,
        "requests_authorized": 0,
        "fees_authorized": 0,
        "output_parameter": 8192,
        "output_reserve": 8202,
        "timeout_seconds": 60,
        "credential_file_metadata": {
            k: getattr(meta, k)
            for k in ["st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"]
        },
        "official_terms_sha256": sha(
            (ROOT / DESIGN / "official-terms.json").read_bytes()
        ),
        "official_sources": json.loads(
            (ROOT / DESIGN / "official-terms.json").read_text()
        )["sources"],
        "response_model_ids": ["qwen3.8-max-0902", "qwen3.8-max-2026-09-02"],
        "phase_gate": "all prior exact receipts human signed; additional screen-pass on4 receipts before8 generalization cases",
        "failure": "persist halt and eliminate sole candidate, no retry/fallback/correction/next-model, preserve original record",
        "generation": "unchanged, public diagnostic fixtures only; connection_test/probe purpose",
    }
    assert (
        p["cost_micro_cny"] == 161071260
        and p["cost_micro_cny"] <= p["global_ceiling_micro_cny"]
    )
    return p


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    p = build()
    path = ROOT / BASE / "proposal.json"
    text = json.dumps(p, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        if path.exists() and path.read_text() != text:
            raise ValueError("REFUSE_OVERWRITE_FROZEN_PACKAGE")
        path.write_text(text)
    print(
        json.dumps(
            {
                "proposal_sha256": stable(p),
                "requests": 12,
                "cost_micro_cny": p["cost_micro_cny"],
                "global_ceiling_micro_cny": 164000000,
                "provider_calls": 0,
                "authorized": False,
            }
        )
    )


if __name__ == "__main__":
    main()
