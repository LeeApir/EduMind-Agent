"""Protocol anomalies and pointer-root defects stay distinct from semantic suggestions."""

# ruff: noqa: E402
import json
import socket
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
import check_p15_split_exploration_r02_results as c


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("No real network in result analysis")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


def sample(wrapper=True):
    payload = c.design.review_source(
        original_goal="合成目标",
        plan_constraints={},
        scene={"text": "数组支持下标访问"},
        upstream=[],
    )
    opinion = {
        "source_sha256": payload["source_sha256"],
        "scope_status": "complete",
        "uncertain_reason": None,
        "verdict": "revise",
        "issues": [
            {
                "area": "fact",
                "severity": "minor",
                "message": "合成建议，不是实际错误标签",
                "source_pointer": "/source/scene/text" if wrapper else "/scene/text",
                "evidence_quote": "数组",
            }
        ],
    }
    request = {
        "input": [{"role": "system", "content": "SYNTHETIC_REVIEW"}],
        "reasoning": {"effort": "none"},
    }
    response = {
        "instructions": "SYNTHETIC_REVIEW\n\nYou are a helpful coding assistant.",
        "reasoning": {"effort": "low"},
        "usage": {"output_tokens_details": {"reasoning_tokens": 89}},
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(opinion)}],
            },
        ],
    }
    return request, response, payload, opinion


def test_original_response_is_invalid_even_when_counterfactual_root_fix_works():
    req, res, source, _ = sample()
    original = deepcopy(res)
    r = c.review_observation(req, res, source)
    assert r["opinion_static_schema_valid"] is True
    assert r["original_pointer_quote_contract_valid"] is False
    assert r["source_pointer_wrapper_counterfactual_valid"] is True
    assert r["counterfactual_applied_to_live_evidence"] is False
    assert (
        r["reported_instruction_characters"] - r["expected_instruction_characters"]
        == 37
    )
    assert r["extra_instruction_suffix"] == "\n\nYou are a helpful coding assistant."
    assert (
        r["reported_reasoning_effort"] == "low" and r["reported_reasoning_tokens"] == 89
    )
    assert r["output_item_types"] == ["reasoning", "message"]
    assert res == original


def test_original_root_can_validate_without_silent_normalization():
    req, res, source, _ = sample(False)
    r = c.review_observation(req, res, source)
    assert r["original_pointer_quote_contract_valid"] is True
    assert r["source_pointer_wrapper_counterfactual_valid"] is False


@pytest.mark.parametrize("fault", ["wrong_quote", "wrong_sha", "bad_schema"])
def test_counterfactual_cannot_turn_other_errors_into_success(fault):
    req, res, source, opinion = sample()
    if fault == "wrong_quote":
        opinion["issues"][0]["evidence_quote"] = "NOT_IN_SOURCE"
    if fault == "wrong_sha":
        opinion["source_sha256"] = "f" * 64
    if fault == "bad_schema":
        opinion["issues"][0]["severity"] = "made_up"
    res["output"][-1]["content"][0]["text"] = json.dumps(opinion)
    r = c.review_observation(req, res, source)
    assert r["original_pointer_quote_contract_valid"] is False
    assert r["source_pointer_wrapper_counterfactual_valid"] is False


def test_instructions_replacement_is_not_misreported_as_known_suffix():
    req, res, source, _ = sample()
    res["instructions"] = "Entirely different instructions"
    r = c.review_observation(req, res, source)
    assert (
        r["instructions_identical"] is False and r["extra_instruction_suffix"] is None
    )


def test_changed_private_evidence_is_rejected_before_database_access(
    monkeypatch, tmp_path
):
    output = tmp_path / "private"
    output.mkdir()
    file = output / "evidence.json"
    file.write_text("changed")
    (tmp_path / "evidence-index.json").write_text(
        json.dumps({"sha256": {str(file): "0" * 64}})
    )
    monkeypatch.setattr(c, "BASE", tmp_path)
    monkeypatch.setattr(c, "OUTPUT", output)
    monkeypatch.setattr(c, "gate", lambda: ("a" * 64, None, None, None))
    with pytest.raises(ValueError, match="PRIVATE_EVIDENCE_CHANGED"):
        c.inspect()


def test_results_checker_never_reports_stopped_batch_as_pass(monkeypatch, tmp_path):
    r = {"durable_state": "stopped", "T038_completed": False}
    (tmp_path / "results.json").write_text(json.dumps(r))
    monkeypatch.setattr(c, "BASE", tmp_path)
    monkeypatch.setattr(c, "inspect", lambda: r)
    monkeypatch.setattr(sys, "argv", ["checker", "--check"])
    assert c.main() == 2
