"""Offline synthetic compatibility, authorization and failure containment regression."""

import asyncio
import copy
import hashlib
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
import run_p15_candidate_compatibility as probe  # noqa: E402
from acceptance_support.p15_candidate_compatibility import Runner, parse, response_value  # noqa: E402
from acceptance_support.p15_diagnostic_ledger import Refused  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402

KEY = "synthetic-only-secret-00000000"
TARGET = ApprovedTarget(
    "https://api.openai.com/v1", "api.openai.com", 443, ("8.8.8.8",)
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No real sockets or DNS")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.name != ".env"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)


@pytest.fixture
def packet(tmp_path):
    base = tmp_path / "packet"
    shutil.copytree(probe.BASE, base)
    manifest = json.loads((base / "manifest.json").read_bytes())
    manifest["sha256"] = {
        str(p.relative_to(tmp_path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [base / "pricing.json", *(base / "probes").glob("*.json")]
    }
    (base / "manifest.json").write_text(json.dumps(manifest))
    package = hashlib.sha256((base / "manifest.json").read_bytes()).hexdigest()
    for kind in ("contract", "execution"):
        grant = json.loads((base / "approval-template.json").read_bytes())
        grant.update(
            status="SYNTHETIC_OFFLINE_FIXTURE",
            kind=kind,
            package_sha256=package,
            human_message="SYNTHETIC TEST ONLY",
            reviewer="fixture",
            received_at="fixture",
            evidence_ref="OFFLINE_TEST_NOT_AUTHORITY",
        )
        (base / (kind + "-approval.json")).write_text(json.dumps(grant))
    now = datetime.fromisoformat(
        json.loads((base / "pricing.json").read_bytes())["checked_at"]
    ) + timedelta(seconds=1)
    return base, probe.gate(base, tmp_path, now=now)


def reply(body, expected):
    return dict(
        object="response",
        model="gpt-6-luna",
        status="completed",
        error=None,
        service_tier="default",
        reasoning={"effort": "none"},
        store=False,
        tools=[],
        usage=dict(input_tokens=37, output_tokens=4, total_tokens=41),
        instructions=body.get("instructions"),
        max_output_tokens=body["max_output_tokens"],
        text=body["text"],
        output=[
            dict(type="reasoning", summary=[]),
            dict(
                type="message",
                role="assistant",
                status="completed",
                content=[
                    dict(
                        type="output_text",
                        text=json.dumps(expected, ensure_ascii=False),
                    )
                ],
            ),
        ],
    )


def run_packet(packet, tmp_path, mode="clean", *, clock=None):
    base, (manifest, package, grants) = packet
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "api.openai.com"
        assert request.extensions["sni_hostname"] == "api.openai.com"
        body = json.loads(request.content)
        is_count = request.url.path.endswith("/input_tokens")
        if mode == "timeout":
            raise httpx.ReadTimeout("arbitrary unsafe error " + KEY)
        if mode == "count_http" and is_count:
            return httpx.Response(429, json={"error": "rate limit"})
        if mode == "redirect":
            return httpx.Response(307, headers={"location": "https://evil.invalid/"})
        if is_count:
            return httpx.Response(
                200,
                json={
                    "object": "response.input_tokens",
                    "input_tokens": 5000 if mode == "count_over" else 37,
                },
            )
        case = next(
            c for c in manifest["cases"] if c["output_max"] == body["max_output_tokens"]
        )
        data = reply(body, case["expected"])
        if mode == "count_mismatch":
            data["usage"].update(input_tokens=38, total_tokens=42)
        elif mode == "cap_null":
            data["max_output_tokens"] = None
        elif mode == "wrong_model":
            data["model"] = "gpt-6-luna-unapproved-snapshot"
        elif mode == "wrong_tier":
            data["service_tier"] = "fast"
        elif mode == "injected":
            data["instructions"] = "extra system text"
        elif mode == "overflow":
            data["usage"].update(output_tokens=1000, total_tokens=1037)
        elif mode == "schema":
            data["output"][1]["content"][0]["text"] = '{"result":"NO"}'
        elif mode == "key_echo":
            data["leak"] = KEY
        elif mode == "large":
            return httpx.Response(200, content=b" " * 2097153)
        elif mode == "duplicate":
            return httpx.Response(200, content=b'{"object":1,"object":2}')
        elif mode == "s2_instruction_null" and case["id"] == "S2":
            data["instructions"] = None
        elif mode == "s2_mismatch" and case["id"] == "S2":
            data["usage"].update(input_tokens=38, total_tokens=42)
        elif mode == "elapsed":
            clock[0] += 91
        return httpx.Response(200, json=data)

    runner = Runner(
        base,
        tmp_path / "output",
        manifest,
        package,
        grants[1],
        probe.LIMITS,
        KEY,
        clock=(lambda: (clock[0], clock[0])) if clock else None,
        contract=grants[0],
    )
    result = asyncio.run(
        runner.execute(lambda: TARGET, lambda: httpx.MockTransport(handler))
    )
    return result, calls, runner


@pytest.mark.parametrize(
    "mode,expected_http",
    [
        ("clean", 4),
        ("count_http", 1),
        ("redirect", 1),
        ("count_over", 1),
        ("timeout", 1),
        ("count_mismatch", 2),
        ("cap_null", 2),
        ("wrong_model", 2),
        ("wrong_tier", 2),
        ("injected", 2),
        ("overflow", 2),
        ("schema", 2),
        ("key_echo", 2),
        ("large", 2),
        ("duplicate", 2),
        ("s2_instruction_null", 4),
        ("s2_mismatch", 4),
    ],
)
def test_sequential_failure_and_preserved_budget(packet, tmp_path, mode, expected_http):
    result, calls, runner = run_packet(packet, tmp_path, mode)
    assert len(calls) == result["http_dispatch_markers"] == expected_http
    assert (
        result["course_generation_authorized"] is False
        and result["T038_completed"] is False
    )
    assert result["actual_invoice_usd"] is None
    assert result["local_accounting"]["fee_micros"] <= 20000
    assert result["status"] == (
        "minimal_compatibility_observed_pass" if mode == "clean" else "blocked"
    )
    if mode == "clean":
        assert result["verified_cases"] == ["S1", "S2"]
        assert (
            calls[0].content == calls[1].content
            and calls[2].content == calls[3].content
        )
        assert result["local_accounting"]["fee_micros"] == 2 * (4096 + 37 + 4)
    elif expected_http <= 2:
        assert result["case_states"]["S2"] == "unrun"
        assert result["local_accounting"]["input_tokens"] == 4096
        assert result["local_accounting"]["output_tokens"] == 16
        assert result["local_accounting"]["fee_micros"] == 8208
    all_bytes = b"".join(p.read_bytes() for p in runner.output.iterdir() if p.is_file())
    assert KEY.encode() not in all_bytes
    with pytest.raises(FileExistsError):
        asyncio.run(
            runner.execute(lambda: TARGET, lambda: pytest.fail("No restart transport"))
        )


def test_deadline_blocks_s2(packet, tmp_path):
    result, calls, _ = run_packet(packet, tmp_path, "elapsed", clock=[1000])
    assert result["status"] == "blocked" and len(calls) == 2
    assert result["verified_cases"] == []


@pytest.mark.parametrize(
    "mutation",
    [
        "total",
        "negative",
        "bool",
        "refusal",
        "tool",
        "strict",
        "store",
        "reasoning",
        "details",
        "wrong_expected",
    ],
)
def test_full_response_validation(packet, mutation):
    base, (manifest, _, _) = packet
    case = manifest["cases"][0]
    body = json.loads((base / case["body"]).read_bytes())
    data = reply(body, case["expected"])
    if mutation == "total":
        data["usage"]["total_tokens"] = 42
    if mutation == "negative":
        data["usage"]["output_tokens"] = -1
    if mutation == "bool":
        data["usage"]["input_tokens"] = True
    if mutation == "refusal":
        data["output"][1]["content"] = [{"type": "refusal", "refusal": "no"}]
    if mutation == "tool":
        data["output"].append({"type": "function_call"})
    if mutation == "strict":
        data["text"] = copy.deepcopy(body["text"])
        data["text"]["format"]["strict"] = False
    if mutation == "store":
        data["store"] = True
    if mutation == "reasoning":
        data["reasoning"] = {"effort": "high"}
    if mutation == "details":
        data["usage"]["output_tokens_details"] = {"reasoning_tokens": 5}
    if mutation == "wrong_expected":
        case["expected"] = {"result": "NO"}
    with pytest.raises(ValueError):
        response_value(body, data, 37, case["expected"], manifest["candidate"])


@pytest.mark.parametrize(
    "raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b"not json", b"\xff"]
)
def test_ambiguous_json_rejected(raw):
    with pytest.raises(ValueError):
        parse(raw)


def test_split_output_and_s1_null_are_legal(packet):
    base, (manifest, _, _) = packet
    case = manifest["cases"][0]
    body = json.loads((base / case["body"]).read_bytes())
    data = reply(body, case["expected"])
    data["output"][1]["content"] = [
        {"type": "output_text", "text": '{"result":'},
        {"type": "output_text", "text": '"OK"}'},
    ]
    assert response_value(body, data, 37, case["expected"], manifest["candidate"]) == (
        37,
        4,
    )


@pytest.mark.parametrize(
    "change",
    ["missing", "old_package", "old_batch", "unlimited", "no_risk", "no_contract"],
)
def test_approval_rejections_before_key_dns_output(
    packet, tmp_path, monkeypatch, change
):
    base, _ = packet
    path = base / "execution-approval.json"
    grant = json.loads(path.read_bytes())
    if change == "missing":
        path.unlink()
    else:
        if change == "old_package":
            grant["package_sha256"] = "0" * 64
        if change == "old_batch":
            grant["batch_id"] = "p15-compatibility-probe-p01"
        if change == "unlimited":
            grant["fee_cap_waiver"] = True
        if change == "no_risk":
            grant["count_fee_allowance_and_invoice_uncertainty_accepted"] = False
        if change == "no_contract":
            (base / "contract-approval.json").unlink()
        path.write_text(json.dumps(grant))
    monkeypatch.setattr(
        probe.os.environ, "get", lambda *a: pytest.fail("Key read before approval")
    )
    with pytest.raises(Refused):
        probe.execute(base, tmp_path, tmp_path / "forbidden-output")
    assert not (tmp_path / "forbidden-output").exists()


def test_price_expiration_and_immutability(packet, tmp_path):
    base, _ = packet
    price = json.loads((base / "pricing.json").read_bytes())
    with pytest.raises(Refused):
        probe.gate(base, tmp_path, now=datetime.fromisoformat(price["expires_at"]))
    (base / "probes/S1.json").write_text("{}")
    with pytest.raises(Refused):
        probe.load_package(base, tmp_path)


def test_missing_dedicated_key_does_not_inherit_provider_key(
    packet, tmp_path, monkeypatch
):
    base, _ = packet
    monkeypatch.delenv("EDUMIND_COMPAT_API_KEY", raising=False)
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", KEY)
    with pytest.raises(Refused, match="DEDICATED_OFFICIAL_CREDENTIAL_REQUIRED"):
        probe.execute(base, tmp_path, tmp_path / "forbidden-output")
    assert not (tmp_path / "forbidden-output").exists()


def test_evidence_failure_stops_before_second_pair(packet, tmp_path, monkeypatch):
    import acceptance_support.p15_candidate_compatibility as impl

    original = impl.evidence

    def fail(path, value):
        if path.name == "S1-model-response.json":
            raise OSError("disk full " + KEY)
        return original(path, value)

    monkeypatch.setattr(impl, "evidence", fail)
    result, calls, _ = run_packet(packet, tmp_path)
    assert result["status"] == "blocked" and len(calls) == 2
    assert result["local_accounting"]["fee_micros"] == 8208


def test_bounded_dns_uses_no_credential_environment(monkeypatch):
    from types import SimpleNamespace

    def child(args, **kwargs):
        assert args[-2:] == ["api.openai.com", "443"]
        assert kwargs["env"] == {} and kwargs["timeout"] == 5
        assert kwargs["capture_output"] and kwargs["check"]
        return SimpleNamespace(stdout=b'["8.8.8.8"]')

    monkeypatch.setattr(probe.subprocess, "run", child)
    assert probe.bounded_resolver("api.openai.com", 443) == ["8.8.8.8"]


def test_dns_failure_is_terminal_without_transport(packet, tmp_path):
    base, (manifest, package, grants) = packet

    def fail():
        raise TimeoutError("DNS timeout synthetic")

    runner = Runner(
        base,
        tmp_path / "dns-output",
        manifest,
        package,
        grants[1],
        probe.LIMITS,
        KEY,
        contract=grants[0],
    )
    result = asyncio.run(
        runner.execute(fail, lambda: pytest.fail("Transport after DNS failure"))
    )
    assert result["status"] == "blocked" and result["http_dispatch_markers"] == 0
    assert result["local_accounting"]["fee_micros"] == 0


def test_readonly_check_has_no_key_dns_or_output(packet, tmp_path, monkeypatch):
    base, _ = packet
    monkeypatch.setattr(
        probe.os.environ, "get", lambda *a: pytest.fail("check reads key")
    )
    (base / "contract-approval.json").unlink()
    (base / "execution-approval.json").unlink()
    probe.load_package(base, tmp_path)
    assert not (tmp_path / "output").exists()


def test_cancellation_retains_unknown_and_does_not_dispatch_s2(packet, tmp_path):
    base, (manifest, package, grants) = packet
    seen = []

    def cancel(request):
        seen.append(request)
        raise asyncio.CancelledError()

    runner = Runner(
        base,
        tmp_path / "cancel-output",
        manifest,
        package,
        grants[1],
        probe.LIMITS,
        KEY,
        contract=grants[0],
    )
    result = asyncio.run(
        runner.execute(lambda: TARGET, lambda: httpx.MockTransport(cancel))
    )
    assert len(seen) == 1 and result["status"] == "blocked"
    assert result["local_accounting"]["fee_micros"] == 8208
    assert result["case_states"]["S2"] == "unrun"
