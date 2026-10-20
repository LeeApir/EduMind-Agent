"""Seal a zero-call final-candidate proposal; this is never execution authorization."""

# ruff: noqa: E402
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.qwen_review_budget import canonical, sha
from run_luna_process_calibration import verify, BASE as LOW
from prepare_last_review_candidate import BASE


def build(root=ROOT):
    previous, ph = verify(root)
    files = dict(previous["files"])
    paths = [
        "scripts/acceptance_support/luna_high_candidate.py",
        "scripts/prepare_last_review_candidate.py",
        "scripts/freeze_last_review_candidate.py",
        "scripts/tests/test_last_review_candidate.py",
        LOW + "/manifest.json",
        LOW + "/run-approval.json",
        LOW + "/assessments/cal-01.json",
        LOW + "/results/cal-01.json",
        LOW + "/results/cal-02.json",
        LOW + "/results/cal-02-claim-review.json",
        LOW + "/results/run-summary.json",
        LOW + "/results/halt.json",
    ]
    paths += [
        p.relative_to(root).as_posix()
        for p in (root / BASE).iterdir()
        if p.is_file() and p.name != "manifest.json"
    ]
    for name in paths:
        p = root / name
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            raise ValueError("UNSAFE_SOURCE")
        files[name] = sha(p.read_bytes())
    return dict(
        kind="ZERO_CALL_PROPOSAL_NOT_EXECUTION_AUTHORITY",
        state="PENDING_CANDIDATE_PLAN_REVIEW",
        previous_retired_candidate_manifest=ph,
        files=dict(sorted(files.items())),
        candidate_count_max=1,
        requests_proposed_max=12,
        requests_authorized=0,
        new_candidate_real_calls=0,
        env_metadata=previous["env_metadata"],
        execution_root=str(root.resolve()),
        failure_research_exit="STOP_BATCH_AND_DISCUSS_DELIVERY_SCOPE",
    )


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    m = build()
    raw = json.dumps(m, ensure_ascii=False, indent=2) + "\n"
    p = ROOT / BASE / "manifest.json"
    if args.write:
        if p.exists() and p.read_text() != raw:
            raise ValueError("REFUSE_RESEAL")
        p.write_text(raw)
    else:
        assert p.read_text() == raw
    print(
        json.dumps(
            dict(
                proposal_sha256=sha(canonical(m)),
                files=len(m["files"]),
                live_authorization=0,
            )
        )
    )


if __name__ == "__main__":
    main()
