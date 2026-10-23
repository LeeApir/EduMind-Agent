"""Actual adapter wire behind explicit HTTPX mock, no real credentials or sockets."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, Refused, digest  # noqa: E402
from acceptance_support.p15_diagnostic_transport import DiagnosticAdapter  # noqa: E402
from app.core.config import ProviderSettings  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402
from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest  # noqa: E402


@pytest.mark.parametrize(
    "mode",
    [
        "valid",
        "count_404",
        "count_large",
        "model_changed",
        "usage_missing",
        "usage_large",
        "count_mismatch",
        "secret_echo",
        "invalid_schema",
        "timeout",
    ],
)
def test_counted_wire_and_fail_closed_shared_ledger(tmp_path, mode):
    ledger = Ledger(tmp_path / "TEST_ONLY.sqlite")
    limits = Limits(6, 100000, 24000, None, 600)
    approval = dict(
        package_sha256="a" * 64,
        batch_id="TEST_ONLY",
        limits=asdict(limits),
        scope="PHASE-1.5-T038",
        evidence_ref="synthetic",
        fee_cap_waiver=True,
    )
    ledger.start(
        "TEST_ONLY", "a" * 64, limits, approval, pinned_approval_sha256=digest(approval)
    )
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append((str(request.url), body))
        assert request.headers["host"] == "www.cbbb.fun"
        assert request.extensions["sni_hostname"] == "www.cbbb.fun"
        assert (
            body["model"] == "gpt-6-luna"
            and body["store"] is False
            and body["reasoning"] == {"effort": "none"}
        )
        if request.url.path.endswith("/input_tokens"):
            return (
                httpx.Response(404, json={})
                if mode == "count_404"
                else httpx.Response(
                    200,
                    json={
                        "object": "response.input_tokens",
                        "input_tokens": 32001 if mode == "count_large" else 100,
                    },
                )
            )
        if mode == "timeout":
            raise httpx.ReadTimeout("synthetic; do not retry")
        text = json.dumps({"ok": True} if mode != "invalid_schema" else {"bad": True})
        if mode == "secret_echo":
            text = "TEST_ONLY_SECRET"
        value = dict(
            model="other" if mode == "model_changed" else "gpt-6-luna",
            status="completed",
            output=[
                dict(
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[dict(type="output_text", text=text)],
                )
            ],
            usage={
                "input_tokens": 101 if mode == "count_mismatch" else 100,
                "output_tokens": 9000 if mode == "usage_large" else 100,
            },
        )
        if mode == "usage_missing":
            value.pop("usage")
        return httpx.Response(200, json=value)

    guard = SimpleNamespace(
        approve_base=lambda: ApprovedTarget(
            "https://www.cbbb.fun/v1", "www.cbbb.fun", 443, ("8.8.8.8",)
        )
    )
    adapter = DiagnosticAdapter(
        ProviderSettings("https://www.cbbb.fun/v1", "TEST_ONLY_SECRET", "gpt-6-luna"),
        guard,
        ledger,
        "TEST_ONLY",
        "a" * 64,
        tmp_path,
        lambda: httpx.MockTransport(handler),
    )
    request = StructuredRequest(
        TextRequest(
            (ChatMessage("user", "Return a boolean."),),
            max_output_tokens=8000,
            temperature=0.2,
        ),
        {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        "offline_test",
    )
    try:
        reply = asyncio.run(adapter.send(request, retry_safe=False))
        if mode in ["valid", "invalid_schema"]:
            assert (
                reply.evidence == "complete_response"
                and reply.input_tokens == 100
                and reply.output_tokens == 100
            )
            assert reply.value == ({"ok": True} if mode == "valid" else {})
            assert len(seen) == 2 and seen[0][1] == seen[1][1]
            assert ledger.usage("TEST_ONLY")["input_tokens"] == 100
            assert ledger.usage("TEST_ONLY")["requests"] == 2
            assert len(list(tmp_path.glob("*-receipt.json"))) == 1
        else:
            assert reply.evidence == "unknown"
            assert (
                ledger.db.execute("SELECT state FROM batches").fetchone()[0]
                == "stopped"
            )
            with pytest.raises(Refused):
                ledger.reserve(
                    "TEST_ONLY", "a" * 64, "new", input_max=1, output_max=1, fee_max=0
                )
            assert not list(tmp_path.glob("*-response.json"))
        if mode in ["count_404", "count_large"]:
            assert len(seen) == 1
        for p in tmp_path.glob("*.json"):
            assert "TEST_ONLY_SECRET" not in p.read_text()
    finally:
        ledger.close()
