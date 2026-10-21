"""Locate retired evidence without changing its frozen bytes or authorizing a run."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def evidence_path(path: Path, *, root: Path = ROOT) -> Path:
    path = Path(path)
    absolute = path if path.is_absolute() else root / path
    if absolute.exists():
        return absolute
    try:
        relative = absolute.relative_to(root).as_posix()
    except ValueError:
        return absolute
    index = root / "docs/maintenance/acceptance-archive-20261021.json"
    if index.exists():
        data = json.loads(index.read_bytes())
        for row in data["files"]:
            if row["original_path"] == relative:
                return root / row["archive_path"]
        for row in data.get("preexisting_local_relocations", []):
            if row["original_path"] == relative:
                return root / row["current_path"]
    if relative.startswith("local-materials/phase-1"):
        relocated = root / "local-materials/phase-1" / relative.removeprefix("local-materials/")
        if relocated.exists():
            return relocated
    return absolute
