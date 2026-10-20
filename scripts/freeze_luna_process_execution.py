"""Freeze new four-request authority, not a continuation of either previous Luna run."""

# ruff: noqa: E402
import argparse
from datetime import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.qwen_review_budget import sha, canonical
from run_luna_schema_validation import verify as verify_old
from run_luna_process_calibration import BASE, MATERIALS, SCHEMA_PARENT, SLOTS


def build(root=ROOT):
    parent, ph = verify_old(root)
    files = dict(parent["files"])
    names = [
        "scripts/run_luna_process_calibration.py",
        "scripts/prepare_luna_process_execution.py",
        "scripts/freeze_luna_process_execution.py",
        "scripts/tests/test_luna_process_execution.py",
        "scripts/prepare_luna_process_calibration.py",
        "scripts/tests/test_luna_process_calibration.py",
        SCHEMA_PARENT + "/manifest.json",
        SCHEMA_PARENT + "/run-approval.json",
        SCHEMA_PARENT + "/results/screen-complete-01.json",
        SCHEMA_PARENT + "/results/run-summary.json",
    ]
    names += [
        p.relative_to(root).as_posix()
        for p in (root / MATERIALS).iterdir()
        if p.is_file()
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
    requests = json.loads((root / BASE / "requests.json").read_bytes())
    plan = json.loads((root / BASE / "plan.json").read_bytes())
    return dict(
        version="luna-process-calibration-execution-r01",
        state="FROZEN_PENDING_NEW_FOUR_REQUEST_APPROVAL",
        execution_root=str(root.resolve()),
        files=dict(sorted(files.items())),
        schema_parent_manifest_sha256=ph,
        env_metadata=parent["env_metadata"],
        policy_digest=parent["policy_digest"],
        slots=list(SLOTS),
        requests_max=4,
        requests_authorized_at_freeze=0,
        request_sha256={slot: requests[slot]["wire_sha256"] for slot in SLOTS},
        expires_at_epoch=int(datetime.fromisoformat(plan["expires_at"]).timestamp()),
        cost_cap=None,
        parent_remaining_slots_transfer=False,
        labels_confirmation="separate labels-human.json binds unchanged material files; no outputs presigned",
    )


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    manifest = build()
    raw = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    path = ROOT / BASE / "manifest.json"
    if args.write:
        if path.exists() and path.read_text() != raw:
            raise ValueError("REFUSE_RESEAL")
        path.write_text(raw)
    else:
        assert path.read_text() == raw, "FREEZE_CHANGED"
    print(
        json.dumps(
            dict(
                manifest_sha256=sha(canonical(manifest)),
                files=len(manifest["files"]),
                requests_max=4,
                live_authorization=0,
            )
        )
    )


if __name__ == "__main__":
    main()
