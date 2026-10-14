"""Offline tool-format and aggregate-budget guards; never execute a tool/model."""

import copy
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_phase1_tool_connection as runner  # noqa: E402
from acceptance_support.connection_diagnostics import ProbeFailure  # noqa: E402


def valid_response():
    return {
        "model": runner.MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "emit_probe", "arguments": '{"ok":true}'},
                        }
                    ],
                },
            }
        ],
    }


def test_frozen_tool_request_matches_approved_proposal_and_is_bounded():
    proposal = json.loads((runner.BASE / "tool-followup-proposal.json").read_text())
    body = runner.BODIES["tool"]
    assert runner.sha(runner.canonical(body)) == proposal["request_sha256"]
    assert body["model"] == runner.MODEL and body["max_completion_tokens"] == 64
    assert body["enable_thinking"] is False and body["stream"] is False
    runner.verify_tool_response(valid_response())


@pytest.mark.parametrize(
    "defect",
    ["wrong_model", "wrong_tool", "extra_call", "integer_boolean", "finish", "index", "refusal"],
)
def test_malformed_tool_response_cannot_pass(defect):
    raw = copy.deepcopy(valid_response())
    choice = raw["choices"][0]
    if defect == "wrong_model":
        raw["model"] = "another-model"
    elif defect == "wrong_tool":
        choice["message"]["tool_calls"][0]["function"]["name"] = "unapproved"
    elif defect == "extra_call":
        choice["message"]["tool_calls"] *= 2
    elif defect == "integer_boolean":
        choice["message"]["tool_calls"][0]["function"]["arguments"] = '{"ok":1}'
    elif defect == "finish":
        choice["finish_reason"] = "stop"
    elif defect == "index":
        choice["index"] = False
    else:
        choice["message"]["refusal"] = "refused"
    with pytest.raises(ProbeFailure):
        runner.verify_tool_response(raw)


def test_prior_budget_checks_all_three_ledgers_and_rejects_extra_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    parent = tmp_path / "local-materials/phase-1-t039"
    for folder, costs, halted in [
        ("r01", [10860], "TEMPORARILY_UNAVAILABLE"),
        ("diagnostic-r02", [10860], None),
        ("checks-r03", [13440, 11328], None),
    ]:
        directory = parent / folder
        directory.mkdir(parents=True)
        with sqlite3.connect(directory / "budget.sqlite") as db:
            db.execute("CREATE TABLE attempts(cost_micro INTEGER)")
            db.executemany("INSERT INTO attempts VALUES(?)", [(c,) for c in costs])
            db.execute("CREATE TABLE run(id INTEGER,halted TEXT)")
            db.execute("INSERT INTO run VALUES(1,?)", (halted,))
    assert runner.prior_usage() == (4, 46488)
    with sqlite3.connect(parent / "checks-r03/budget.sqlite") as db:
        db.execute("INSERT INTO attempts VALUES(0)")
    with pytest.raises(ValueError, match="PRIOR_BUDGET_CHANGED"):
        runner.prior_usage()


@pytest.mark.parametrize(
    "defect,expected_failed",
    [
        ("name", "function_name"),
        ("argument", "arguments_schema"),
        ("finish", "tool_finish_reason"),
        ("model", "model_identity"),
    ],
)
def test_safe_shape_diagnostics_identify_failure_without_content(defect, expected_failed):
    from acceptance_support.tool_probe_observation import tool_shape

    raw = valid_response()
    canary = "PRIVATE_CANARY_DO_NOT_PERSIST"
    raw["choices"][0]["message"]["content"] = canary
    if defect == "name":
        raw["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = canary
    elif defect == "argument":
        raw["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"ok":1}'
    elif defect == "finish":
        raw["choices"][0]["finish_reason"] = "stop"
    else:
        raw["model"] = canary
    flags = tool_shape(raw, models={runner.MODEL})
    assert [key for key, passed in flags.items() if not passed] == [expected_failed]
    assert canary not in json.dumps(flags)
    assert all(type(value) is bool for value in flags.values())


def test_safe_shape_diagnostics_accept_only_exact_arguments():
    from acceptance_support.tool_probe_observation import tool_shape

    assert all(tool_shape(valid_response(), models={runner.MODEL}).values())


@pytest.mark.parametrize(
    "arguments,wire_type,json_type,ok_type,ok_boolean",
    [
        ('{"ok":true}', "str", "dict", "bool", True),
        ('{"ok":1}', "str", "dict", "int", None),
        ('{"ok":"PRIVATE_CANARY"}', "str", "dict", "str", None),
        ({"ok": True}, "dict", "dict", "bool", True),
    ],
)
def test_tool_metadata_disambiguates_types_without_retaining_values(
    arguments, wire_type, json_type, ok_type, ok_boolean
):
    from acceptance_support.tool_probe_observation import tool_metadata

    raw = valid_response()
    raw["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = arguments
    meta = tool_metadata(raw)
    assert (
        meta["argument_wire_type"],
        meta["argument_json_type"],
        meta["ok_type"],
        meta["ok_boolean"],
    ) == (wire_type, json_type, ok_type, ok_boolean)
    assert "PRIVATE_CANARY" not in json.dumps(meta)


def test_new_diagnostic_prior_guard_and_round_bounds(tmp_path, monkeypatch):
    import run_phase1_tool_diagnostics as diagnostics

    monkeypatch.setattr(diagnostics, "ROOT", tmp_path)
    parent = tmp_path / "local-materials/phase-1-t039"
    records = [
        ("r01", [10860], "TEMPORARILY_UNAVAILABLE"),
        ("diagnostic-r02", [10860], None),
        ("checks-r03", [13440, 11328], None),
        ("tool-r04", [14724], "INVALID_OUTPUT"),
    ]
    for name, costs, halted in records:
        directory = parent / name
        directory.mkdir(parents=True)
        with sqlite3.connect(directory / "budget.sqlite") as db:
            db.execute("CREATE TABLE attempts(cost_micro INTEGER)")
            db.executemany("INSERT INTO attempts VALUES(?)", [(c,) for c in costs])
            db.execute("CREATE TABLE run(id INTEGER,halted TEXT)")
            db.execute("INSERT INTO run VALUES(1,?)", (halted,))
    assert diagnostics.prior_check(5) == (5, 61212)
    for name, state, cost, halted in [
        ("tool-diagnostic-r05", "failed", 14724, "INVALID_OUTPUT"),
        ("tool-diagnostic-r06", "complete", 14172, None),
    ]:
        directory = parent / name
        directory.mkdir(parents=True)
        with sqlite3.connect(directory / "budget.sqlite") as db:
            db.execute("CREATE TABLE attempts(state TEXT,cost_micro INTEGER)")
            db.execute("INSERT INTO attempts VALUES(?,?)", (state, cost))
            db.execute("CREATE TABLE run(id INTEGER,halted TEXT)")
            db.execute("INSERT INTO run VALUES(1,?)", (halted,))
    with pytest.raises(ValueError, match="PREVIOUS_ROUND_NOT_FAILED"):
        diagnostics.prior_check(7)
    with pytest.raises(ValueError, match="ROUND_NOT_APPROVED"):
        diagnostics.names(8)
