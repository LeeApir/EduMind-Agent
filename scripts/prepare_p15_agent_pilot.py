"""Check the pilot development freeze. Preparation only; cannot perform live requests."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1.5-agent-pilot/t069-preparation"


def check() -> dict[str, Any]:
    manifest = json.loads((BASE / "development-freeze.json").read_text())
    for row in manifest["files"]:
        path = ROOT / row["path"]
        if (
            path.is_symlink()
            or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]
        ):
            raise ValueError("DEVELOPMENT_FREEZE_DRIFT")
    return dict(
        state="preparation_only_not_executable",
        candidate_verified=True,
        real_http=0,
        credentials_loaded=False,
        required=[
            "independent assistant truth selection and attestation",
            "same-condition baseline or explicit absolute-only scope",
            "exact live adapter/configuration and compatibility evidence",
            "current provider rates/currency or specifically accepted unknown fees",
            "new exact request/token/money/time/transfer approval",
        ],
        T069_completed=False,
        T070_completed=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    try:
        print(json.dumps(check(), ensure_ascii=False, sort_keys=True))
    except (ValueError, OSError, KeyError):
        print("Preparation refused: development freeze mismatch.")
    return 2  # Preparation cannot become executable through user-edited flags.


if __name__ == "__main__":
    raise SystemExit(main())
