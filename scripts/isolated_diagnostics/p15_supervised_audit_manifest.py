"""Create or check a local review snapshot; this is not a live execution package."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/acceptance/phase-1.5-supervised-encrypted-t102/audit-manifest.json"
FILES = (
    "scripts/isolated_diagnostics/p15_controlled_mock_v1.py",
    "scripts/isolated_diagnostics/p15_encrypted_controller_v1.py",
    "scripts/isolated_diagnostics/p15_supervised_mock_v1.py",
    "scripts/isolated_diagnostics/p15_synthetic_fixtures_v1.py",
    "scripts/isolated_diagnostics/p15_synthetic_guard_v1.py",
    "scripts/isolated_diagnostics/p15_synthetic_vault_v1.py",
    "scripts/isolated_diagnostics/p15_pinned_transport_v1.py",
    "scripts/isolated_diagnostics/p15_minimal_contract.py",
    "scripts/isolated_diagnostics/p15_head_insertion_engine.py",
    "scripts/isolated_diagnostics/p15_pilot_wire.py",
    "scripts/isolated_diagnostics/p15_visible_worker_v1.py",
    "scripts/isolated_diagnostics/p15_visible_review_view_v1.py",
    "scripts/isolated_diagnostics/p15_visible_request_budget_v1.py",
    "scripts/isolated_diagnostics/p15_reference_document_v1.py",
    "scripts/isolated_diagnostics/p15_reference_artifact_v1.py",
    "scripts/isolated_diagnostics/p15_teaching_pilot.py",
    "scripts/isolated_diagnostics/p15_teaching_revision.py",
    "scripts/isolated_diagnostics/p15_bounded_json_v1.py",
    "scripts/isolated_diagnostics/p15_minimal_pilot.py",
    "scripts/isolated_diagnostics/generate_p15_supervised_evidence.py",
    "scripts/isolated_diagnostics/p15_supervised_audit_manifest.py",
    "scripts/tests/test_p15_supervised_encrypted_t102.py",
    "docs/acceptance/phase-1.5-minimal-output-contract-r01/schemas.json",
    "docs/acceptance/phase-1.5-supervised-encrypted-t102/README.md",
    "docs/acceptance/phase-1.5-supervised-encrypted-t102/check_evidence.py",
    "docs/acceptance/phase-1.5-supervised-encrypted-t102/offline-evidence.json.gz",
    "docs/acceptance/phase-1.5-teaching-frozen-r01/manifest.json",
    "backend/pyproject.toml",
    "backend/uv.lock",
)


def contents() -> dict[str, object]:
    return dict(
        version="supervised-encrypted-review-snapshot-v1",
        scope="Selected development files for independent review; not a complete runtime closure or live grant.",
        independent_samples_selected=False,
        real_provider_calls=0,
        files={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES},
    )


if __name__ == "__main__":
    actual = contents()
    if sys.argv[1:] == ["--write"]:
        OUTPUT.write_text(json.dumps(actual, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print("review snapshot written; no Provider calls")
    elif sys.argv[1:] == ["--check"]:
        if json.loads(OUTPUT.read_text()) != actual:
            raise SystemExit("review snapshot mismatch")
        print("selected review files match; no Provider calls")
    else:
        raise SystemExit("use --write or --check")
