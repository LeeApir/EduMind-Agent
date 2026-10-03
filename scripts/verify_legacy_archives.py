"""Read-only byte checks for local archives; never import or run experiment code."""

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


def main():
    inventory = json.loads(
        (ROOT / "docs/maintenance/legacy-worktree-inventory-20261003.json").read_text()
    )
    covered = set(inventory["delivery_full_files"])
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
    for name, digest in inventory["original_hashes"].items():
        assert sha((ROOT / name).read_bytes()) == digest, "Changed original: " + name
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
    assert git("branch", "--show-current").decode().strip() == "codex/mvp-0.3"
    print(
        json.dumps(
            {
                "passed": True,
                "original_files_verified": len(covered),
                "experiment_files": inventory["code_archive"]["count"],
                "evidence_files": inventory["evidence_archive"]["count"],
                "provider_requests": 0,
                "t033": "blocked",
            }
        )
    )


if __name__ == "__main__":
    main()
