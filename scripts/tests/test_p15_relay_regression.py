"""Current relay fault regression: no live credentials, DNS or sockets."""

import asyncio
import hashlib
import json
import shutil
import socket
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import run_p15_relay_regression as probe  # noqa: E402
from acceptance_support.p15_diagnostic_ledger import Refused  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402

KEY = "synthetic-relay-key-only-000000"
TARGET = ApprovedTarget("https://www.cbbb.fun/v1", "www.cbbb.fun", 443, ("8.8.8.8",))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No real DNS or sockets")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.resolve() != ROOT / ".env"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)


@pytest.fixture
def packet(tmp_path):
    base = tmp_path / "packet"
    shutil.copytree(probe.BASE, base)
    manifest = json.loads((base / "manifest.json").read_bytes())
    manifest["sha256"] = {
        "packet/request.json": hashlib.sha256(
            (base / "request.json").read_bytes()
        ).hexdigest()
    }
    (base / "manifest.json").write_text(json.dumps(manifest))
    package = hashlib.sha256((base / "manifest.json").read_bytes()).hexdigest()
    for kind in ("contract", "execution"):
        grant = json.loads((base / "approval-template.json").read_bytes())
        grant.update(
            status="SYNTHETIC_OFFLINE_ONLY",
            kind=kind,
            package_sha256=package,
            human_message="SYNTHETIC TEST ONLY",
            reviewer="fixture",
            received_at="fixture",
            evidence_ref="OFFLINE_TEST_NOT_AUTHORITY",
        )
        (base / (kind + "-approval.json")).write_text(json.dumps(grant))
    return base, probe.gate(base, tmp_path)


@pytest.mark.parametrize(
    "mode,calls_max",
    [
        ("clean", 2),
        ("old_usage", 2),
        ("old_suffix", 2),
        ("old_cap_null", 2),
        ("schema", 2),
        ("count_http", 1),
        ("redirect", 1),
        ("timeout", 1),
        ("secret_echo", 2),
        ("count_over", 1),
    ],
)
def test_one_pair_then_terminal(packet, tmp_path, mode, calls_max):
    base, (manifest, package, grants) = packet
    calls = []

    def handler(request):
        calls.append(request)
        assert (
            request.url.host == "8.8.8.8" and request.headers["host"] == "www.cbbb.fun"
        )
        assert request.extensions["sni_hostname"] == "www.cbbb.fun"
        if mode == "timeout":
            raise httpx.ReadTimeout("unsafe " + KEY)
        if mode == "redirect":
            return httpx.Response(
                307, headers={"location": "https://elsewhere.invalid"}
            )
        if request.url.path.endswith("/input_tokens"):
            if mode == "count_http":
                return httpx.Response(404, json={"error": "unsupported"})
            return httpx.Response(
                200,
                json={
                    "object": "response.input_tokens",
                    "input_tokens": 9000 if mode == "count_over" else 37,
                },
            )
        body = json.loads(request.content)
        data = dict(
            object="response",
            model="gpt-6-luna",
            status="completed",
            error=None,
            service_tier="default",
            reasoning={"effort": "none"},
            store=False,
            usage=dict(input_tokens=37, output_tokens=13, total_tokens=50),
            instructions=None,
            max_output_tokens=16,
            text=body["text"],
            output=[
                dict(
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[dict(type="output_text", text='{"result":"OK"}')],
                )
            ],
        )
        if mode == "old_usage":
            data["usage"].update(input_tokens=4438, total_tokens=4451)
        if mode == "old_suffix":
            data["instructions"] = "unrequested coding assistant instructions"
        if mode == "old_cap_null":
            data["max_output_tokens"] = None
        if mode == "schema":
            data["output"][0]["content"][0]["text"] = '{"result":"NO"}'
        if mode == "secret_echo":
            data["secret"] = KEY
        return httpx.Response(200, json=data)

    output = tmp_path / "output"
    result = asyncio.run(
        probe.run(
            base,
            output,
            manifest,
            package,
            grants,
            KEY,
            lambda: TARGET,
            lambda: httpx.MockTransport(handler),
        )
    )
    assert len(calls) == result["http_dispatch_markers"] == calls_max
    assert result["outcome"] == (
        "original_fault_not_observed_one_case_only"
        if mode == "clean"
        else "candidate_rejected_stop_using"
    )
    assert result["actual_vendor_currency"] is None and result["actual_invoice"] is None
    assert result["local_fee_units_are_unvalidated_planning_allowance"] is True
    assert (
        not result["course_diagnostic_preparation_unlocked"]
        and not result["further_calls_authorized"]
    )
    summary = json.loads((output / "summary.json").read_bytes())
    if mode != "clean":
        assert summary["local_accounting"]["fee_micros"] == 8208
    if mode == "clean":
        assert calls[0].content == calls[1].content
    assert KEY.encode() not in b"".join(
        p.read_bytes() for p in output.iterdir() if p.is_file()
    )
    with pytest.raises(FileExistsError):
        asyncio.run(
            probe.run(
                base,
                output,
                manifest,
                package,
                grants,
                KEY,
                lambda: pytest.fail("No restart"),
                lambda: pytest.fail("No restart"),
            )
        )


