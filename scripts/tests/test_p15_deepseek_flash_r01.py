"""No-network regression for direct-authorized DeepSeek synthetic observation."""

import asyncio
import json
import shutil
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import run_p15_deepseek_flash_r01 as p  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402

KEY = "synthetic-fixture-not-a-real-key-0000"
TARGET = ApprovedTarget(
    "https://api.deepseek.com", "api.deepseek.com", 443, ("8.8.8.8",)
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No actual DNS or sockets")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.fixture
def packet(tmp_path):
    base = tmp_path / "docs/acceptance/phase-1.5-deepseek-flash-r01"
    shutil.copytree(p.BASE, base)
    manifest = json.loads((base / "manifest.json").read_text())
    for name in manifest["sha256"]:
        dest = tmp_path / name
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)
    _, sha, _ = p.load_package(base, tmp_path)
    grant = {
        "package_sha256": sha,
        "batch_id": p.BATCH,
        "scope": "PHASE-1.5-T038",
        "limits": p.asdict(p.LIMITS),
        "authorization_basis": "latest_explicit_direct_execution_instruction",
        "new_manifest_independently_human_reviewed": False,
        "human_message": "直接执行，不用批准",
        "evidence_ref": "SYNTHETIC_OFFLINE_FIXTURE_ONLY",
        "no_course_or_review_calls": True,
    }
    (base / "execution-authorization.json").write_text(json.dumps(grant))
    rates = p.parse((base / "pricing.json").read_bytes())
    now = datetime.fromisoformat(rates["checked_at"]) + timedelta(seconds=1)
    return base, tmp_path, now


def reply(body, value):
    return {
        "object": "response",
        "status": "completed",
        "model": "deepseek-flash",
        "store": False,
        "usage": {"input_tokens": 60, "output_tokens": 20, "total_tokens": 80},
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(value)}],
            }
        ],
    }


def stream_bytes(r):
    text = p.output_text(r)
    events = [
        {
            "type": "response.created",
            "sequence_number": 0,
            "response": {"status": "in_progress"},
        },
        {"type": "response.output_text.delta", "sequence_number": 1, "delta": text},
        {"type": "response.completed", "sequence_number": 2, "response": r},
    ]
    return b"".join(
        ("event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n").encode()
        for e in events
    )


def test_real_package_checks_without_env_or_dns(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("No environment reads")

    monkeypatch.setattr(p, "credential", fail)
    monkeypatch.setattr(p, "dotenv_values", fail)
    assert p.load_package()[0]["url"] == p.URL


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "incomplete"),
        ("model", "other"),
        ("store", True),
        ("instructions", "Injected coding role"),
        ("max_output_tokens", 999),
        ("tools", [{"type": "function"}]),
        ("usage", {"input_tokens": 60, "output_tokens": 129, "total_tokens": 189}),
        ("usage", {"input_tokens": 60, "output_tokens": 20, "total_tokens": 90}),
        ("usage", {"input_tokens": True, "output_tokens": 20, "total_tokens": 21}),
    ],
)
def test_response_contradictions_stop(field, value):
    _, _, plan = p.load_package()
    body = p.parse((p.BASE / "S1.json").read_bytes())
    r = reply(body, plan["expected"]["S1"])
    r[field] = value
    with pytest.raises(p.ProbeFailure):
        p.observe(body, r, plan["expected"]["S1"])


def test_absent_echo_stays_unknown_not_complete_compatibility():
    _, _, plan = p.load_package()
    body = p.parse((p.BASE / "S1.json").read_bytes())
    result = p.observe(
        body, reply(body, plan["expected"]["S1"]), plan["expected"]["S1"]
    )
    assert "instructions_echo_missing" in result["unknown"]
    assert "max_output_tokens_echo_missing" in result["unknown"]
    assert "independent_input_count_unavailable" in result["unknown"]


def test_invalid_enum_even_with_echo_and_consistent_usage_rejected():
    _, _, plan = p.load_package()
    body = p.parse((p.BASE / "S2.json").read_bytes())
    wrong = {**plan["expected"]["S2"], "objective_source": "user's words"}
    r = reply(body, wrong)
    r.update(
        instructions=body["instructions"], max_output_tokens=512, text=body["text"]
    )
    with pytest.raises(p.ProbeFailure, match="LOCAL_FULL_SCHEMA_REJECTED"):
        p.observe(body, r, plan["expected"]["S2"])


