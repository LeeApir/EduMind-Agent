"""T040 preparation tests use historical fixtures only; no key or real Provider."""

import asyncio
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acceptance_support.phase1_budget import canonical, sha  # noqa: E402
from prepare_t040_diagnostics import (  # noqa: E402
    HISTORY,
    MAX_OUTPUT,
    OVERHEAD,
    capture_case,
    prepare,
    reservation,
)
from verify_phase1_dynamic_approval import ADR, verify_current_attachment  # noqa: E402


def test_independent_groups_count_duplicates_and_bind_real_production_prompt(monkeypatch):
    monkeypatch.delenv("EDUMIND_PROVIDER_API_KEY", raising=False)
    bodies, plan = asyncio.run(prepare())
    assert len(bodies) == plan["requested_total_calls"] == 13
    assert [g["requests"] for g in plan["groups"]] == [5, 5, 1, 2]
    assert plan["provider_requests_authorized"] == plan["real_requests_sent"] == 0
    assert not plan["formal_quality_authorized"] and not plan["dsl_quality_authorized"]
    assert not plan["t041_authorized"]
    for group in plan["groups"]:
        assert group["state"] == "PENDING_BUDGET_APPROVAL"
        assert group["cost_cap_micro_cny"] >= group["computed_reservation_micro_cny"]
        assert group["computed_reservation_micro_cny"] == sum(
            reservation(bodies[row["slot"]]) for row in group["slots"]
        )
        for row in group["slots"]:
            body = bodies[row["slot"]]
            assert body["model"] == "deepseek-flash"
            assert body["reasoning"] == {"effort": "none"}
            assert body["max_output_tokens"] == MAX_OUTPUT
            assert body["text"]["format"]["type"] == "json_schema"
            assert row["request_sha256"] == sha(canonical(body))
            assert row["input_token_upper_bound"] == len(canonical(body)) + OVERHEAD
            # Ground-truth answers are evaluation metadata, never prompt additions.
            assert set(json.loads(body["input"][1]["content"])) == {
                "resource_type", "content", "reference_context"
            }
    for index in range(1, 6):
        assert bodies[f"error_detection:{index:02}"] == bodies[f"classification:{index:02}"]


def test_mutated_historical_payload_stops_before_capture():
    case = copy.deepcopy(json.loads(HISTORY.read_text())["cases"][0])
    case["payload"]["content"] = {"markdown": "changed"}
    with pytest.raises(AssertionError):
        asyncio.run(capture_case(case))


def test_local_only_rejection_cannot_count_as_cloud_review():
    case = {"payload": {"resource_type": "code", "content": {"source": "eval(x)"},
                        "reference_context": {}}}
    case["payload_sha256"] = sha(canonical(case["payload"]))
    with pytest.raises(ValueError, match="LOCAL_ONLY"):
        asyncio.run(capture_case(case))


def test_approved_adr_extension_does_not_allow_edited_original_or_sample():
    original = b"approved original\n"
    extension = original + b"\napproved addendum\n"
    verify_current_attachment(ADR, original, extension, extension)
    with pytest.raises(AssertionError):
        verify_current_attachment(ADR, original, extension + b"unauthorized", extension)
    with pytest.raises(AssertionError):
        verify_current_attachment(ADR, original, b"changed\n", b"changed\n")
    with pytest.raises(AssertionError):
        verify_current_attachment("docs/acceptance/phase-1-dynamic-v1/history.json",
                                  original, extension, extension)
