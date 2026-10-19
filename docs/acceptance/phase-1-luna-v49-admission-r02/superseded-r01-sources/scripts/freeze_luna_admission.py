"""Seal the immutable zero-call Luna package; never grants request/label approval."""

# ruff: noqa: E402
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_admission_gate import BASE, env_metadata
from acceptance_support.qwen_review_budget import canonical, sha
from app.services.learning_policy import active_policy_digest


def build(root=ROOT):
    package = root / BASE
    names = {
        p.relative_to(root).as_posix()
        for parent in [root / "backend/app", root / "scripts"]
        for p in parent.rglob("*")
        if p.is_file() and p.suffix in {".py", ".json"} and "__pycache__" not in p.parts
    }
    names.update(
        p.relative_to(root).as_posix()
        for p in package.iterdir()
        if p.is_file()
        and p.name
        not in {
            "manifest.json",
            "run-approval.json",
            "labels-human.json",
            "screen-pass.json",
        }
    )
    names.update(
        [
            "backend/pyproject.toml",
            "backend/uv.lock",
            "data/knowledge/phase-1.1.0.json",
            "docs/acceptance/phase-1-review-binding-preparation-t070/manifest.json",
            "docs/ADR/0017-approval-20261019.json",
            "docs/ADR/0018-approval-20261019.json",
        ]
    )
    for name in names:
        p = root / name
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            raise ValueError("UNSAFE_SOURCE")
    budget = json.loads((package / "budget.json").read_text())
    assert (
        budget["requests_max"] == 12
        and budget["requests_authorized"] == 0
        and budget["cost_cap"] is None
    )
    return {
        "version": "luna-v49-admission-freeze-r01",
        "state": "FROZEN_PENDING_INDEPENDENT_LABELS_AND_EXACT_REQUEST_APPROVAL",
        "execution_root": str(root.resolve()),
        "repository_base_commit": "06429591dca83a1b57987e90b87ff3241a706258",
        "policy_digest": active_policy_digest(),
        "env_metadata": env_metadata(root / ".env"),
        "files": {n: sha((root / n).read_bytes()) for n in sorted(names)},
        "expires_at_epoch": int(
            datetime.fromisoformat("2026-10-21T23:59:59+08:00").timestamp()
        ),
        "requests_max": 12,
        "fees": "uncapped_by_explicit_user_instruction",
        "requests_authorized": 0,
        "independent_human_labels": "pending",
        "T040_pass": False,
    }


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    result = build()
    path = ROOT / BASE / "manifest.json"
    raw = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if a.write:
        if path.exists() and path.read_text() != raw:
            raise ValueError("REFUSE_RESEAL_FROZEN_PACKAGE")
        path.write_text(raw)
    elif path.read_text() != raw:
        raise ValueError("FREEZE_CHANGED")
    print(
        json.dumps(
            {
                "manifest_sha256": sha(canonical(result)),
                "files": len(result["files"]),
                "requests_max": 12,
                "cost_cap": None,
                "real_calls": 0,
                "requests_authorized": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
