"""Single R0 actual controller with MockTransport; no live requests or semantic pass."""

import asyncio
from copy import deepcopy
import json
import math
import socket

import httpx
import pytest

from scripts import run_p15_r0_once as cli
from scripts.isolated_diagnostics import p15_r0_once as p
from scripts.isolated_diagnostics import p15_r0_once_contract as c
from scripts.tests import test_p15_separated_probe as fixtures

PACKAGE = "f" * 64


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("No real DNS/network")
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def grant():
    return dict(
        accepted=True, scope="PHASE-1.5-T090", package_sha256=PACKAGE,
        limits=deepcopy(c.LIMITS), human_message="test-only standalone R0",
        evidence_ref="synthetic fixture", fee_exception_human_message="test-only fresh fee risk",
        window_started_epoch=999.0, deadline_epoch=1119.0,
        **{n: True for n in p.FLAGS},
    )


def execute(tmp_path, repair=0, attack=None, clock=None, ip="8.8.8.8"):
    seen = []
    def handler(request):
        seen.append(request)
        value = fixtures.reply("R0", repair)
        if attack == "http":
            return httpx.Response(400, json={"error": "synthetic"})
        if attack == "timeout":
            raise httpx.ReadTimeout("synthetic")
        if attack == "redirect":
            return httpx.Response(302, headers={"Location": "https://example.com"})
        if attack == "malformed":
            value["output"][0]["content"][0]["text"] = fixtures.BAD_TEXT
        elif attack == "schema":
            value["output"][0]["content"][0]["text"] = json.dumps(json.loads(c.bodies()["R0"])["text"]["format"]["schema"])
        elif attack == "extra":
            v = json.loads(value["output"][0]["content"][0]["text"])
            v["unknown"] = True
            value["output"][0]["content"][0]["text"] = json.dumps(v)
        elif attack == "duplicate":
            value["output"][0]["content"][0]["text"] = '{"x":1,"x":2}'
        elif attack == "model":
            value["model"] = "foreign"
        elif attack == "schema_echo":
            value.pop("text")
        elif attack == "reasoning":
            value["reasoning"]["effort"] = "low"
        elif attack == "phase":
            value["output"][0]["phase"] = "commentary"
        elif attack == "input":
            value["usage"]["input_tokens"] = 8193
            value["usage"]["total_tokens"] = 8273
        elif attack == "output":
            value["usage"]["output_tokens"] = 4097
            value["usage"]["total_tokens"] = 4197
        elif attack == "secret":
            value["output"][0]["content"][0]["text"] = fixtures.KEYS["generation"]
        elif callable(attack):
            attack(value)
        return httpx.Response(200, content=json.dumps(value).encode())
    r = p.Runner(tmp_path / "out", PACKAGE, grant(), fixtures.KEYS,
                 clock=clock or (lambda: 1000.0), monotonic=lambda: 0.0)
    result = asyncio.run(r.run(transport_factory=lambda: httpx.MockTransport(handler),
                              resolver=lambda *args: [ip]))
    return r, result, seen


@pytest.mark.parametrize("repair", [0, 1, 2], ids=["good_a", "good_b", "false_prose_pending"])
def test_only_R0_sent_and_mechanical_success_is_only_pending(tmp_path, repair):
    r, result, seen = execute(tmp_path, repair)
    assert len(seen) == 1 and seen[0].content == c.bodies()["R0"]
    assert result["planned_samples"] == result["validated_samples"] == 1
    assert result["repair_success"] is result["diagnostic_success"] is False
    assert result["repair_status"] == "pending_independent_semantic_review"
    assert result["network_phase_complete"] is True and cli.result_exit_code(result) == 3
    assert result == p.verify_results(r.output, PACKAGE, grant(), require_real=False)
    assert c.ORDER == ("R0",) and p.frozen.contract.ORDER == ("P0", "W0", "W1", "W2", "W3", "W4", "R0")
    assert p.observe is p.frozen.observe
    with pytest.raises(p.Refused, match="MOCK_NOT_REAL"):
        p.verify_results(r.output, PACKAGE, grant())


@pytest.mark.parametrize("repair", [3, 4], ids=["unauthorized", "unchanged"])
def test_unacceptable_repair_stops_once(tmp_path, repair):
    _, result, seen = execute(tmp_path, repair)
    assert len(seen) == 1 and result["validated_samples"] == 0
    assert result["outcome"] == "inconclusive_stopped" and cli.result_exit_code(result) == 2


@pytest.mark.parametrize("attack", ["http", "timeout", "redirect", "malformed", "schema", "extra", "duplicate", "model", "schema_echo", "reasoning", "phase", "input", "output", "secret"])
def test_protocol_failure_has_no_retry_or_followup(tmp_path, attack):
    _, result, seen = execute(tmp_path, attack=attack)
    assert len(seen) == 1 and result["validated_samples"] == 0
    assert result["repair_success"] is False and result["outcome"] == "inconclusive_stopped"
    assert result["requests_reserved"] == result["dispatch_markers"] == 1