@pytest.mark.parametrize(
    "change", ["missing", "official", "no_risk", "no_path", "no_discard", "no_contract"]
)
def test_gate_precedes_env_and_dns(packet, tmp_path, monkeypatch, change):
    base, _ = packet
    path = base / "execution-approval.json"
    grant = json.loads(path.read_bytes())
    if change == "missing":
        path.unlink()
    else:
        if change == "official":
            grant["batch_id"] = "p15-candidate-compat-r01"
        if change == "no_risk":
            grant["unknown_vendor_currency_and_rates_accepted"] = False
        if change == "no_path":
            grant["root_to_v1_mapping_accepted"] = False
        if change == "no_discard":
            grant["fail_then_discard_no_retry"] = False
        if change == "no_contract":
            (base / "contract-approval.json").unlink()
        path.write_text(json.dumps(grant))
    monkeypatch.setattr(
        probe,
        "credential_after_approval",
        lambda *a: pytest.fail("Env read before approval"),
    )
    with pytest.raises(Refused):
        probe.execute(base, tmp_path, tmp_path / "forbidden")
    assert not (tmp_path / "forbidden").exists()


@pytest.mark.parametrize(
    "mode",
    ["valid", "wrong_host", "wrong_model", "duplicate", "invalid_quote", "empty_key"],
)
def test_frozen_dotenv_identity_and_no_shell_evaluation(tmp_path, monkeypatch, mode):
    url = (
        "https://www.cbbb.fun" if mode != "wrong_host" else "https://api.openai.com/v1"
    )
    model = "gpt-6-luna" if mode != "wrong_model" else "other-model"
    key = KEY if mode != "empty_key" else ""
    raw = f"EDUMIND_PROVIDER_BASE_URL={url}\nEDUMIND_PROVIDER_MODEL={model}\nEDUMIND_PROVIDER_STRUCTURED_TRANSPORT=responses_json_schema\nEDUMIND_PROVIDER_API_KEY={key}\n"
    if mode == "duplicate":
        raw += "EDUMIND_PROVIDER_API_KEY=ambiguous\n"
    if mode == "invalid_quote":
        raw = raw.replace("KEY=" + key, 'KEY="' + key)
    (tmp_path / ".env").write_text(raw)
    monkeypatch.setenv("EDUMIND_PROVIDER_BASE_URL", "https://wrong.invalid")
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "WRONG_PROCESS_KEY")
    if mode == "valid":
        assert probe.credential_after_approval(tmp_path) == KEY
    else:
        with pytest.raises(Refused) as exc:
            probe.credential_after_approval(tmp_path)
        assert KEY not in str(exc.value)


def test_frozen_original_request_and_readonly_check(packet, tmp_path, monkeypatch):
    base, _ = packet
    monkeypatch.setattr(
        probe, "credential_after_approval", lambda *a: pytest.fail("check reads env")
    )
    probe.load_package(base, tmp_path)
    (base / "request.json").write_text("{}")
    with pytest.raises(Refused):
        probe.load_package(base, tmp_path)
