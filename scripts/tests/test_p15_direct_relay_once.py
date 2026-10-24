"""The user-authorized direct observation never calls the count endpoint or retries."""

import asyncio
import hashlib
import json
import socket
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import run_p15_direct_relay_once as p  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402

KEY = "SYNTHETIC-ONLY-KEY-000000000000"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("No real network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.mark.parametrize(
    "mode",
    ["clean", "http404", "null_cap", "injected", "bad_schema", "key_echo", "timeout"],
)
def test_exactly_one_direct_request_terminal(tmp_path, mode):
    from dataclasses import asdict

    package = "a" * 64
    grant = dict(
        scope="PHASE-1.5-T038",
        batch_id=p.BATCH,
        package_sha256=package,
        limits=asdict(p.LIMITS),
        evidence_ref="OFFLINE SYNTHETIC ONLY",
    )
    calls = []
    body = json.loads((p.BASE / "request.json").read_bytes())

    def handler(request):
        calls.append(request)
        assert request.url.path == "/v1/responses"
        assert hashlib.sha256(request.content).hexdigest() == p.BODY_SHA
        if mode == "timeout":
            raise httpx.ReadTimeout("unsafe " + KEY)
        if mode == "http404":
            return httpx.Response(404, json={"error": "unsupported"})
        data = dict(
            object="response",
            status="completed",
            error=None,
            model="gpt-6-luna",
            store=False,
            service_tier="default",
            instructions=None,
            max_output_tokens=16,
            usage=dict(input_tokens=37, output_tokens=13, total_tokens=50),
            text=body["text"],
            output=[
                dict(
                    type="message",
                    role="assistant",
                    content=[dict(type="output_text", text='{"result":"OK"}')],
                )
            ],
        )
        if mode == "null_cap":
            data["max_output_tokens"] = None
        if mode == "injected":
            data["instructions"] = "unrequested suffix"
        if mode == "bad_schema":
            data["output"][0]["content"][0]["text"] = '{"result":"NO"}'
        if mode == "key_echo":
            data["leak"] = KEY
        return httpx.Response(200, json=data)

    target = ApprovedTarget(p.URL, "www.cbbb.fun", 443, ("8.8.8.8",))
    output = tmp_path / "output"
    result = asyncio.run(
        p.run(
            p.BASE,
            output,
            package,
            grant,
            KEY,
            lambda: target,
            lambda: httpx.MockTransport(handler),
        )
    )
    assert (
        len(calls) == 1
        and result["http_dispatch_markers"] == result["model_dispatch_markers"] == 1
    )
    assert result["outcome"] == (
        "direct_response_observed"
        if mode == "clean"
        else "http_failure"
        if mode == "http404"
        else "transport_or_evidence_unknown"
        if mode in ("timeout", "key_echo")
        else "response_contract_issues_observed"
    )
    assert (
        result["count_equivalence_tested"] is False
        and result["count_call_sent"] is False
    )
    assert result["actual_invoice"] is None and result["T038_completed"] is False
    assert result["local_accounting"]["fee_micros"] == 10000
    assert KEY.encode() not in b"".join(
        x.read_bytes() for x in output.iterdir() if x.is_file()
    )
    with pytest.raises(FileExistsError):
        asyncio.run(
            p.run(
                p.BASE,
                output,
                package,
                grant,
                KEY,
                lambda: pytest.fail("No restart"),
                lambda: pytest.fail("No restart"),
            )
        )
