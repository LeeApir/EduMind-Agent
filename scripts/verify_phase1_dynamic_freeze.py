"""Read-only offline verification of ADR-0011 proposal and immutable historical provenance."""

import json
import subprocess
from pathlib import Path

from acceptance_support.phase1_budget import canonical, sha
from verify_phase1_dynamic_approval import main as verify_approval

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1-dynamic-v1"


def read(name):
    return json.loads((BASE / name).read_text())


def archived(commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def main():
    verify_approval()
    approval = json.loads((ROOT / "docs/ADR/0011-dynamic-approval-20261008.json").read_text())
    manifest = read("manifest.json")
    assert manifest["status"] == "PROPOSED_NO_CALLS"
    assert manifest["authorized_requests"] == manifest["authorized_cost_micro"] == 0
    for path, digest in manifest["files"].items():
        # This proposal records historical sources, not the later execution freeze.
        # verify_approval above separately checks current immutable samples and ADR addendum.
        assert sha(archived(approval["approved_proposal_commit"], path)) == digest, path
    history = read("history.json")
    raw = archived(history["archive_commit"], history["source_path"])
    assert sha(raw) == history["source_sha256"]
    original = json.loads(raw)
    for frozen, source in zip(history["cases"], original["cases"], strict=True):
        assert frozen["id"] == source["id"]
        assert frozen["original_content_sha256"] == source["content_sha256"]
        assert frozen["original_request_sha256"] == source["request_sha256"]
        messages = source["wire_body"]["messages"]
        payload = json.loads(
            next(m["content"] for m in messages if m["role"] == "user")
        )
        assert frozen["payload"] == payload
        assert frozen["payload_sha256"] == sha(canonical(payload))
    for report in history["reports"]:
        assert (
            sha(archived(history["archive_commit"], report["path"])) == report["sha256"]
        )
    cases = read("new-resource-cases.json")["cases"]
    assert len({c["id"] for c in cases}) == len(cases) == 50
    assert {
        k: sum(c["kind"] == k for c in cases)
        for k in ("severe_error", "correct_control", "long_review")
    } == {"severe_error": 20, "correct_control": 20, "long_review": 10}
    for case in cases:
        assert case["input_sha256"] == sha(canonical(case["input"]["content"]))
        assert (
            case["used_for_tuning"] is False and case["human_label_status"] == "pending"
        )
    units = read("generation-slots.json")
    assert len(units["slots"]) == units["planned_new_units"] == 100
    assert len({s["id"] for s in units["slots"]}) == 100
    for slot in units["slots"]:
        assert slot["input_sha256"] == sha(canonical(slot["input"]))
        assert slot["used_for_tuning"] is False
    old_quality = archived(history["archive_commit"], units["historical_failed_source"])
    assert sha(old_quality) == units["historical_failed_source_sha256"]
    failed = [s for s in json.loads(old_quality)["samples"] if not s.get("published")]
    assert len(failed) == len(units["historical_failed_slots"]) == 9
    for source, frozen in zip(failed, units["historical_failed_slots"], strict=True):
        assert (
            source["id"] == frozen["id"]
            and sha(canonical(source)) == frozen["sample_sha256"]
        )
    ledger = json.loads((ROOT / "docs/tasks/mvp-0.3.json").read_text())
    assert (
        next(t for t in ledger["tasks"] if t["id"] == "MVP-0.3-T033")["status"]
        == "blocked"
    )
    print(
        "PASS: proposal hashes, 8 historical cases, 9 failed slots, 50 new review cases, "
        "100 new generation slots; Provider calls=0; execution budget remains separate"
    )


if __name__ == "__main__":
    main()
