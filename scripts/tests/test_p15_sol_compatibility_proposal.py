"""Narrow known differences never authorize new calls or relax source/semantic gates."""

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
from isolated_diagnostics import p15_sol_compatibility_proposal as p


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Offline proposal cannot use network")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


def sample():
    payload = p.original.review_source(
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
                "source_pointer": "/scene/text",
                "evidence_quote": "数组",
                "message": "合成审核示例",
            }
        ],
    }
    req = {
        "model": "gpt-6.1-sol",
        "reasoning": {"effort": "low"},
        "store": False,
        "stream": False,
        "input": [{"role": "system", "content": "SYNTHETIC"}],
        "text": {"format": {"strict": True, "schema": p.schema()}},
    }
    response = {
        "object": "response",
        "status": "completed",
        "model": "gpt-6.1-sol",
        "store": False,
        "tools": [],
        "reasoning": {"effort": "low"},
        "instructions": "SYNTHETIC" + p.SUFFIX,
        "usage": {
            "input_tokens": 20,
            "output_tokens": 100,
            "total_tokens": 120,
            "output_tokens_details": {"reasoning_tokens": 11},
        },
        "output": [
            {
                "type": "reasoning",
                "id": "synthetic",
                "summary": [],
                "content": [],
                "encrypted_content": None,
            },
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(opinion)}],
            },
        ],
    }
    return req, response, payload, opinion


def test_exact_known_suffix_and_low_metadata_are_only_proposed_observations():
    req, res, source, _ = sample()
    before = deepcopy((req, res, source))
    out = p.validate_envelope(req, res, source)
    assert out["verdict"] == "revise" and out["observed_known_suffix"] is True
    assert out["reported_output_tokens_including_reasoning"] == 100
    assert out["reported_reasoning_tokens"] == 11
    assert (
        not out["upstream_context_verified"]
        and not out["production_admission"]
        and not out["live_execution_authorized"]
    )
    assert (req, res, source) == before


def test_no_suffix_also_accepted_with_zero_reasoning_and_no_reasoning_item():
    req, res, source, _ = sample()
    res["instructions"] = "SYNTHETIC"
    res["usage"]["output_tokens_details"]["reasoning_tokens"] = 0
    res["output"] = res["output"][1:]
    assert p.validate_envelope(req, res, source)["observed_known_suffix"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "suffix_change",
        "suffix_duplicate",
        "missing_instructions",
        "prefix_injection",
        "high_reasoning",
        "request_none",
        "model",
        "store",
        "status",
        "tools",
        "usage_missing",
        "usage_arithmetic",
        "reasoning_over_output",
        "reasoning_boolean",
        "reasoning_text",
        "reasoning_encrypted",
        "reasoning_summary",
        "reasoning_duplicate",
        "function_call",
        "duplicate_message",
        "refusal_content",
        "schema_strict_false",
        "schema_changed",
        "bad_pointer",
        "bad_quote",
        "bad_sha",
        "bad_escape",
        "pass_with_issues",
        "insufficient_pass",
        "missing_reasoning_item",
        "request_stream",
    ],
)
def test_unknown_variations_fail_closed(fault):
    req, res, source, opinion = sample()
    if fault == "suffix_change":
        res["instructions"] += " "
    if fault == "suffix_duplicate":
        res["instructions"] += p.SUFFIX
    if fault == "missing_instructions":
        res.pop("instructions")
    if fault == "prefix_injection":
        res["instructions"] = "INJECTED" + res["instructions"]
    if fault == "high_reasoning":
        res["reasoning"]["effort"] = "high"
    if fault == "request_none":
        req["reasoning"]["effort"] = "none"
    if fault == "model":
        res["model"] = "other"
    if fault == "store":
        res["store"] = True
    if fault == "status":
        res["status"] = "incomplete"
    if fault == "tools":
        res["tools"] = [{"type": "web_search"}]
    if fault == "usage_missing":
        res.pop("usage")
    if fault == "usage_arithmetic":
        res["usage"]["total_tokens"] = 999
    if fault == "reasoning_over_output":
        res["usage"]["output_tokens_details"]["reasoning_tokens"] = 101
    if fault == "reasoning_boolean":
        res["usage"]["output_tokens_details"]["reasoning_tokens"] = True
    if fault == "reasoning_text":
        res["output"][0]["content"] = [
            {"type": "reasoning_text", "text": "do not reveal"}
        ]
    if fault == "reasoning_encrypted":
        res["output"][0]["encrypted_content"] = {"invalid": "type"}
    if fault == "reasoning_summary":
        res["output"][0]["summary"] = [{"text": "not requested"}]
    if fault == "reasoning_duplicate":
        res["output"].insert(0, deepcopy(res["output"][0]))
    if fault == "function_call":
        res["output"][0] = {"type": "function_call"}
    if fault == "duplicate_message":
        res["output"].append(deepcopy(res["output"][-1]))
    if fault == "refusal_content":
        res["output"][-1]["content"][0]["type"] = "refusal"
    if fault == "schema_strict_false":
        req["text"]["format"]["strict"] = False
    if fault == "schema_changed":
        req["text"]["format"]["schema"]["extra"] = True
    if fault == "bad_pointer":
        opinion["issues"][0]["source_pointer"] = "/source/scene/text"
    if fault == "bad_quote":
        opinion["issues"][0]["evidence_quote"] = "not present"
    if fault == "bad_sha":
        opinion["source_sha256"] = "f" * 64
    if fault == "bad_escape":
        opinion["issues"][0]["source_pointer"] = "/scene/~2text"
    if fault == "pass_with_issues":
        opinion["verdict"] = "pass"
    if fault == "insufficient_pass":
        opinion.update(
            scope_status="insufficient_evidence",
            verdict="pass",
            uncertain_reason="missing",
            issues=[],
        )
    if fault == "missing_reasoning_item":
        res["output"] = res["output"][1:]
    if fault == "request_stream":
        req["stream"] = True
    res["output"][-1].setdefault("content", [{}])[0]["text"] = json.dumps(opinion)
    with pytest.raises((ValueError, TypeError)):
        p.validate_envelope(req, res, source)


def test_opaque_encrypted_field_is_not_returned_forwarded_or_decoded():
    req, res, source, _ = sample()
    opaque = "SYNTHETIC_OPAQUE_ENVELOPE_NOT_ACTUAL_REASONING"
    res["output"][0]["encrypted_content"] = opaque
    out = p.validate_envelope(req, res, source)
    assert opaque not in json.dumps(out)
    assert out["production_admission"] is False
