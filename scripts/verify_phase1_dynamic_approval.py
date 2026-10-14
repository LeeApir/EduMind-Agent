"""Verify the human-approved proposal at its immutable Git commit, without model calls."""

import json
import subprocess
from pathlib import Path

from acceptance_support.phase1_budget import sha

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/ADR/0011-dynamic-approval-20261008.json"
MANIFEST = "docs/acceptance/phase-1-dynamic-v1/manifest.json"
ADR = "docs/ADR/0011-independent-dynamic-acceptance.md"
DEFERRAL_COMMIT = "61ffdcc"
DEFERRAL_RECORD = "docs/acceptance/phase-1-provider-connection-v1/target-deferral-20261014.json"


def verify_current_attachment(path, original, current, deferred_adr=None):
    """Only the separately authorized target addendum may extend the approved ADR."""
    if path == ADR and deferred_adr is not None:
        assert deferred_adr.startswith(original + b"\n"), path
        assert current == deferred_adr, path
    else:
        assert current == original, path


def main():
    record = json.loads(RECORD.read_text())
    assert record["adr"] == "ADR-0011" and record["status"] == "Accepted"
    assert record["approved_sections"] == ["A", "B", "C", "D"]
    assert (
        record["user_response"] == "全部批准"
        and record["sample_labels_authorized"] is True
    )
    assert (
        record["provider_requests_authorized"]
        == record["provider_cost_micro_authorized"]
        == 0
    )
    assert record["dynamic_test_opening_authorized"] is False
    assert record["production_dynamic_opening_authorized"] is False
    commit = record["approved_proposal_commit"]

    def archived(path):
        return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)

    raw = archived(MANIFEST)
    assert sha(raw) == record["approved_proposal_manifest_sha256"]
    manifest = json.loads(raw)
    assert record["approved_files"] == manifest["files"]
    for path, digest in record["approved_files"].items():
        assert sha(archived(path)) == digest, path
        # Proposal/sample bytes stay immutable. Runtime sources may evolve in later tasks;
        # their approved baseline remains historical, never a future execution freeze.
        if path.startswith("docs/acceptance/phase-1-dynamic-v1/") or path.startswith(
            "docs/ADR/0011-"
        ):
            deferred = None
            if path == ADR:
                deferred = subprocess.check_output(
                    ["git", "show", f"{DEFERRAL_COMMIT}:{ADR}"], cwd=ROOT
                )
                deferral_raw = subprocess.check_output(
                    ["git", "show", f"{DEFERRAL_COMMIT}:{DEFERRAL_RECORD}"], cwd=ROOT
                )
                assert (ROOT / DEFERRAL_RECORD).read_bytes() == deferral_raw
                deferral = json.loads(deferral_raw)
                assert deferral["deferred_real_targets"] == [
                    "ollama", "anthropic", "gemini", "spark"
                ]
                assert deferral["additional_provider_requests_authorized"] == 0
                assert deferral["t040_t041_execution_authorized"] is False
            verify_current_attachment(path, archived(path), (ROOT / path).read_bytes(), deferred)
    assert (
        sha((ROOT / MANIFEST).read_bytes())
        == record["approved_proposal_manifest_sha256"]
    )
    print(
        "PASS: ADR-0011 A-D and labels approved; exact historical manifest verified; "
        "Provider requests/cost=0; dynamic opening=false"
    )


if __name__ == "__main__":
    main()
