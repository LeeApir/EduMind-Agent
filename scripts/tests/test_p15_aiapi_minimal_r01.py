"""Offline stop-rule regressions; no credentials or network."""

import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "run_p15_aiapi_minimal_r01.py"
spec = importlib.util.spec_from_file_location("aiapi_r01", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def reply():
    body = m.read(m.BASE / "S1.json")
    value = {
        "role_marker": "EDUMIND_TUTOR_R01",
        "explanation": "栈后进先出。",
        "learner_level": None,
    }
    return body, {
        "status": "completed",
        "error": None,
        "model": body["model"],
        "store": False,
        "instructions": body["instructions"],
        "max_output_tokens": 128,
        "usage": {"input_tokens": 30, "output_tokens": 20, "total_tokens": 50},
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": m.json.dumps(value)}],
            }
        ],
    }


def test_valid_observation():
    body, r = reply()
    assert m.observe(body, r, 0)["all_passed"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_output_tokens", None),
        ("instructions", "You are a helpful coding assistant."),
        ("model", "other"),
        ("status", "incomplete"),
        ("usage", {"input_tokens": 30, "output_tokens": 20, "total_tokens": 99}),
    ],
)
def test_stop_on_unproven_or_invalid(field, value):
    body, r = reply()
    r[field] = value
    assert not m.observe(body, r, 0)["all_passed"]


def test_invalid_schema_stops():
    body, r = reply()
    r["output"][0]["content"][0]["text"] = '{"role_marker":"WRONG"}'
    assert not m.observe(body, r, 0)["all_passed"]


def test_reported_over_cap_stops():
    body, r = reply()
    r["usage"] = {"input_tokens": 30, "output_tokens": 129, "total_tokens": 159}
    assert not m.observe(body, r, 0)["all_passed"]


def test_scrubs_account_fields():
    assert m.scrub({"encrypted_content": "private", "instructions": "text"}) == {
        "encrypted_content": "<omitted>",
        "instructions": "text",
    }