@pytest.mark.parametrize(
    "mode",
    [
        "missing_terminal",
        "duplicate_terminal",
        "bad_sequence",
        "delta_mismatch",
        "failure",
        "tool_item",
    ],
)
def test_sse_failures_rejected(mode):
    _, _, plan = p.load_package()
    body = p.parse((p.BASE / "S2.json").read_bytes())
    raw = stream_bytes(reply(body, plan["expected"]["S2"]))
    blocks = raw.split(b"\n\n")
    if mode == "missing_terminal":
        raw = b"\n\n".join(blocks[:2]) + b"\n\n"
    if mode == "duplicate_terminal":
        raw += blocks[2] + b"\n\n"
    if mode == "bad_sequence":
        raw = raw.replace(b'"sequence_number": 1', b'"sequence_number": 0')
    if mode == "delta_mismatch":
        raw = raw.replace(b'"delta": "', b'"delta": "wrong', 1)
    if mode == "failure":
        raw = raw.replace(b"response.completed", b"response.failed")
    if mode == "tool_item":
        raw = raw.replace(b'"delta":', b'"item": {"type":"function_call"}, "delta":', 1)
    with pytest.raises(p.ProbeFailure):
        p.parse_stream(raw)


def test_missing_grant_refuses_before_credentials_or_output(packet, monkeypatch):
    base, root, now = packet
    (base / "execution-authorization.json").unlink()
    with pytest.raises(p.Refused, match="DIRECT_EXECUTION_AUTHORITY_REQUIRED"):
        p.gate(base, root, now=now)


def test_expired_prices_and_changed_grant_rejected(packet):
    base, root, now = packet
    with pytest.raises(p.Refused, match="PRICE_WINDOW_EXPIRED"):
        p.gate(base, root, now=now + timedelta(days=2))
    grant = p.parse((base / "execution-authorization.json").read_bytes())
    grant["package_sha256"] = "0" * 64
    (base / "execution-authorization.json").write_text(json.dumps(grant))
    with pytest.raises(p.Refused, match="AUTHORITY_BINDING_CHANGED"):
        p.gate(base, root, now=now)


def test_changed_request_bytes_rejected(packet):
    base, root, _ = packet
    with (base / "S1.json").open("ab") as f:
        f.write(b" ")
    with pytest.raises(p.Refused, match="FROZEN_PACKAGE_CHANGED"):
        p.load_package(base, root)


def test_never_uses_generic_key(tmp_path, monkeypatch):
    monkeypatch.delenv(p.KEY_NAME, raising=False)
    (tmp_path / ".env").write_text(
        "EDUMIND_PROVIDER_API_KEY=do-not-send-this-generic-key\n"
    )
    with pytest.raises(p.Refused, match="DEDICATED_DEEPSEEK_CREDENTIAL_REQUIRED"):
        p.credential(tmp_path)


@pytest.mark.parametrize(
    "mode,expected_calls",
    [
        ("clean", 2),
        ("http", 1),
        ("injection", 1),
        ("cap", 1),
        ("secret_echo", 1),
        ("timeout", 1),
        ("bad_stream", 2),
        ("oversize", 1),
    ],
)
def test_mock_dispatch_stop_accounting_and_no_restart(
    packet, tmp_path, mode, expected_calls
):
    base, root, now = packet
    _, sha, plan, grant = p.gate(base, root, now=now)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "api.deepseek.com"
        assert request.extensions["sni_hostname"] == "api.deepseek.com"
        assert request.headers["authorization"] == "Bearer " + KEY
        body = p.parse(request.content)
        name = "S2" if body["stream"] else "S1"
        r = reply(body, plan["expected"][name])
        if mode == "http":
            return httpx.Response(503, json={"error": "unavailable"})
        if mode == "injection":
            r["instructions"] = "coding assistant"
        if mode == "cap":
            r["usage"] = {"input_tokens": 60, "output_tokens": 129, "total_tokens": 189}
        if mode == "secret_echo":
            r["instructions"] = KEY
        if mode == "timeout":
            raise httpx.ReadTimeout("synthetic fixture")
        if mode == "oversize":
            return httpx.Response(200, content=b"x" * 1048577)
        if body["stream"]:
            raw = stream_bytes(r)
            if mode == "bad_stream":
                raw = raw.split(b"event: response.completed")[0]
            return httpx.Response(
                200, content=raw, headers={"content-type": "text/event-stream"}
            )
        return httpx.Response(200, json=r)

    output = tmp_path / "out"
    runner = p.Runner(base, output, sha, plan, grant, KEY)
    result = asyncio.run(
        runner.execute(lambda: TARGET, lambda: httpx.MockTransport(handler))
    )
    assert len(calls) == expected_calls
    assert result["local_accounting"] == {
        "requests": 2,
        "input_tokens": 8192,
        "output_tokens": 640,
        "fee_micros": 10000,
    }
    assert result["actual_invoice_usd"] is None and result["T038_completed"] is False
    if mode == "clean":
        assert result["state"] == "two_synthetic_observations_only_unsettled"
    else:
        assert result["state"] == "blocked"
    assert KEY.encode() not in (output / "summary.json").read_bytes()
    if mode == "secret_echo":
        assert not (output / "S1-response.bin").exists()
    again = p.Runner(base, output, sha, plan, grant, KEY)
    with pytest.raises(FileExistsError):
        asyncio.run(again.execute(lambda: TARGET, lambda: httpx.MockTransport(handler)))
    assert len(calls) == expected_calls
