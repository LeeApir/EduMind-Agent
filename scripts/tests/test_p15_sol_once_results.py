"""Evidence verifier cannot accept altered private originals or report full admission."""

# ruff: noqa: E402
import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
import check_p15_sol_compatibility_once_results as p


def test_private_evidence_mutation_refused_before_package_processing(
    tmp_path, monkeypatch
):
    out = tmp_path / "private"
    out.mkdir()
    file = out / "request.json"
    file.write_text("changed")
    (tmp_path / "evidence-index.json").write_text(
        json.dumps({"sha256": {str(file): "0" * 64}})
    )
    monkeypatch.setattr(p, "BASE", tmp_path)
    with pytest.raises(ValueError, match="PRIVATE_EVIDENCE_CHANGED"):
        p.inspect(out)


def test_readonly_verifier_has_no_execute_option(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["checker", "--execute"])
    with pytest.raises(SystemExit) as exc:
        p.main()
    assert exc.value.code == 2


def test_report_tamper_is_not_synthetic_pass(tmp_path, monkeypatch):
    (tmp_path / "results.json").write_text(json.dumps({"course_admission": True}))
    monkeypatch.setattr(p, "BASE", tmp_path)
    monkeypatch.setattr(p, "inspect", lambda: {"course_admission": False})
    monkeypatch.setattr(sys, "argv", ["checker", "--check"])
    with pytest.raises(ValueError, match="RESULT_REPORT_CHANGED"):
        p.main()
