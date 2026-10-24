"""Exact two-call discovery execution behind injected Mock and synthetic approvals."""

import asyncio
import hashlib
import json
import shutil
import socket
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import run_p15_compatibility_probe as probe  # noqa: E402

from acceptance_support.p15_diagnostic_ledger import Refused  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402


@pytest.fixture(autouse=True)
def no_network_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No real network or credentials")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.name != ".env"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)


def setup_packet(tmp_path):
    base = tmp_path / "package"
    base.mkdir()
    shutil.copyfile(probe.BASE / "request.json", base / "request.json")
    manifest = dict(
        batch_id=probe.BATCH,
        purpose=probe.PURPOSE,
        limits=asdict(probe.LIMITS),
        sha256={
            "package/request.json": hashlib.sha256(
                (base / "request.json").read_bytes()
            ).hexdigest()
        },
    )
    (base / "manifest.json").write_text(json.dumps(manifest))
    package = hashlib.sha256((base / "manifest.json").read_bytes()).hexdigest()
    for kind in ("contract", "execution"):
        grant = dict(
            kind=kind,
            scope="PHASE-1.5-T038",
            purpose=probe.PURPOSE,
            batch_id=probe.BATCH,
            package_sha256=package,
            limits=asdict(probe.LIMITS),
            human_message="SYNTHETIC TEST ONLY",
            reviewer="test",
            received_at="test",
            evidence_ref="offline test",
            decisions=["A", "B", "C"],
            fee_cap_waiver=True,
            unverified_upstream_bounds_risk_accepted=True,
            no_course_admission=True,
        )
        (base / (kind + "-approval.json")).write_text(json.dumps(grant))
    return base, probe.gate(base, tmp_path)


@pytest.mark.parametrize(
    "mode",
    [
        "clean",
        "injected",
        "count_mismatch",
        "cap_null",
        "over_output",
        "wrong_schema",
        "count_http",
        "key_echo",
        "timeout",
    ],
)
def test_single_probe_all_outcomes_terminal(tmp_path, mode):
    base, (manifest, package, grants) = setup_packet(tmp_path)
    seen = []

    def handler(request):
        seen.append(request)
        body = json.loads(request.content)
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(
                503 if mode == "count_http" else 200,
                json={"object": "response.input_tokens", "input_tokens": 100},
            )
        if mode == "timeout":
            raise httpx.ReadTimeout("TEST_SECRET")
        result = dict(
            model="gpt-6-luna",
            status="completed",
            error=None,
            instructions="\n\n".join(
                m["content"] for m in body["input"] if m["role"] == "system"
            ),
            max_output_tokens=16,
            text=body["text"],
            usage=dict(
                input_tokens=101 if mode == "count_mismatch" else 100,
                output_tokens=17 if mode == "over_output" else 8,
            ),
            output=[
                dict(
                    type="message",
                    role="assistant",
                    content=[
                        dict(
                            type="output_text",
                            text=json.dumps(
                                {"result": "BAD" if mode == "wrong_schema" else "OK"}
                            ),
                        )
                    ],
                )
            ],
        )
        if mode == "injected":
            result["instructions"] += "\nUNAPPROVED"
        if mode == "cap_null":
            result["max_output_tokens"] = None
        if mode == "key_echo":
            result["instructions"] += "TEST_SECRET"
        return httpx.Response(200, json=result)

    settings = SimpleNamespace(api_key="TEST_SECRET")
    target = ApprovedTarget(
        "https://www.cbbb.fun/v1", "www.cbbb.fun", 443, ("8.8.8.8",)
    )
    output = tmp_path / "run"
    result = asyncio.run(
        probe.run(
            base,
            output,
            manifest,
            package,
            grants,
            settings,
            target,
            httpx.MockTransport(handler),
        )
    )
    assert len(seen) == (1 if mode == "count_http" else 2)
    if len(seen) == 2:
        assert seen[0].content == seen[1].content
    assert not result["course_admitted"] and not result["T038_completed"]
    assert result["http_dispatch_markers"] == len(seen)
    assert result["model_dispatch_markers"] == (0 if mode == "count_http" else 1)
    if mode in {
        "injected",
        "count_mismatch",
        "cap_null",
        "over_output",
        "wrong_schema",
    }:
        assert result["provider_reported_usage"]["input_tokens"] in (100, 101)
        assert result["verified_protocol_usage"] is None
    assert (
        result["actual_relay_fee"] is None
        and not result["upstream_hard_bounds_independently_verified"]
    )
    if mode == "clean":
        assert result["verdict"] == "no_observed_contract_violation_not_admitted"
        assert result["usage"]["input_tokens"] == 100
    else:
        assert result["verdict"] == "contract_failure_or_unknown_not_admitted"
        assert result["usage"]["input_tokens"] == 32000
        assert result["usage"]["output_tokens"] == 16
    with sqlite3.connect(output / "ledger.sqlite") as db:
        assert db.execute("SELECT state FROM batches").fetchone()[0] == "stopped"
    assert "TEST_SECRET" not in "".join(p.read_text() for p in output.rglob("*.json"))
    with pytest.raises(FileExistsError):
        asyncio.run(
            probe.run(
                base,
                output,
                manifest,
                package,
                grants,
                settings,
                target,
                httpx.MockTransport(handler),
            )
        )
    assert len(seen) == (1 if mode == "count_http" else 2)


@pytest.mark.parametrize(
    "change",
    ["no_contract", "no_execution", "old_grant", "no_fee", "no_risk", "tamper"],
)
def test_accurate_dual_gate(tmp_path, change):
    base, _ = setup_packet(tmp_path)
    if change.startswith("no_") and change in {"no_contract", "no_execution"}:
        (base / (change[3:] + "-approval.json")).unlink()
    elif change == "tamper":
        (base / "request.json").write_text("{}")
    else:
        path = base / "execution-approval.json"
        grant = json.loads(path.read_text())
        if change == "old_grant":
            grant["batch_id"] = "p15-development-r03"
        if change == "no_fee":
            grant["fee_cap_waiver"] = False
        if change == "no_risk":
            grant["unverified_upstream_bounds_risk_accepted"] = False
        path.write_text(json.dumps(grant))
    with pytest.raises(Refused):
        probe.gate(base, tmp_path)
    assert not (tmp_path / "run").exists()


def test_real_main_missing_approval_has_no_side_effects(monkeypatch, tmp_path):
    base, _ = setup_packet(tmp_path)
    (base / "contract-approval.json").unlink()
    (base / "execution-approval.json").unlink()
    actual_gate = probe.gate
    monkeypatch.setattr(probe, "gate", lambda: actual_gate(base, tmp_path))
    monkeypatch.setattr(probe, "OUTPUT", tmp_path / "not_started")
    monkeypatch.setattr(sys, "argv", ["probe", "--execute"])
    with pytest.raises(Refused, match="APPROVALS_REQUIRED"):
        probe.main()
    assert not probe.OUTPUT.exists()
