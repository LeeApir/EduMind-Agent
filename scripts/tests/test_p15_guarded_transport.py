"""Zero-network regression for guarded diagnostic composition and durable evidence."""

import asyncio
import json
import socket
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
    str(ROOT / "backend/tests"),
]
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, Refused, digest  # noqa: E402
from acceptance_support.p15_diagnostic_transport import CountedTransport  # noqa: E402
from acceptance_support.p15_guarded_transport import (  # noqa: E402
    GuardedStrictDiagnosticAdapter,
    GuardedWireTransport,
)  # noqa: E402
from acceptance_support.p15_strict_transport import SCHEMAS  # noqa: E402
from test_free_course_planning import candidate  # noqa: E402

from app.core.config import ProviderSettings  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402
from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest  # noqa: E402


@pytest.fixture(autouse=True)
def forbid_network_env(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.name != ".env"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)


def ledger_at(path):
    ledger = Ledger(path / "TEST_ONLY.sqlite")
    limits = Limits(2, 32000, 8000, None, 600)
    approval = dict(
        scope="PHASE-1.5-T038",
        batch_id="TEST_ONLY",
        package_sha256="a" * 64,
        limits=asdict(limits),
        fee_cap_waiver=True,
        evidence_ref="synthetic_only",
    )
    ledger.start(
        "TEST_ONLY", "a" * 64, limits, approval, pinned_approval_sha256=digest(approval)
    )
    return ledger


def originals():
    report = json.loads(
        (
            ROOT
            / "docs/acceptance/phase-1.5-development-diagnostic-results-r03/results.json"
        ).read_text()
    )
    paths = {i["role"]: Path(i["path"]) for i in report["raw_evidence"]}
    return [
        json.loads(paths[k].read_bytes()) for k in ("request_body", "model_response")
    ]


@pytest.mark.parametrize(
    "mode",
    [
        "actual",
        "equal_injected",
        "clean",
        "cap",
        "instructions_missing",
        "schema",
        "http",
        "malformed",
        "key_echo",
        "oversized",
        "timeout",
        "disk",
    ],
)
def test_before_settlement_and_evidence(tmp_path, monkeypatch, mode):
    body, response = originals()
    if mode != "actual":
        response["instructions"] = "\n\n".join(
            m["content"] for m in body["input"] if m["role"] == "system"
        )
        response["max_output_tokens"] = 8000
    if mode == "equal_injected":
        response["instructions"] += "\nUNAPPROVED"
        response["max_output_tokens"] = None
    if mode == "cap":
        response["max_output_tokens"] = None
    if mode == "instructions_missing":
        response.pop("instructions")
    if mode == "schema":
        response["text"]["format"]["schema"] = {}
    seen = []

    def handler(request):
        seen.append((request.url.path, request.content))
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(
                200,
                json={
                    "object": "response.input_tokens",
                    "input_tokens": 1677 if mode == "actual" else 6507,
                },
            )
        if mode == "timeout":
            raise httpx.ReadTimeout("TEST_SECRET_IN_EXCEPTION")
        raw = json.dumps(response).encode()
        if mode == "malformed":
            raw = b"not json"
        if mode == "key_echo":
            raw = b'{"text":"TEST_SECRET_IN_EXCEPTION"}'
        if mode == "oversized":
            raw = b"x" * (2 * 1024 * 1024 + 1)
        return httpx.Response(503 if mode == "http" else 200, content=raw)

    ledger = ledger_at(tmp_path)
    guard = GuardedWireTransport(
        httpx.MockTransport(handler), tmp_path / "audit", "TEST_SECRET_IN_EXCEPTION"
    )
    if mode == "disk":

        def fail(*args, **kwargs):
            raise OSError("TEST_SECRET_IN_EXCEPTION")

        monkeypatch.setattr(guard, "save", fail)
    transport = CountedTransport(
        guard, ledger, "TEST_ONLY", "a" * 64, tmp_path, "TEST_SECRET_IN_EXCEPTION"
    )
    request = httpx.Request(
        "POST", "https://www.cbbb.fun/v1/responses", content=json.dumps(body).encode()
    )
    try:
        if mode == "clean":
            asyncio.run(transport.handle_async_request(request))
            assert transport.usage == (6507, 480)
            assert ledger.usage("TEST_ONLY")["input_tokens"] == 6507
        else:
            with pytest.raises((Refused, ValueError, httpx.ReadTimeout, OSError)):
                asyncio.run(transport.handle_async_request(request))
            assert transport.proof is None and transport.usage is None
            assert (
                ledger.db.execute("SELECT state FROM batches").fetchone()[0]
                == "stopped"
            )
            assert ledger.usage("TEST_ONLY")["input_tokens"] == 32000
            assert ledger.usage("TEST_ONLY")["output_tokens"] == 8000
        if mode == "disk":
            assert not seen
        else:
            assert len(seen) == 2 and seen[0][1] == seen[1][1]
            files = list((tmp_path / "audit").glob("*.json"))
            assert all(p.stat().st_mode & 0o077 == 0 for p in files)
            text = "".join(p.read_text() for p in files)
            assert "TEST_SECRET_IN_EXCEPTION" not in text
            assert "Authorization" not in text and "Cookie" not in text
            statuses = [
                json.loads(p.read_text())["http_status"]
                for p in files
                if p.name.endswith("-status.json")
            ]
            assert sorted(statuses) == (
                [200, 503]
                if mode == "http"
                else [200]
                if mode == "timeout"
                else [200, 200]
            )
            if mode not in ("timeout", "key_echo", "oversized"):
                assert len(list((tmp_path / "audit").glob("*-body.json"))) == 2
            if mode not in ("clean",):
                assert list((tmp_path / "audit").glob("*-failure.json"))
    finally:
        ledger.close()


