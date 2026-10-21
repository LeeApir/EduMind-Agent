"""Check/restore retired evidence locally from the exact Git snapshot; never run it."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/maintenance/acceptance-archive-20261021.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "restore"])
    parser.add_argument("--path", help="Optional exact original repo-relative evidence path.")
    args = parser.parse_args()
    data = json.loads(INDEX.read_bytes())
    rows = [r for r in data["files"] if args.path is None or r["original_path"] == args.path]
    if not rows:
        parser.error("Path is not registered in the archive index")
    for row in rows:
        path = (ROOT / row["archive_path"]).resolve()
        if not path.is_relative_to((ROOT / data["git_ignored_archive_root"]).resolve()):
            raise ValueError("Unsafe archive path")
        if not path.exists() and args.action == "restore":
            body = subprocess.check_output(["git", "show", data["source_commit"] + ":" + row["original_path"]], cwd=ROOT)
            if hashlib.sha256(body).hexdigest() != row["sha256"]:
                raise ValueError("Git snapshot digest mismatch")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as f:
                f.write(body)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Missing/changed evidence: " + row["original_path"])
    print(json.dumps(dict(checked=len(rows),source_commit=data["source_commit"],action=args.action,provider_calls=0)))


if __name__ == "__main__":
    main()
