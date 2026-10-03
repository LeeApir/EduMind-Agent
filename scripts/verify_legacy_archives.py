"""Verify local Git archives or a restored tree without executing experiment code."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, check=True
    ).stdout


def sha(value):
    return hashlib.sha256(value).hexdigest()


def verify(*, restored_root: Path | None = None, check_worktree: bool = False):
    if restored_root is not None and check_worktree:
        raise ValueError("Choose a restored tree or the original worktree, not both")
    inventory = json.loads(
        (ROOT / "docs/maintenance/legacy-worktree-inventory-20261003.json").read_text()
    )
    covered = set()
    for name in inventory["delivery_full_files"]:
        assert (
            sha(git("show", inventory["delivery_commit"] + ":" + name))
            == inventory["original_hashes"][name]
        ), "Changed archived delivery file: " + name
        covered.add(name)
    for key in ("code_archive", "evidence_archive"):
        group = inventory[key]
        assert git("rev-parse", group["branch"]).decode().strip() == group["commit"]
        manifest = json.loads(git("show", group["commit"] + ":" + group["manifest"]))
        assert len(manifest["file_hashes"]) == group["count"]
        for name, digest in manifest["file_hashes"].items():
            assert sha(git("show", group["commit"] + ":" + name)) == digest
            assert digest == inventory["original_hashes"][name]
            covered.add(name)
    assert covered == set(inventory["original_hashes"])
    files_root = ROOT if check_worktree else restored_root
    if files_root is not None:
        for name, digest in inventory["original_hashes"].items():
            assert sha((files_root / name).read_bytes()) == digest, "Changed restored file: " + name
    for name, digest in inventory["delivery_blob_hashes"].items():
        assert sha(git("show", inventory["delivery_commit"] + ":" + name)) == digest
    current = json.loads((ROOT / "task.json").read_text())
    original = json.loads(git("show", inventory["baseline_commit"] + ":task.json"))
    assert (
        current == original
    )  # Sorting must not reopen/regrade/complete T033 or change any task.
    assert (
        next(t for t in current["tasks"] if t["id"] == "MVP-0.3-T033")["status"]
        == "blocked"
    )
    assert (
        inventory["provider_requests"] == 0 and inventory["cumulative_requests"] == 2033
    )
    return {
        "passed": True,
        "source": "git_archives" if files_root is None else "restored_tree",
        "original_files_verified": len(covered),
        "experiment_files": inventory["code_archive"]["count"],
        "evidence_files": inventory["evidence_archive"]["count"],
        "provider_requests": 0,
        "t033": "blocked",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--restored-root", type=Path, help="Also check an extracted historical tree")
    source.add_argument("--check-worktree", action="store_true", help="Check original uncleaned paths")
    args = parser.parse_args()
    print(json.dumps(verify(restored_root=args.restored_root, check_worktree=args.check_worktree)))


if __name__ == "__main__":
    main()
