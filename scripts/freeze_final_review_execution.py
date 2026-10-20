"""Seal sole final high candidate with 12-slot authority and terminal R&D exit policy."""

# ruff: noqa: E402
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.qwen_review_budget import canonical, sha
from acceptance_support.luna_admission_gate import env_metadata
from run_final_review_candidate import BASE, MATERIALS, SLOTS


def build(root=ROOT):
    previous = json.loads((root / MATERIALS / "manifest.json").read_bytes())
    assert previous["execution_root"] == str(root.resolve())
    assert env_metadata(root / ".env") == previous["env_metadata"]
    files = dict(previous["files"])
    for name, expected in files.items():
        assert sha((root / name).read_bytes()) == expected, name
    names = [
        MATERIALS + "/manifest.json",
        "scripts/run_final_review_candidate.py",
        "scripts/run_final_review_attempt.py",
        "scripts/prepare_final_review_execution.py",
        "scripts/freeze_final_review_execution.py",
        "scripts/tests/test_final_review_execution.py",
    ]
    names += [
        p.relative_to(root).as_posix()
        for p in (root / BASE).iterdir()
        if p.is_file() and p.name not in {"manifest.json", "run-approval.json"}
    ]
    for name in names:
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("UNSAFE_SOURCE")
        files[name] = sha(path.read_bytes())
    plan = json.loads((root / BASE / "plan.json").read_bytes())
    requests = json.loads((root / BASE / "requests.json").read_bytes())
    return dict(
        kind="FINAL_SINGLE_CANDIDATE_EXECUTION",
        state="FROZEN_PENDING_NEW_EXACT_12_REQUEST_APPROVAL",
        execution_root=str(root.resolve()),
        proposal_sha256=sha(canonical(previous)),
        candidate_id="luna-high-v49-final-01",
        candidate_count_max=1,
        requests_max=12,
        requests_authorized_at_freeze=0,
        slots=list(SLOTS),
        request_sha256={s: requests[s]["wire_sha256"] for s in SLOTS},
        files=dict(sorted(files.items())),
        env_metadata=previous["env_metadata"],
        expires_at_epoch=int(datetime.fromisoformat(plan["expires_at"]).timestamp()),
        cost_cap=None,
        failure_research_exit="STOPPED_SCOPE_DISCUSSION_REQUIRED",
        candidate_attempts_after_failure=0,
    )


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    m = build()
    raw = json.dumps(m, ensure_ascii=False, indent=2) + "\n"
    path = ROOT / BASE / "manifest.json"
    if a.write:
        if path.exists() and path.read_text() != raw:
            raise ValueError("REFUSE_RESEAL")
        path.write_text(raw)
    else:
        assert path.read_text() == raw
    print(
        json.dumps(
            dict(
                manifest_sha256=sha(canonical(m)),
                files=len(m["files"]),
                candidate_count_max=1,
                requests_max=12,
                live_authorization=0,
            )
        )
    )


if __name__ == "__main__":
    main()