@pytest.mark.parametrize("field", ["accepted", *p.FLAGS, "fee_exception_human_message"])
def test_all_fresh_approval_and_fee_ack_required(field):
    g = grant()
    g[field] = False
    with pytest.raises(p.Refused, match="APPROVAL_REQUIRED"):
        p.check_grant(g, PACKAGE, now=1000.0)


@pytest.mark.parametrize("scope", ["PHASE-1.5-T088", "PHASE-1.5-T089", "PHASE-1.5-T085"])
def test_old_scopes_not_inherited(scope):
    g = grant()
    g["scope"] = scope
    with pytest.raises(p.Refused):
        p.check_grant(g, PACKAGE, now=1000.0)


@pytest.mark.parametrize("now", [998.0, 1119.0, math.nan])
def test_expired_or_invalid_clock_refused(now):
    with pytest.raises(p.Refused):
        p.check_grant(grant(), PACKAGE, now=now)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_public_target_required_before_send(tmp_path, ip):
    _, result, seen = execute(tmp_path, ip=ip)
    assert not seen and result["dispatch_markers"] == 0


def test_terminal_and_receipts_cannot_promote_success_or_add_second_send(tmp_path):
    r, result, seen = execute(tmp_path)
    rows = [json.loads(f.read_bytes()) for f in sorted(r.output.glob("event-*.json"))]
    for field, value in [("sample_status", "repaired_successfully"), ("repair_success", True), ("semantic_evaluated", True), ("fixed_echo_verified", True)]:
        changed = deepcopy(rows)
        next(x for x in changed if x["kind"] == "validated")["data"]["observation"][field] = value
        with pytest.raises(p.Refused):
            p.replay(fixtures.rehash(changed), PACKAGE, grant(), c.bodies())
    changed = deepcopy(rows)
    changed.append(deepcopy(rows[1]))
    with pytest.raises(p.Refused):
        p.replay(fixtures.rehash(changed), PACKAGE, grant(), c.bodies())
    result["repair_success"] = True
    with pytest.raises(p.Refused):
        cli.result_exit_code(result)
    before = {f.name: p.sha(f.read_bytes()) for f in r.output.iterdir()}
    with pytest.raises(FileExistsError):
        asyncio.run(r.run())
    assert before == {f.name: p.sha(f.read_bytes()) for f in r.output.iterdir()}


def test_late_result_stops_and_never_becomes_success(tmp_path):
    calls = [0]
    def clock():
        calls[0] += 1
        return 1120.0 if calls[0] > 10 else 1000.0
    _, result, _ = execute(tmp_path, clock=clock)
    assert result["network_phase_complete"] is False and result["repair_success"] is False


def test_pending_cli_never_reads_key_or_creates_live_directory(tmp_path, monkeypatch):
    g = grant()
    g["accepted"] = False
    (tmp_path / "execution-approval.json").write_text(json.dumps(g))
    monkeypatch.setattr(cli, "BASE", tmp_path)
    monkeypatch.setattr(cli, "OUTPUT", tmp_path / "out")
    monkeypatch.setattr(cli, "load_package", lambda: (PACKAGE, c.bodies()))
    monkeypatch.setattr(cli, "credential", lambda: pytest.fail("No key before approval"))
    monkeypatch.setattr("sys.argv", ["r0", "--run"])
    assert cli.main() == 2 and not (tmp_path / "out").exists()


def test_cli_readonly_mechanical_acceptance_is_exit3_not_success(tmp_path, monkeypatch, capsys):
    r, result, _ = execute(tmp_path, repair=2)
    (tmp_path / "execution-approval.json").write_text(json.dumps(grant()))
    original = p.verify_results
    # Only this test reader accepts Mock; live CLI retains require_real=True.
    monkeypatch.setattr(p, "verify_results", lambda output, package, g: original(output, package, g, require_real=False))
    monkeypatch.setattr(cli, "BASE", tmp_path)
    monkeypatch.setattr(cli, "OUTPUT", r.output)
    monkeypatch.setattr(cli, "load_package", lambda: (PACKAGE, c.bodies()))
    monkeypatch.setattr(cli, "credential", lambda: pytest.fail("No key in readonly mode"))
    monkeypatch.setattr("sys.argv", ["r0", "--check-results"])
    assert cli.main() == 3
    printed = json.loads(capsys.readouterr().out)
    assert printed == result and printed["repair_success"] is False


def test_summary_promotion_and_old_900s_window_rejected(tmp_path):
    r, result, _ = execute(tmp_path)
    result["repair_success"] = True
    (r.output / "summary.json").write_bytes(p.canonical(result))
    with pytest.raises(p.Refused, match="SUMMARY_DRIFT"):
        p.verify_results(r.output, PACKAGE, grant(), require_real=False)
    g = grant()
    g["deadline_epoch"] = 1899.0
    with pytest.raises(p.Refused, match="WINDOW_INVALID"):
        p.check_grant(g, PACKAGE, now=1000.0)
