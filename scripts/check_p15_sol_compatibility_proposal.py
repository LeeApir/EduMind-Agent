"""Verify the frozen offline proposal. --execute is unconditionally unavailable."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1.5-sol-compatibility-plan-r01"


def check():
    manifest = json.loads((BASE / "manifest.json").read_bytes())
    required = {
        "docs/ADR/0036-sol-known-difference-proposal.md",
        "scripts/isolated_diagnostics/p15_sol_compatibility_proposal.py",
        "scripts/check_p15_sol_compatibility_proposal.py",
        "scripts/tests/test_p15_sol_compatibility_proposal.py",
        str((BASE / "scene-review.schema.json").relative_to(ROOT)),
        str((BASE / "scene-review-prompt.txt").relative_to(ROOT)),
    }
    if (
        manifest.get("status") != "frozen_offline_proposal_not_execution_authority"
        or not required <= manifest.get("sha256", {}).keys()
    ):
        raise ValueError("PROPOSAL_MANIFEST_INCOMPLETE")
    for name, sha in manifest["sha256"].items():
        p = (ROOT / name).resolve()
        if (
            not p.is_relative_to(ROOT)
            or hashlib.sha256(p.read_bytes()).hexdigest() != sha
        ):
            raise ValueError("FROZEN_PROPOSAL_CHANGED")
    policy = json.loads((BASE / "policy.json").read_bytes())
    if (
        policy["new_real_requests_authorized"] != 0
        or policy["automatic_pointer_normalization"] is not False
        or policy["request_reasoning"] != "low"
        or len(policy["known_suffix"]) != 37
    ):
        raise ValueError("PROPOSAL_SCOPE_CHANGED")
    return {
        "proposal_verified": True,
        "live_execution_authorized": False,
        "real_calls_this_check": 0,
        "production_admission": False,
        "files_verified": len(manifest["sha256"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        print("PROPOSAL_ONLY_NO_REAL_EXECUTION_AUTHORITY")
        return 2
    print(json.dumps(check()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
