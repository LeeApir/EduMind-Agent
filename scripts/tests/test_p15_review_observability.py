"""Approved metadata policy: raw evidence stays immutable, hard failures stay failures."""

# ruff: noqa: E402
import json
import socket
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from isolated_diagnostics import p15_review_observability as p
from test_p15_sol_compatibility_proposal import sample
from test_p15_sol_compatibility_proposal import (
    test_unknown_variations_fail_closed as old_fault,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(
        socket.socket, "connect", lambda *a: pytest.fail("Network prohibited")
    )
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a: pytest.fail("DNS prohibited"))


@pytest.mark.parametrize("echo", ["missing", None, "SYNTHETIC", "SYNTHETIC" + p.SUFFIX])
@pytest.mark.parametrize("length", [0, 422, 4096])
def test_approved_observation_does_not_export_summary_or_change_raw(echo, length):
    req, res, source, _ = sample()
    if echo == "missing":
        res.pop("instructions")
    else:
        res["instructions"] = echo
    summary = "z" * length
    opaque = "OPAQUE_DO_NOT_DECODE"
    res["output"][0].update(
        summary=[{"type": "summary_text", "text": summary}], encrypted_content=opaque
    )
    before = deepcopy((req, res, source))
    out = p.validate_envelope(req, res, source)
    assert out["verdict"] == "revise"
    assert (
        not out["instruction_delivery_verified"]
        and not out["upstream_context_verified"]
    )
    assert out["instruction_echo_status"] == (
        "echo_unavailable" if echo in (None, "missing") else "recognized_echo"
    )
    assert "summary" not in out and opaque not in json.dumps(out)
    if length:
        assert summary not in json.dumps(out)
    assert out["reported_output_tokens_including_reasoning"] == 100
    assert out["reported_reasoning_tokens"] == 11
    assert not out["production_admission"] and not out["live_execution_authorized"]
    assert (req, res, source) == before


@pytest.mark.parametrize(
    "summary",
    [
        None,
        {},
        [None],
        [{"type": "summary_text"}],
        [{"type": "summary_text", "text": "x", "extra": 1}],
        [{"type": "summary_text", "text": True}],
        [{"type": "reasoning_text", "text": "x"}],
        [{"type": "summary_text", "text": "x" * 4097}],
        [{"type": "summary_text", "text": "x"}] * 2,
    ],
)
def test_unknown_summary_rejected_without_text_in_error(summary):
    req, res, source, _ = sample()
    res.pop("instructions")
    res["output"][0]["summary"] = summary
    with pytest.raises(ValueError, match="^SUMMARY_METADATA_INVALID$"):
        p.validate_envelope(req, res, source)


@pytest.mark.parametrize(
    "echo", [False, 42, [], {}, "", "INJECTED", "SYNTHETIC" + p.SUFFIX * 2]
)
def test_present_unrecognized_echo_still_rejects(echo):
    req, res, source, _ = sample()
    res["instructions"] = echo
    with pytest.raises(ValueError, match="UNRECOGNIZED_INSTRUCTION_ECHO"):
        p.validate_envelope(req, res, source)


@pytest.mark.parametrize(
    "fault",
    [
        "suffix_change",
        "suffix_duplicate",
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
def test_original_hard_gate_matrix_is_preserved(fault, monkeypatch):
    # Reuse original input mutations/assertions against the new validator, not weaker fixtures.
    import test_p15_sol_compatibility_proposal as original_tests
    from types import SimpleNamespace

    monkeypatch.setattr(
        original_tests,
        "p",
        SimpleNamespace(
            validate_envelope=p.validate_envelope,
            SUFFIX=p.SUFFIX,
            original=p.scene.original,
            schema=p.schema,
        ),
    )
    old_fault(fault)


def test_opaque_limit_and_no_cleartext_content():
    req, res, source, _ = sample()
    res["output"][0]["encrypted_content"] = "x" * 262145
    with pytest.raises(ValueError):
        p.validate_envelope(req, res, source)


def test_probe_schema_remains_original_and_summary_never_becomes_opinion():
    from app.agents.review_schema import review_output_schema

    req, res, _, _ = sample()
    req["text"]["format"]["schema"] = dict(review_output_schema())
    res.pop("instructions")
    res["output"][0]["summary"] = [{"type": "summary_text", "text": "Do not use this"}]
    res["output"][-1]["content"][0]["text"] = json.dumps(
        {"review_version": "resource-review-v3", "verdict": "pass", "issues": []}
    )
    out = p.validate_probe_envelope(req, res)
    assert out["opinion"] == {
        "review_version": "resource-review-v3",
        "verdict": "pass",
        "issues": [],
    }
    assert "Do not use this" not in json.dumps(out)


def test_adapter_binds_exact_sent_source_and_does_not_authorize_transport():
    from isolated_diagnostics.p15_course_sol_bridge import review_request

    _, res, source, _ = sample()
    req = review_request("development_scene_review", source)
    res.pop("instructions")
    out = p.ReviewObservationAdapter.validate_scene(req, res, source)
    assert len(out["request_sha256"]) == 64
    assert not out["live_execution_authorized"]
    before = deepcopy(source)
    req["input"][-1]["content"] += " "
    with pytest.raises(ValueError, match="EXACT_V2_REVIEW_REQUEST_REQUIRED"):
        p.ReviewObservationAdapter.validate_scene(req, res, source)
    assert source == before