def test_real_transport_refused_before_directory_or_egress(tmp_path):
    class RealLooking(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            pytest.fail("must not reach network transport")

    with pytest.raises(Refused, match="INDEPENDENT_PREFLIGHT_PROOF"):
        GuardedWireTransport(RealLooking(), tmp_path / "never_created", "TEST")
    assert not (tmp_path / "never_created").exists()


def test_request_credential_echo_never_saved_or_sent(tmp_path):
    body, _ = originals()
    body["input"][-1]["content"] = "TEST_SECRET"
    seen = []
    ledger = ledger_at(tmp_path)
    guard = GuardedWireTransport(
        httpx.MockTransport(lambda r: seen.append(r)), tmp_path / "audit", "TEST_SECRET"
    )
    transport = CountedTransport(
        guard, ledger, "TEST_ONLY", "a" * 64, tmp_path, "TEST_SECRET"
    )
    try:
        with pytest.raises(Refused, match="CREDENTIAL_ECHO"):
            asyncio.run(
                transport.handle_async_request(
                    httpx.Request(
                        "POST", "https://www.cbbb.fun/v1/responses", json=body
                    )
                )
            )
        assert not seen
        assert "TEST_SECRET" not in "".join(
            p.read_text() for p in tmp_path.rglob("*.json")
        )
        assert ledger.db.execute("SELECT state FROM batches").fetchone()[0] == "stopped"
    finally:
        ledger.close()


def test_count_body_binding_rejects_changed_generation_and_repeated_count(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200, json={"object": "response.input_tokens", "input_tokens": 1}
        )

    guard = GuardedWireTransport(
        httpx.MockTransport(handler), tmp_path / "audit", "TEST_SECRET"
    )
    asyncio.run(
        guard.handle_async_request(
            httpx.Request(
                "POST", "https://www.cbbb.fun/v1/responses/input_tokens", content=b"{}"
            )
        )
    )
    with pytest.raises(Refused, match="COUNT_REQUEST_BINDING_MISSING"):
        asyncio.run(
            guard.handle_async_request(
                httpx.Request(
                    "POST",
                    "https://www.cbbb.fun/v1/responses",
                    content=b'{"different":true}',
                )
            )
        )
    with pytest.raises(Refused, match="DUPLICATE_COUNT_REQUEST"):
        asyncio.run(
            guard.handle_async_request(
                httpx.Request(
                    "POST",
                    "https://www.cbbb.fun/v1/responses/input_tokens",
                    content=b"{}",
                )
            )
        )
    assert len(seen) == 1


@pytest.mark.parametrize("invalid_local", [False, True])
def test_strict_adapter_composition_preserves_full_local_schema(
    tmp_path, invalid_local
):
    ledger = ledger_at(tmp_path)
    seen = []
    value = candidate(1)
    if invalid_local:
        value["plan"]["scenes"][0]["forms"] = ["text", "text"]

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(
                200, json={"object": "response.input_tokens", "input_tokens": 100}
            )
        return httpx.Response(
            200,
            json=dict(
                model="gpt-6-luna",
                status="completed",
                error=None,
                instructions="\n\n".join(
                    m["content"] for m in body["input"] if m["role"] == "system"
                ),
                max_output_tokens=8000,
                text=body["text"],
                usage=dict(input_tokens=100, output_tokens=100),
                output=[
                    dict(
                        type="message",
                        role="assistant",
                        status="completed",
                        content=[dict(type="output_text", text=json.dumps(value))],
                    )
                ],
            ),
        )

    adapter = GuardedStrictDiagnosticAdapter(
        ProviderSettings("https://www.cbbb.fun/v1", "SYNTHETIC_KEY", "gpt-6-luna"),
        SimpleNamespace(
            approve_base=lambda: ApprovedTarget(
                "https://www.cbbb.fun/v1", "www.cbbb.fun", 443, ("8.8.8.8",)
            )
        ),
        ledger,
        "TEST_ONLY",
        "a" * 64,
        tmp_path,
        lambda: httpx.MockTransport(handler),
    )
    try:
        reply = asyncio.run(
            adapter.send(
                StructuredRequest(
                    TextRequest(
                        (
                            ChatMessage("system", "trusted"),
                            ChatMessage("user", "synthetic"),
                        ),
                        max_output_tokens=8000,
                    ),
                    SCHEMAS["free_course_plan_generation"],
                    "free_course_plan_generation",
                ),
                retry_safe=False,
            )
        )
        assert reply.evidence == "complete_response" and reply.value == (
            {} if invalid_local else value
        )
        assert len(seen) == 2 and seen[0] == seen[1]
    finally:
        ledger.close()
