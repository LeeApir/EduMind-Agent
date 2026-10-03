"""Archive integrity checks survive cleanup and reject missing or corrupted recovery data."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def archive_verifier(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts/verify_legacy_archives.py"
    spec = importlib.util.spec_from_file_location("legacy_archive_verifier", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    files = {
        "delivery.py": b"# committed repair\n",
        "experiment.py": b"# archived experiment\n",
        "evidence.json": b'{"passed": false}\n',
    }
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    tasks = {"tasks": [{"id": "MVP-0.3-T033", "status": "blocked"}]}
    inventory = {
        "delivery_full_files": ["delivery.py"],
        "delivery_commit": "delivery",
        "baseline_commit": "baseline",
        "original_hashes": hashes,
        "delivery_blob_hashes": {"delivery.py": hashes["delivery.py"]},
        "provider_requests": 0,
        "cumulative_requests": 2033,
    }
    responses = {
        ("show", "delivery:delivery.py"): files["delivery.py"],
        ("show", "baseline:task.json"): json.dumps(tasks).encode(),
    }
    for kind, name in (("code", "experiment.py"), ("evidence", "evidence.json")):
        inventory[kind + "_archive"] = {
            "branch": kind,
            "commit": kind + "-commit",
            "count": 1,
            "manifest": "manifest.json",
        }
        responses["rev-parse", kind] = (kind + "-commit\n").encode()
        responses["show", kind + "-commit:manifest.json"] = json.dumps(
            {"file_hashes": {name: hashes[name]}}
        ).encode()
        responses["show", kind + "-commit:" + name] = files[name]
    monkeypatch.setattr(module, "git", lambda *args: responses[args])
    directory = tmp_path / "docs/maintenance"
    directory.mkdir(parents=True)
    (directory / "legacy-worktree-inventory-20261003.json").write_text(json.dumps(inventory))
    (tmp_path / "task.json").write_text(json.dumps(tasks))
    return module, responses, files


def test_git_archives_pass_after_original_files_are_deleted(archive_verifier):
    module, _, files = archive_verifier
    assert all(not (module.ROOT / name).exists() for name in files)
    result = module.verify()
    assert result["source"] == "git_archives"
    assert result["original_files_verified"] == 3
    assert result["t033"] == "blocked"


def test_corrupted_archived_blob_is_rejected(archive_verifier):
    module, responses, _ = archive_verifier
    responses["show", "code-commit:experiment.py"] = b"changed"
    with pytest.raises(AssertionError):
        module.verify()


def test_wrong_archive_ref_is_rejected(archive_verifier):
    module, responses, _ = archive_verifier
    responses["rev-parse", "evidence"] = b"another-commit\n"
    with pytest.raises(AssertionError):
        module.verify()


def test_restored_tree_passes_then_rejects_corruption(archive_verifier, tmp_path):
    module, _, files = archive_verifier
    restored = tmp_path / "restored"
    restored.mkdir()
    for name, value in files.items():
        (restored / name).write_bytes(value)
    assert module.verify(restored_root=restored)["source"] == "restored_tree"
    (restored / "evidence.json").write_text('{"passed": true}')
    with pytest.raises(AssertionError, match="Changed restored file"):
        module.verify(restored_root=restored)


def test_missing_restored_file_never_falls_back_to_git(archive_verifier, tmp_path):
    module, _, _ = archive_verifier
    with pytest.raises(FileNotFoundError):
        module.verify(restored_root=tmp_path / "missing")


def test_phase_transition_reads_unchanged_archived_ledger(archive_verifier):
    module, _, _ = archive_verifier
    active = module.ROOT / "task.json"
    archive = module.ROOT / "docs/tasks/mvp-0.3.json"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(active.read_bytes())
    active.write_text(json.dumps({"active_phase": "Phase 1", "tasks": []}))
    assert module.verify()["t033"] == "blocked"

    content = json.loads(archive.read_text())
    content["tasks"][0]["status"] = "done"
    archive.write_text(json.dumps(content))
    with pytest.raises(AssertionError):
        module.verify()


def test_phase_transition_requires_archive(archive_verifier):
    module, _, _ = archive_verifier
    (module.ROOT / "task.json").write_text(
        json.dumps({"active_phase": "Phase 1", "tasks": []})
    )
    with pytest.raises(FileNotFoundError):
        module.verify()
