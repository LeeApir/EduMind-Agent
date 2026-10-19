"""Freeze a new one-request schema validation package; never resumes the parent."""

# ruff: noqa: E402
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_admission_gate import verify_freeze as parent_verify
from acceptance_support.qwen_review_budget import sha, canonical
from prepare_luna_schema_validation import BASE, PARENT, SLOT


def build(root=ROOT):
    parent, ph = parent_verify(root)
    files = dict(parent["files"])
    names = [
        PARENT + "/manifest.json",
        PARENT + "/run-approval.json",
        PARENT + "/labels-human.json",
        PARENT + "/results/screen-complete-01.json",
        PARENT + "/results/run-summary.json",
        "scripts/acceptance_support/luna_schema_projection.py",
        "scripts/prepare_luna_schema_validation.py",
        "scripts/run_luna_schema_validation.py",
        "scripts/freeze_luna_schema_validation.py",
        "scripts/tests/test_luna_schema_validation.py",
    ]
    names.extend(
        p.relative_to(root).as_posix()
        for p in (root / BASE).iterdir()
        if p.is_file() and p.name not in {"manifest.json", "run-approval.json"}
    )
    for name in names:
        p = root / name
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            raise ValueError("UNSAFE_SOURCE")
        files[name] = sha(p.read_bytes())
    request = json.loads((root / BASE / "request.json").read_bytes())
    case = json.loads((root / PARENT / "cases.json").read_bytes())[SLOT]
    return {
        "version": "luna-schema-single-validation-r01",
        "state": "FROZEN_PENDING_NEW_ONE_REQUEST_APPROVAL",
        "execution_root": str(root.resolve()),
        "parent_manifest_sha256": ph,
        "env_metadata": parent["env_metadata"],
        "expires_at_epoch": parent["expires_at_epoch"],
        "case_sha256": sha(canonical(case)),
        "request_sha256": request["wire_sha256"],
        "policy_digest": parent["policy_digest"],
        "files": dict(sorted(files.items())),
        "requests_max": 1,
        "requests_authorized": 0,
        "cost_cap": None,
        "stop_after_call_regardless_of_outcome": True,
        "parent_remaining_slots_transfer": False,
    }


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
    elif path.read_text() != raw:
        raise ValueError("FREEZE_CHANGED")
    print(
        json.dumps(
            {
                "manifest_sha256": sha(canonical(m)),
                "files": len(m["files"]),
                "requests_max": 1,
                "requests_authorized": 0,
                "real_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
