"""Freeze r09 for review without creating approval, a ledger, DNS traffic or key access."""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from acceptance_support.claim_review_prototype import digest, encoded  # noqa: E402
from acceptance_support.derived_diagnostic_budget import DerivedBudget, price  # noqa: E402
from acceptance_support.derived_review_contracts import contracts  # noqa: E402
from prepare_t040_derived_calibration import CASE_IDS, MAX_RESULT, wire_bound  # noqa: E402

BASE_REL = "docs/acceptance/phase-1-t040-derived-calibration-r09"
PRIVATE_REL = "local-materials/phase-1-t040-derived-calibration-r09"
EXPIRES_AT = int(
    datetime(2026, 10, 18, 23, 59, 59, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
)


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment_version(path):
    # Metadata only. Never hash, parse or print the real key during proposal preparation.
    if path.is_symlink() or not path.is_file():
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    st = path.stat()
    return {
        k: getattr(st, k)
        for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    }


def artifacts(root=ROOT, *, credential_file=None):
    base = root / BASE_REL
    proof_path = base / "token-cost-proof.json"
    proof = json.loads(proof_path.read_text())
    if (
        proof["context_token_ceiling"] != 1048576
        or proof["input_overhead_tokens"] != 1048576
        or proof["output_token_ceiling_including_reasoning"] != 8192
        or proof["input_price_micro_per_million"] != 2000000
        or proof["output_price_micro_per_million"] != 8000000
    ):
        raise ValueError("PROOF_CHANGED")
    history_path = root / "docs/acceptance/phase-1-dynamic-v1/history.json"
    history = json.loads(history_path.read_text())
    originals = [
        next(c for c in history["cases"] if c["id"] == cid) for cid in CASE_IDS
    ]
    cases, labels = [], []
    cs = contracts()
    bounds = {s: 1 for s in cs}
    for index, original in enumerate(originals):
        cid = ("queue-error", "correct-control")[index]
        payload = original["payload"]
        if digest(payload) != original["payload_sha256"]:
            raise ValueError("HISTORY_CHANGED")
        cases.append({"id": cid, **payload, "label_sha256": digest(original)})
        labels.append(
            {
                "case_id": cid,
                "historical_case_id": original["id"],
                "kind": original["kind"],
                "original_label_sha256": digest(original),
                "criteria": (
                    ["wrapped_count", "empty_full_ambiguity"]
                    if index == 0
                    else ["no_false_rejection"]
                ),
                "expected_area": original.get("expected_area"),
            }
        )
        for s in ("inventory", "coverage", "claim", "overall"):
            bounds[s] = max(bounds[s], wire_bound(payload, s, cs[s]))
    metadata = environment_version(credential_file or root / ".env")
    credential = {"path": ".env", "metadata": metadata}
    consent = {
        "version": "derived-calibration-consent-v1",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "credential_binding": credential,
        "purpose": "r09 historical diagnostic calibration",
        "payload_sha256": [digest(c["payload"]) for c in originals],
        "no_fallback": True,
        "no_production_opening": True,
    }
    target = {
        "version": "derived-deepseek-target-v1",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "transport": "responses_json_schema",
        "credential_ref": "server-env:" + digest(credential),
        "credential_version": 1,
        "consent_sha256": digest(consent),
    }
    prerequisite_files = [
        "docs/ADR/0014-derived-budget-approval-20261015.json",
        "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
    ]
    connection = json.loads((root / prerequisite_files[1]).read_text())
    if len(connection["observations"]) != 4 or not all(
        x["passed"] is True for x in connection["observations"]
    ):
        raise ValueError("CONNECTION_NOT_PASSED")
    prereq = {p: file_sha(root / p) for p in prerequisite_files}
    generated = {
        "target.json": target,
        "consent.json": consent,
        "labels.json": labels,
        "prerequisites.json": prereq,
    }
    # Existing production/dependency closure plus the new isolated runner and contracts.
    old = json.loads(
        (
            root
            / "docs/acceptance/phase-1-t040-review-coverage-check/run-review_scope-r08.json"
        ).read_text()
    )
    files = {p: file_sha(root / p) for p in old["files"]}
    extra = [
        "scripts/prepare_t040_derived_calibration.py",
        "scripts/prepare_t040_derived_run.py",
        "scripts/run_t040_derived_calibration.py",
        "scripts/acceptance_support/claim_review_prototype.py",
        "scripts/acceptance_support/derived_diagnostic_budget.py",
        "scripts/acceptance_support/derived_review_contracts.py",
        "scripts/acceptance_support/derived_responses_sender.py",
        "backend/tests/test_t040_derived_run.py",
        "backend/tests/test_derived_responses_sender.py",
        "backend/tests/test_derived_diagnostic_budget.py",
        *prerequisite_files,
        BASE_REL + "/token-cost-proof.json",
    ]
    files.update({p: file_sha(root / p) for p in extra})
    files.update(
        {
            BASE_REL + "/" + name: hashlib.sha256(encoded(value)).hexdigest()
            for name, value in generated.items()
        }
    )
    stages = {
        s: {
            **contract,
            "max_wire_bytes": bounds[s],
            "max_result_bytes": MAX_RESULT,
            "input_overhead_tokens": proof["input_overhead_tokens"],
            "max_output_tokens": 8192,
            "input_price_micro_per_million": 2000000,
            "output_price_micro_per_million": 8000000,
            "proof_sha256": file_sha(proof_path),
            "timeout_seconds": 120,
        }
        for s, contract in cs.items()
    }
    full_cost = 2 * sum(
        price(stages[s], bounds[s]) * (16 if s == "claim" else 1)
        for s in ("inventory", "coverage", "claim", "overall")
    )
    manifest = {
        "version": "phase1-derived-diagnostic-v1",
        "run_id": "t040-derived-calibration-r09",
        "phase": "diagnostic",
        "execution_root": str(root.resolve()),
        "ledger_path": PRIVATE_REL + "/budget.sqlite",
        "registry_path": PRIVATE_REL + "/run.registry.json",
        "files": files,
        "target": {"model": "deepseek-flash", "target_sha256": digest(target)},
        "config": {"reasoning": "low", "temperature": 0},
        "currency": "CNY",
        "cases": cases,
        "max_claims": 16,
        "corrections": 0,
        "stages": stages,
        "bounds": {
            "requests": 38,
            "cost_micro": full_cost,
            "expires_at": EXPIRES_AT,
            "overall_seconds": 10800,
        },
        "prerequisite_sha256": digest(prereq),
    }
    validation = object.__new__(DerivedBudget)
    validation.serialized, validation.root = encoded(manifest), root.resolve()
    validation._validate()  # Pure shape/worst-case validation, no authorization or enrollment.
    generated["run-r09.json"] = manifest
    return generated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = artifacts()
    for name, value in generated.items():
        path = ROOT / BASE_REL / name
        if args.check:
            if path.read_bytes() != encoded(value):
                raise ValueError("FREEZE_CHANGED")
        else:
            if path.exists() and path.read_bytes() != encoded(value):
                raise ValueError("FROZEN_ARTIFACT_EXISTS")
            path.write_bytes(encoded(value))
    m = generated["run-r09.json"]
    print(
        json.dumps(
            {
                "state": "AWAITING_EXACT_RUN_APPROVAL",
                "root_sha256": digest(m),
                "potential_requests": 38,
                "cost_micro_cny": m["bounds"]["cost_micro"],
                "provider_requests_authorized": 0,
                "key_read": False,
            }
        )
    )


if __name__ == "__main__":
    main()
