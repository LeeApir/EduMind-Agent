import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acceptance_support.archive_paths import evidence_path


def index(root, **extra):
    p = root / "docs/maintenance/acceptance-archive-20261021.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(dict(files=[dict(original_path="docs/acceptance/old/a.json", archive_path="local-materials/archive/a.json")], **extra)))


def test_archived_evidence_resolves_without_rewriting_source(tmp_path):
    index(tmp_path)
    assert evidence_path(Path("docs/acceptance/old/a.json"), root=tmp_path) == tmp_path / "local-materials/archive/a.json"


def test_present_original_never_silently_replaced(tmp_path):
    index(tmp_path)
    original = tmp_path / "docs/acceptance/old/a.json"
    original.parent.mkdir(parents=True)
    original.write_text("changed original; caller must reject hash mismatch")
    assert evidence_path(original, root=tmp_path) == original


def test_explicit_old_local_relocation_and_unregistered_path(tmp_path):
    index(tmp_path, preexisting_local_relocations=[dict(original_path="local-materials/old/a", current_path="local-materials/phase-1/old/a")])
    assert evidence_path(Path("local-materials/old/a"), root=tmp_path) == tmp_path / "local-materials/phase-1/old/a"
    assert evidence_path(Path("docs/acceptance/unlisted/a"), root=tmp_path) == tmp_path / "docs/acceptance/unlisted/a"


def test_outside_workspace_not_redirected(tmp_path):
    index(tmp_path)
    outside = tmp_path.parent / "outside/a"
    assert evidence_path(outside, root=tmp_path) == outside
