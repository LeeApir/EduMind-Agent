"""Offline human-signature preflight; never auto-approve or connect to a database."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__" and Path(sys.prefix) != ROOT / "backend/.venv":
    python = ROOT / "backend/.venv/bin/python"
    if not python.exists():
        raise SystemExit(
            "Backend locked dependencies are required; initialize backend/.venv first"
        )
    os.execv(str(python), [str(python), __file__, *sys.argv[1:]])
sys.path.insert(0, str(ROOT / "backend"))
from app.services.catalog_package import load_package, read_json, validate_approval  # noqa: E402


def verify(
    directory: Path, trusted_digest: str, approval_path: Path | None = None
) -> dict:
    package = load_package(directory)
    # The allowlist value comes explicitly from the human/deployer, not from package input.
    if package.digest != trusted_digest:
        raise ValueError("Content is not authorized by the trusted digest")
    approval_path = approval_path or directory / "approval.json"
    if not approval_path.exists():
        return {
            "state": "PENDING_HUMAN_REVIEW",
            "manifest_digest": package.digest,
            "publishable": False,
            "provider_requests": 0,
        }
    approval = validate_approval(
        package, read_json(approval_path), trusted_digest=trusted_digest
    )
    for key in ("reviewer", "basis"):
        if "TEST_ONLY" in str(approval[key]).upper():
            raise ValueError("Synthetic approval is not a human release")
    return {
        "state": "HUMAN_APPROVED",
        "manifest_digest": package.digest,
        "reviewer": approval["reviewer"],
        "reviewed_at": approval["reviewed_at"],
        "publishable": True,
        "provider_requests": 0,
    }


def trusted_release(directory: Path, allowlist: Path) -> tuple[str, Path]:
    """Local publisher configuration, never a student-provided authorization."""
    package = load_package(directory)
    entries = read_json(allowlist)["releases"]
    matches = [
        entry
        for entry in entries
        if entry["package_id"] == package.manifest["package_id"]
        and entry["version"] == package.manifest["version"]
    ]
    if len(matches) != 1:
        raise ValueError("Release must have exactly one trusted allowlist entry")
    entry = matches[0]
    return entry["manifest_digest"], ROOT / entry["approval_path"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory", type=Path, default=ROOT / "data/course_catalog/linear-v1"
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=ROOT / "data/course_catalog/release-allowlist.json",
    )
    args = parser.parse_args()
    digest, approval_path = trusted_release(args.directory, args.allowlist)
    result = verify(args.directory, digest, approval_path)
    print(json.dumps(result, ensure_ascii=False))
    if not result["publishable"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
