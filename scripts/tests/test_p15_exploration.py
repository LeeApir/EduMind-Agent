"""Explicit waiver does not weaken schema, source, transport or human review checks."""

# ruff: noqa: E402
import asyncio
import json
import socket
import sys
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from isolated_diagnostics import p15_exploration as x
from isolated_diagnostics import p15_split_provider as p
from app.core.provider_target import ApprovedTarget
from app.agents.free_course_planning import SCHEMA
from app.services.provider_gateway import TextRequest, ChatMessage, StructuredRequest
from test_p15_split_provider import json_reply, scene_target, clean_opinion


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("Offline only")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


@pytest.fixture
def setup(tmp_path):
    grant = {
        "scope": "PHASE-1.5-T038",
        "package_sha256": "a" * 64,
        "batch_id": "p15-split-experiment-test",
        "limits": asdict(x.ExplorationLimits()),
        "evidence_ref": "SYNTHETIC_TEST_NOT_APPROVAL",
        "fee_cap_waiver": True,
    }
    j = x.ExplorationJournal.create(
        tmp_path / "wire", grant["batch_id"], "a" * 64, grant
    )
    i = p.Identity("slot", "owner", "course")
    j.bind(i)
    yield j, i
    j.ledger.close()


def adapter(j, handler):
    return x.ExplorationAdapter(
        j,
        {"generation": "TEST_ONLY_DEEPSEEK_KEY", "review": "TEST_ONLY_AIAPI_KEY"},
        lambda role: ApprovedTarget(
            "https://api.deepseek.com"
            if role == "generation"
            else "https://aiapi.world/v1",
            "api.deepseek.com" if role == "generation" else "aiapi.world",
            443,
            ("8.8.8.8",),
        ),
        lambda: httpx.MockTransport(handler),
    )


def plan_request():
    return StructuredRequest(
        TextRequest(
            (
                ChatMessage("system", "Synthetic only"),
                ChatMessage("user", "Synthetic goal"),
            ),
            max_output_tokens=1,
        ),
        SCHEMA,
        "free_course_plan_generation",
    )


def test_waiver_preserves_unverified_flags_and_real_observed_overflow(setup):
    j, i = setup

    def response(r):
        result = json_reply(r, {})
        body = json.loads(result.content)
        body["usage"] = {
            "input_tokens": 50000,
            "output_tokens": 20000,
            "total_tokens": 70000,
        }
        return httpx.Response(200, json=body)

    a = adapter(j, response)
    assert a.bound(i).policy.bounded_output_verified is False
    with pytest.raises(p.Refused, match="NO_VERIFIED_INPUT_BOUND"):
        a.bound(i).input_upper_bound(plan_request())
    reply = asyncio.run(a.bound(i).send(plan_request(), retry_safe=False))
    assert reply.evidence == "complete_response" and (
        reply.input_tokens,
        reply.output_tokens,
    ) == (50000, 20000)
    assert j.ledger.usage(j.batch)["input_tokens"] == 50000
    assert j.ledger.usage(j.batch)["fee_micros"] is None
    assert j.events("unbounded_usage_observed")[0]["reported_over_request"] is True
    with pytest.raises(p.Refused, match="ATTEMPT_ALREADY_RESERVED"):
        asyncio.run(a.bound(i).send(plan_request(), retry_safe=False))


@pytest.mark.parametrize(
    "fault", ["model", "instructions", "usage", "key", "timeout", "role", "host"]
)
def test_other_protocol_failures_still_stop_without_retry(setup, fault):
    j, i = setup
    calls = []

    def response(r):
        calls.append(r)
        if fault == "timeout":
            raise httpx.ReadTimeout("Synthetic")
        b = json.loads(json_reply(r, {}).content)
        if fault == "model":
            b["model"] = "unexpected-model"
        if fault == "instructions":
            b["instructions"] = "Injected coding assistant instructions"
        if fault == "usage":
            b["usage"]["total_tokens"] = 999
        if fault == "key":
            b["extra"] = "TEST_ONLY_AIAPI_KEY"
        if fault == "role":
            b["output"][0]["type"] = "function_call"
        if fault == "host":
            b["status"] = "incomplete"
        return httpx.Response(200, json=b)

    a = adapter(j, response)
    with pytest.raises((p.Refused, httpx.ReadTimeout)):
        asyncio.run(a.bound(i).send(plan_request(), retry_safe=False))
    assert len(calls) == 1 and j.ledger.usage(j.batch)["requests"] == 1
    with pytest.raises(p.Refused, match="BATCH_STOPPED"):
        asyncio.run(a.bound(i).send(plan_request(), retry_safe=False))
    assert len(calls) == 1
    assert "TEST_ONLY_AIAPI_KEY" not in "".join(
        p.read_text() for p in j.output.glob("*response.json")
    )


def test_source_review_pause_and_exact_human_gate_remain(setup):
    j, i = setup
    t = scene_target(i)
    j.freeze(i, [t])

    def response(r):
        source = json.loads(json.loads(r.content)["input"][-1]["content"])
        op = clean_opinion(source)
        op.update(
            scope_status="insufficient_evidence",
            uncertain_reason="Synthetic missing context",
            verdict="uncertain",
        )
        return json_reply(r, op)

    a = adapter(j, response)

    async def current(t):
        return True

    assert (
        asyncio.run(x.review_pending(a, i, verify_current=current))
        == "paused_for_human"
    )
    assert j.events("scene_review_finished")[0]["mock_only"] is False
    with pytest.raises(p.Refused, match="SCENE_ADVISORY_REQUIRES_HUMAN"):
        j.guard()


def test_request_count_and_unknown_no_resend(setup):
    j, i = setup
    for n in range(250):
        j.ledger.reserve(
            j.batch, j.package, str(n), input_max=0, output_max=0, fee_max=0
        )
    with pytest.raises(p.Refused, match="BUDGET_EXHAUSTED"):
        j.ledger.reserve(
            j.batch, j.package, "overflow", input_max=0, output_max=0, fee_max=0
        )
    assert j.ledger.usage(j.batch)["requests"] == 250
