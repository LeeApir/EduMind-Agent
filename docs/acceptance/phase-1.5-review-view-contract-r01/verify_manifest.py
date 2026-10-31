"""Verify the proposal attachments; no calls, runtime authorization or state changes."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EXPECTED = {
    "docs/ADR/0049-visible-review-view.md",
    "docs/acceptance/phase-1.5-review-view-contract-r01/README.md",
    "docs/acceptance/phase-1.5-review-view-contract-r01/VIEW-CONTRACT.md",
    "docs/acceptance/phase-1.5-review-view-contract-r01/OLD-TARGET-MAPPING.md",
    "docs/acceptance/phase-1.5-review-view-contract-r01/EXAMPLES.md",
    "docs/acceptance/phase-1.5-review-view-contract-r01/check_mapping.py",
    "docs/acceptance/phase-1.5-review-view-contract-r01/sample-old-target-inventory.json",
    "docs/acceptance/phase-1.5-review-view-contract-r01/verify_manifest.py",
}


def main() -> None:
    manifest = json.loads((HERE / "manifest.json").read_text())
    assert manifest["status"] == "proposed_not_authorized"
    assert set(manifest["files"]) == EXPECTED
    for name, expected in manifest["files"].items():
        path = ROOT / name
        assert not any(p.is_symlink() for p in (path, *path.parents))
        assert (
            path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected
        )
    print(f"{len(EXPECTED)} proposed files match; no execution grant")


if __name__ == "__main__":
    main()
