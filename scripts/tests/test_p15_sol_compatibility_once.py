"""One-shot proof: no retry, no leaked key, exact final source and fixed differences."""

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
sys.path.insert(0, str(ROOT / "backend"))
import run_p15_sol_compatibility_once as p
from app.core.provider_target import ApprovedTarget


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("Offline test only")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


def material():
    return json.loads((p.BASE / "request.json").read_bytes()), json.loads(
        (p.BASE / "expected.json").read_bytes()
    )


def reply(body, expected):
    source = json.loads(body["input"][-1]["content"])
    opinion = {
        "source_sha256": source["source_sha256"],
        "scope_status": "complete",
        "uncertain_reason": None,
        "verdict": "revise",
        "issues": [
            {
                "source_pointer": expected["incorrect_pointer"],
                "evidence_quote": expected["incorrect_quote"],
                "area": "fact",
                "severity": "severe",
                "message": "下标访问不必逐项扫描。",
            }
        ],
    }
    return {
        "object": "response",
        "model": "gpt-6.1-sol",
        "status": "completed",
        "store": False,
        "tools": [],
        "instructions": body["input"][0]["content"] + p.proposal.SUFFIX,
        "reasoning": {"effort": "low"},
        "usage": {
            "input_tokens": 100,
            "output_tokens": 200,
            "total_tokens": 300,
            "output_tokens_details": {"reasoning_tokens": 10},
        },
        "output": [
            {
                "type": "reasoning",
                "summary": [],
                "content": [],
                "encrypted_content": "TEST_OPAQUE_NOT_ACTUAL_REASONING",
            },
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(opinion)}],
            },
        ],
    }


def target():
    return ApprovedTarget("https://aiapi.world/v1", "aiapi.world", 443, ("8.8.8.8",))


def test_single_success_has_immutable_dispatch_and_cannot_restart(tmp_path):
    body, expected = material()
    calls = []
    output = tmp_path / "one"

    def handler(request):
        calls.append(request)
        assert (
            request.headers["host"] == "aiapi.world" and request.url.host == "8.8.8.8"
        )
        assert request.extensions["sni_hostname"] == "aiapi.world"
        assert (output / "dispatch.json").exists()
        return httpx.Response(200, json=reply(body, expected))

    def run():
        return asyncio.run(
            p.run_once(
                "a" * 64,
                body,
                expected,
                "TEST_ONLY_API_KEY",
                output=output,
                target_factory=target,
                transport_factory=lambda: httpx.MockTransport(handler),
            )
        )

    result = run()
    assert (
        result["state"] == "one_synthetic_observation_only"
        and result["dispatch_markers"] == 1
    )
    assert (
        result["workflow_requests_including_prior"] == 7
        and result["outcome"]["synthetic_only_pass"]
    )
    assert not result["T038_completed"] and result["actual_fee_usd"] is None
    with pytest.raises(FileExistsError):
        run()
    assert len(calls) == 1
    assert "TEST_ONLY_API_KEY" not in "".join(
        f.read_text() for f in output.glob("*.json")
    )


@pytest.mark.parametrize(
    "fault",
    [
        "timeout",
        "redirect",
        "instructions",
        "reasoning",
        "pointer",
        "quote",
        "key",
        "false_control",
    ],
)
def test_any_anomaly_stops_without_retry(tmp_path, fault):
    body, expected = material()
    calls = []
    output = tmp_path / "one"

    def handler(request):
        calls.append(request)
        if fault == "timeout":
            raise httpx.ReadTimeout("synthetic")
        r = reply(body, expected)
        if fault == "instructions":
            r["instructions"] += "unexpected"
        if fault == "reasoning":
            r["reasoning"]["effort"] = "high"
        if fault == "key":
            r["extra"] = "TEST_ONLY_API_KEY"
        if fault in ("pointer", "quote", "false_control"):
            opinion = json.loads(r["output"][-1]["content"][0]["text"])
            if fault == "pointer":
                opinion["issues"][0]["source_pointer"] = (
                    "/source" + expected["incorrect_pointer"]
                )
            if fault == "quote":
                opinion["issues"][0]["evidence_quote"] = "NO_MATCH"
            if fault == "false_control":
                item = deepcopy(opinion["issues"][0])
                item["source_pointer"] = expected["correct_pointer"]
                item["evidence_quote"] = "数组"
                opinion["issues"].append(item)
            r["output"][-1]["content"][0]["text"] = json.dumps(opinion)
        return httpx.Response(
            307 if fault == "redirect" else 200,
            json=r,
            headers={"location": "https://other.example/v1"}
            if fault == "redirect"
            else {},
        )

    result = asyncio.run(
        p.run_once(
            "a" * 64,
            body,
            expected,
            "TEST_ONLY_API_KEY",
            output=output,
            target_factory=target,
            transport_factory=lambda: httpx.MockTransport(handler),
        )
    )
    assert result["state"] == "stopped" and len(calls) == 1
    assert result["automatic_restart"] is False
    assert "TEST_ONLY_API_KEY" not in "".join(
        f.read_text() for f in output.glob("*.json")
    )


def test_old_deadline_expiry_prevents_even_dns(tmp_path, monkeypatch):
    body, expected = material()
    monkeypatch.setattr(p.time, "time", lambda: p.DEADLINE + 1)

    def deny():
        raise AssertionError("Must not resolve")

    r = asyncio.run(
        p.run_once(
            "a" * 64,
            body,
            expected,
            "TEST_ONLY_API_KEY",
            output=tmp_path / "one",
            target_factory=deny,
        )
    )
    assert r["state"] == "stopped" and r["dispatch_markers"] == 0
