"""Check the selected offline-review files, not a live-execution closure."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def main() -> None:
    manifest = json.loads((HERE / "audit-manifest.json").read_text())
    assert manifest["version"] == "t102-isolated-repair-review-v2"
    assert manifest["real_provider_calls"] == 0
    for name, expected in manifest["files"].items():
        path = ROOT / name
        assert not path.is_symlink() and path.is_file(), name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    print(f"{len(manifest['files'])} selected offline review files match; Provider 0")


if __name__ == "__main__":
    main()
