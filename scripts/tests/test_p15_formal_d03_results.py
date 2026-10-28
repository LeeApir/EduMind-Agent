"""Bind the stopped diagnosis to actual raw bytes and SQL snapshots."""

# ruff: noqa: E402
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import check_p15_formal_d03_results as checker


def test_actual_stopped_evidence_does_not_imply_review_or_quality_pass():
    result = checker.check()
    assert result == json.loads((checker.cli.BASE / "results.json").read_bytes())
    assert result["primary_valid"] == [True, True, False]
    assert result["review_requests"] == 0
    assert not result["T038_completed"] and not result["local_recheck_pass"]


@pytest.mark.parametrize("target", ["request", "response", "pg", "ledger"])
def test_tampered_evidence_rejected(tmp_path, monkeypatch, target):
    original = checker.cli.OUTPUT
    for path in original.iterdir():
        if path.is_file() and not path.name.endswith(("-shm", "-wal")):
            shutil.copyfile(path, tmp_path / path.name)
    monkeypatch.setattr(checker.cli, "OUTPUT", tmp_path)
    if target in ("request", "response"):
        path = next(tmp_path.glob("*-" + target + ".json"))
        path.write_bytes(path.read_bytes() + b" ")
    elif target == "pg":
        path = tmp_path / "pg-export.json"
        value = json.loads(path.read_bytes())
        value["tables"]["free_course_scene_versions"] = []
        path.write_text(json.dumps(value))
    else:
        db = sqlite3.connect(tmp_path / "ledger.sqlite")
        db.execute("UPDATE batches SET state='complete'")
        db.commit()
        db.close()
    with pytest.raises((AssertionError, ValueError)):
        checker.check()
