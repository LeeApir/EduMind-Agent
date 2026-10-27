"""Schema-valid but unplanned forms cannot be reported as successful generation."""

# ruff: noqa: E402
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend/tests"))
sys.path.insert(0, str(ROOT / "scripts"))
from test_free_scene_generation import inputs, response
import check_p15_split_exploration_results as c


def test_extra_visualization_is_exact_failure_and_counterfactual_does_not_mutate():
    data = inputs(n=1, forms=["text", "code", "exercise"])
    raw = response()
    value = {
        "engineering_pass": False,
        "operation_state": "failed",
        "tables": {
            "free_course_attempts": [
                {
                    "id": "one",
                    "sent_at": "2026-10-27",
                    "purpose": "primary",
                    "input_snapshot": data,
                    "request_json": {"request": {"stage": "free_scene_generation"}},
                }
            ],
            "free_course_settlements": [
                {"attempt_id": "one", "outcome_json": {"value": raw}}
            ],
        },
    }
    before = json.dumps(value, sort_keys=True)
    result = c.inspect_slot(value)
    assert result["engineering_pass"] is False
    finding = result["scene_attempts"][0]
    assert finding["json_schema_errors"] == 0
    assert finding["extra_forms"] == ["visualization"]
    assert finding["counterfactual_remove_extra_blocks_admitted"] is True
    assert finding["counterfactual_applied_to_course"] is False
    assert json.dumps(value, sort_keys=True) == before


@pytest.mark.parametrize(
    "engineering,state,expected",
    [(False, "stopped", 2), (True, "stopped", 2), (True, "running", 0)],
)
def test_terminal_state_overrides_wrapper_text(
    monkeypatch, tmp_path, engineering, state, expected
):
    result = {
        "durable_state": state,
        "slots": [{"engineering_pass": engineering}],
        "legacy_cli_human_review_required_is_not_success_evidence": True,
    }
    (tmp_path / "results.json").write_text(json.dumps(result))
    monkeypatch.setattr(c, "BASE", tmp_path)
    monkeypatch.setattr(c, "inspect", lambda: result)
    monkeypatch.setattr(sys, "argv", ["checker", "--check"])
    assert c.main() == expected


def test_changed_result_report_refused(monkeypatch, tmp_path):
    (tmp_path / "results.json").write_text("{}")
    monkeypatch.setattr(c, "BASE", tmp_path)
    monkeypatch.setattr(c, "inspect", lambda: {"durable_state": "stopped"})
    monkeypatch.setattr(sys, "argv", ["checker", "--check"])
    with pytest.raises(ValueError, match="RESULTS_DIFFER"):
        c.main()
