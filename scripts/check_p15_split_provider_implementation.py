"""Verify approved isolated implementation. --execute always refuses ADR0033 D."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from isolated_diagnostics.p15_split_provider import (  # noqa: E402
    Refused,
    approved_design,
    refuse_live,
)

BASE = ROOT / "docs/acceptance/phase-1.5-split-provider-implementation-r01"


def check():
    approved_design()
    manifest = json.loads((BASE / "manifest.json").read_text())
    required = {
        "scripts/isolated_diagnostics/p15_split_provider.py",
        "scripts/check_p15_split_provider_implementation.py",
        "scripts/tests/test_p15_split_provider.py",
        "backend/tests/test_p15_split_provider.py",
        "docs/ADR/0033-approval-20261027.json",
    }
    if (
        manifest.get("status") != "frozen_isolated_implementation_no_live_authority"
        or manifest.get("real_requests_authorized") != 0
        or not required.issubset(manifest.get("sha256", {}))
    ):
        raise ValueError("IMPLEMENTATION_MANIFEST_INCOMPLETE")
    for name, sha in manifest["sha256"].items():
        path = (ROOT / name).resolve()
        if (
            not path.is_relative_to(ROOT)
            or hashlib.sha256(path.read_bytes()).hexdigest() != sha
        ):
            raise ValueError("IMPLEMENTATION_SOURCE_CHANGED")
    return {
        "isolated_implementation_verified": True,
        "actual_provider_calls": 0,
        "live_execution_ready": False,
        "production_bound_evidence_changed": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.execute:
        try:
            refuse_live()
        except Refused as exc:
            print(str(exc))
            raise SystemExit(2) from None
    print(json.dumps(check()))
