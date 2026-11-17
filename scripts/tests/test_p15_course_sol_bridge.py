"""Offline course source, identity and advisory checkpoints across HTTPX Mock."""

# ruff: noqa: E402
import asyncio
import json
import socket
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from isolated_diagnostics import p15_course_sol_bridge as bridge
from test_p15_sol_compatibility_proposal import sample


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Real network forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


def run_case(fault=None, verdict="revise"):
    _, response, payload, opinion = sample()
    body = bridge.review_request(bridge.STAGE, payload)
    response["instructions"] = body["input"][0]["content"] + bridge.compat.SUFFIX
    if verdict == "pass":
        opinion.update(verdict="pass", issues=[])
    calls, current = [], []
    if fault == "path":
        opinion["issues"][0]["source_pointer"] = "/source/scene/text"
    if fault == "quote":
        opinion["issues"][0]["evidence_quote"] = "invented"
    if fault == "sha":
        opinion["source_sha256"] = "a" * 64
    if fault == "suffix":
        response["instructions"] += " "
    if fault == "reasoning":
        response["output"][0]["summary"] = [{"text": "unrequested"}]
    response["output"][-1]["content"][0]["text"] = json.dumps(opinion)

    def handler(request):
        calls.append(json.loads(request.content))
        assert request.url == bridge.ENDPOINT
        assert "authorization" not in request.headers
        return httpx.Response(503 if fault == "http" else 200, json=response)

    async def verify(source):
        assert source == payload
        current.append(True)
        return not (
            fault == "stale_before" or fault == "stale_after" and len(current) == 2
        )

    runner = bridge.MockCourseReview(
        httpx.MockTransport(handler), owner="owner", course="course"
    )
    args = dict(owner="owner", course="course", payload=payload, verify_current=verify)
    return runner, args, calls, current


def test_generation_source_to_review_preserves_exact_payload_and_stops_for_assistant():
    runner, args, calls, current = run_case()
    original = deepcopy(args["payload"])
    event = asyncio.run(runner.review(**args))
    assert event["state"] == "paused_for_delegated_assistant"
    assert event["mock_only"] and not event["production_admission"]
    assert event["reported_output_tokens_including_reasoning"] == 100
    assert len(current) == 2 and len(calls) == 1
    assert calls[0]["reasoning"] == {"effort": "low"}
    assert json.loads(calls[0]["input"][1]["content"]) == original == args["payload"]
    assert calls[0]["text"]["format"]["schema"] == bridge.compat.schema()
    assert not runner.events[0]["independent_human_truth"]
    with pytest.raises(ValueError, match="STOPPED_NO_RESTART"):
        asyncio.run(runner.review(**args))
    assert len(calls) == 1


def test_model_pass_still_requires_actual_delegated_assistant_review():
    runner, args, calls, _ = run_case(verdict="pass")
    event = asyncio.run(runner.review(**args))
    assert event["state"] == "delegated_assistant_review_required"
    assert not event["production_admission"] and len(calls) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "path",
        "quote",
        "sha",
        "suffix",
        "reasoning",
        "http",
        "stale_before",
        "stale_after",
    ],
)
def test_failures_never_record_success_and_never_resend(fault):
    runner, args, calls, _ = run_case(fault)
    with pytest.raises(ValueError):
        asyncio.run(runner.review(**args))
    assert runner.stopped and runner.events == []
    sent = len(calls)
    assert sent == (0 if fault == "stale_before" else 1)
    with pytest.raises(ValueError, match="STOPPED_NO_RESTART"):
        asyncio.run(runner.review(**args))
    assert len(calls) == sent


@pytest.mark.parametrize("field", ["owner", "course"])
def test_cross_owner_or_course_refused_before_mock_send(field):
    runner, args, calls, _ = run_case()
    args[field] = "different"
    with pytest.raises(ValueError, match="OWNER_COURSE_CHANGED"):
        asyncio.run(runner.review(**args))
    assert calls == []


def test_tampered_source_refused_without_silent_rehash():
    runner, args, calls, _ = run_case()
    args["payload"]["source"]["scene"]["text"] = "different source"
    with pytest.raises(ValueError, match="EXACT_SOURCE_ENVELOPE_REQUIRED"):
        asyncio.run(runner.review(**args))
    assert calls == []


def test_probe_cannot_enter_scene_schema_route():
    _, _, payload, _ = sample()
    with pytest.raises(ValueError, match="SCENE_ONLY_PROBES_NOT_ADMITTED"):
        bridge.review_request("development_review_probe", payload)


def test_real_transport_rejected_before_any_network():
    with pytest.raises(ValueError, match="MOCK_TRANSPORT_REQUIRED"):
        bridge.MockCourseReview(object(), owner="owner", course="course")
