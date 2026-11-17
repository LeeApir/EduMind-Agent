"""Isolated HTTP MockTransport only; no keys, DNS, or paid provider calls."""

import asyncio
from copy import deepcopy
import json
import math
import sys

import httpx
import pytest

from scripts.isolated_diagnostics import p15_schema_probe as p
from scripts import run_p15_schema_probe as cli

PACKAGE = "a" * 64
KEY = "synthetic-placeholder-never-a-real-key"


def grant():
    return dict(accepted=True, scope="PHASE-1.5-T074", package_sha256=PACKAGE,
                limits=deepcopy(p.LIMITS), human_message="explicit synthetic fixture approval",
                evidence_ref="offline test only", synthetic_only_accepted=True,
                conditional_second_request_accepted=True, new_window_accepted=True,
                unverified_limits_and_fee_waiver_accepted=True,
                window_started_epoch=999.0, deadline_epoch=1089.0)


def bodies():
    return {n: p.canonical(v) for n, v in p.request_pair().items()}


def response(*, input_tokens=20, output_tokens=8, kind="show_state", **updates):
    value = dict(model="deepseek-flash", status="completed", store=False, error=None,
                 reasoning={"effort": "none"},
                 usage=dict(input_tokens=input_tokens, output_tokens=output_tokens,
                            total_tokens=input_tokens + output_tokens),
                 output=[dict(type="message", role="assistant", status="completed",
                              content=[dict(type="output_text", text=json.dumps({"kind": kind}))])])
    value.update(updates)
    return httpx.Response(200, json=value)


def rejected(message=None):
    return httpx.Response(400, json={"error": dict(type="invalid_request_error",
        code="invalid_request_error", message=message or p.MISSING_TYPE_ERROR + " (request_id: synthetic)")})


def execute(tmp_path, replies, *, clock=None, resolver=None):
    seen = []
    def handler(request):
        index = len(seen)
        seen.append(request)
        item = replies[index]
        if callable(item):
            return item(request)
        if isinstance(item, Exception):
            raise item
        return item
    runner = p.Runner(tmp_path / "out", PACKAGE, grant(), bodies(), KEY,
                      clock=clock or (lambda: 1000.0), monotonic=lambda: 500.0)
    result = asyncio.run(runner.run(transport_factory=lambda: httpx.MockTransport(handler),
        resolver=resolver or (lambda *a: ["8.8.8.8"])))
    return runner, result, seen


def events(output):
    return [json.loads(x.read_text()) for x in sorted(output.glob("event-*.json"))]


def rehash(rows):
    previous = None
    for index, row in enumerate(rows):
        row.update(seq=index, previous=previous)
        row.pop("digest", None)
        row["digest"] = p.sha(p.canonical(row))
        previous = row["digest"]
    return rows


def test_pair_has_exactly_one_typed_discriminator_difference():
    pair = p.request_pair()
    typed = deepcopy(pair["S1"])
    assert typed["text"]["format"]["schema"]["properties"]["kind"] == {
        "type": "string", "enum": ["show_state", "highlight_code", "advance_step"]}
    del typed["text"]["format"]["schema"]["properties"]["kind"]["type"]
    assert typed == pair["S2"]
    assert all(len(raw) <= 1024 for raw in bodies().values())
    assert pair["S1"]["max_output_tokens"] == pair["S2"]["max_output_tokens"] == 32


def test_positive_control_then_matching_schema_400(tmp_path):
    runner, result, seen = execute(tmp_path, [response(), rejected()])
    assert len(seen) == result["dispatch_markers"] == 2
    assert result["outcome"] == "minimal_enum_rejection_observed"
    assert result["unknown_protocol_or_usage"] == 1
    assert result["course_feasibility_authorized"] is False
    assert result["full_original_schema_compatibility_verified"] is False
    for index, name in enumerate(("S1", "S2")):
        assert seen[index].content == (runner.output / f"{name}-request.json").read_bytes() == bodies()[name]
        assert seen[index].headers["Host"] == "api.deepseek.com"
        assert seen[index].extensions["sni_hostname"] == "api.deepseek.com"
        assert seen[index].url.host == "8.8.8.8"
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in runner.output.iterdir())
    assert KEY not in "".join(x.read_text() for x in runner.output.iterdir())


def test_both_success_does_not_reproduce_enum_rejection(tmp_path):
    _, result, seen = execute(tmp_path, [response(), response()])
    assert len(seen) == 2
    assert result["outcome"] == "minimal_enum_rejection_not_reproduced"
    assert result["actual_invoice"] is None
    assert result["unknown_protocol_or_usage"] == 0


def test_mock_receipts_cannot_be_accepted_as_real(tmp_path):
    runner, result, _ = execute(tmp_path, [response(), rejected()])
    assert result["transport_kinds"] == {"mock": 2}
    with pytest.raises(p.Refused, match="MOCK_NOT_REAL_EVIDENCE"):
        p.verify_results(runner.output, PACKAGE, grant(), bodies(), require_real=True)


@pytest.mark.parametrize("first", [rejected(), httpx.Response(401), httpx.Response(429),
    httpx.Response(302, headers={"Location": "https://example.com/"}),
    httpx.Response(500), httpx.ConnectError("synthetic"), httpx.ReadTimeout("synthetic"),
    response(kind="highlight_code"), response(input_tokens=4097), response(output_tokens=33),
    response(model="other"), response(usage=None), response(status="incomplete"),
    response(output=[{"type": "function_call"}]),
    httpx.Response(200, content=b"x" * 65537),
    httpx.Response(200, content=KEY.encode())])
def test_control_failure_never_sends_second_or_retries(tmp_path, first):
    _, result, seen = execute(tmp_path, [first])
    assert len(seen) == 1
    assert result["outcome"] == "inconclusive_stopped"
    assert result["requests_reserved"] == 1
    assert result["unused_requests_not_inherited"] == 1


@pytest.mark.parametrize("second", [rejected("unrelated invalid schema"), httpx.Response(503),
                                    httpx.ReadTimeout("synthetic"), response(kind="advance_step")])
def test_other_second_failure_is_inconclusive_and_terminal(tmp_path, second):
    runner, result, seen = execute(tmp_path, [response(), second])
    assert len(seen) == 2 and result["outcome"] == "inconclusive_stopped"
    with pytest.raises(p.Refused, match="POST_STOP"):
        runner.record("reserved", dict(name="S2", request_sha256=p.sha(bodies()["S2"])))


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_nonpublic_dns_rejected_before_dispatch(tmp_path, address):
    _, result, seen = execute(tmp_path, [], resolver=lambda *a: [address])
    assert not seen and result["dispatch_markers"] == 0
    assert result["requests_reserved"] == 1


@pytest.mark.parametrize("flag", ["accepted", "synthetic_only_accepted",
    "conditional_second_request_accepted", "new_window_accepted",
    "unverified_limits_and_fee_waiver_accepted"])
def test_all_exact_new_approval_flags_required(flag):
    g = grant()
    g[flag] = False
    with pytest.raises(p.Refused, match="EXACT_NEW_APPROVAL_REQUIRED"):
        p.check_grant(g, PACKAGE, now=1000.0)


@pytest.mark.parametrize("field,value", [("deadline_epoch", 1090), ("deadline_epoch", math.nan),
    ("window_started_epoch", True), ("deadline_epoch", math.inf)])
def test_grant_clock_rejects_invalid_windows(field, value):
    g = grant()
    g[field] = value
    with pytest.raises(p.Refused, match="WINDOW"):
        p.check_grant(g, PACKAGE, now=1000)


@pytest.mark.parametrize("now", [998.0, 1089.0, 1090.0, math.nan])
def test_expired_or_future_authority_never_starts(now):
    with pytest.raises(p.Refused, match="WINDOW"):
        p.check_grant(grant(), PACKAGE, now=now)


def test_existing_directory_cannot_restart(tmp_path):
    execute(tmp_path, [rejected()])
    with pytest.raises(FileExistsError):
        execute(tmp_path, [])


@pytest.mark.parametrize("late", [1089.0, 998.0, math.nan])
def test_invalid_response_receipt_clock_cannot_advance(tmp_path, late):
    wall = [1000.0]
    def delayed(request):
        wall[0] = late
        return response()
    _, result, seen = execute(tmp_path, [delayed], clock=lambda: wall[0])
    assert len(seen) == 1 and result["outcome"] == "inconclusive_stopped"
    assert result["observations"] == {}


def test_late_terminal_does_not_credit_pair_success(tmp_path, monkeypatch):
    wall = [1000.0]
    original = p.success_observation
    count = [0]
    def validate(body, raw):
        obs = original(body, raw)
        count[0] += 1
        if count[0] == 2:
            wall[0] = 1089.0
        return obs
    monkeypatch.setattr(p, "success_observation", validate)
    _, result, seen = execute(tmp_path, [response(), response()], clock=lambda: wall[0])
    assert len(seen) == 2 and result["outcome"] == "inconclusive_stopped"


@pytest.mark.parametrize("attack", ["remove_control", "late_control", "post_stop", "duplicate_sent"])
def test_rehashed_trace_still_enforces_control_window_stop_and_unique_dispatch(tmp_path, attack):
    runner, _, _ = execute(tmp_path, [response(), rejected()])
    rows = events(runner.output)
    if attack == "remove_control":
        rows = [r for r in rows if r["kind"] != "control_validated"]
    elif attack == "late_control":
        next(r for r in rows if r["kind"] == "control_validated")["epoch"] = 1089.0
    elif attack == "post_stop":
        rows.insert(5, deepcopy(rows[-1]))
    else:
        index = next(i for i, r in enumerate(rows) if r["kind"] == "sent")
        rows.insert(index + 1, deepcopy(rows[index]))
    with pytest.raises(p.Refused):
        p.replay(rehash(rows), PACKAGE, grant(), bodies())


def test_tampered_response_is_rejected(tmp_path):
    runner, _, _ = execute(tmp_path, [response(), rejected()])
    (runner.output / "S1-response.bin").write_bytes(b"{}")
    with pytest.raises(p.Refused, match="RESULT_RESPONSE_DRIFT"):
        p.verify_results(runner.output, PACKAGE, grant(), bodies())


@pytest.mark.parametrize("attack", ["summary", "permissions", "symlink"])
def test_saved_summary_and_private_file_guards(tmp_path, attack):
    runner, _, _ = execute(tmp_path, [response(), rejected()])
    if attack == "summary":
        (runner.output / "summary.json").write_text("{}")
    elif attack == "permissions":
        (runner.output / "S1-response.bin").chmod(0o644)
    else:
        victim = runner.output / "S1-response.bin"
        victim.unlink()
        victim.symlink_to(runner.output / "S2-response.bin")
    with pytest.raises(p.Refused):
        p.verify_results(runner.output, PACKAGE, grant(), bodies())


def test_pending_cli_refuses_before_key_output_or_runner(tmp_path, monkeypatch):
    g = grant()
    g["accepted"] = False
    (tmp_path / "execution-approval.json").write_text(json.dumps(g))
    def forbidden(*a, **k):
        raise AssertionError("credential or real runner reached")
    monkeypatch.setattr(cli, "BASE", tmp_path)
    monkeypatch.setattr(cli, "OUTPUT", tmp_path / "never-created")
    monkeypatch.setattr(cli, "load_package", lambda: (PACKAGE, bodies()))
    monkeypatch.setattr(cli, "credential", forbidden)
    monkeypatch.setattr(sys, "argv", ["probe", "--run"])
    assert cli.main() == 2
    assert not cli.OUTPUT.exists()


def test_pair_uses_one_dns_result_and_same_ip(tmp_path):
    calls = []
    def resolver(*args):
        calls.append(args)
        return ["8.8.8.8"]
    _, result, seen = execute(tmp_path, [response(), rejected()], resolver=resolver)
    assert len(calls) == 1 and len(seen) == 2
    assert seen[0].url == seen[1].url
    assert result["outcome"] == "minimal_enum_rejection_observed"


@pytest.mark.parametrize("case", ["valid", "timeout", "oversize", "bad_json", "private"])
def test_dns_only_child_is_bounded_credential_free_and_reaped(monkeypatch, case):
    class FakeProcess:
        returncode = None
        killed = False
        sent = False
        stdout = None
        def __init__(self):
            self.stdout = self
        async def read(self, maximum):
            if self.sent:
                return b""
            self.sent = True
            if case == "timeout":
                raise TimeoutError("synthetic")
            if case == "oversize":
                return b"x" * 16385
            if case == "bad_json":
                return b"invalid"
            return b'["10.0.0.1"]' if case == "private" else b'["8.8.8.8"]'
        async def wait(self):
            self.returncode = -9 if self.killed else 0
            return self.returncode
        def kill(self):
            self.killed = True
    process = FakeProcess()
    async def spawn(*args, **kwargs):
        assert kwargs["env"] == {} and "api.deepseek.com" in args[-1]
        assert KEY not in repr((args, kwargs))
        assert args[1:3] == ("-I", "-c")
        return process
    monkeypatch.setattr(p.asyncio, "create_subprocess_exec", spawn)
    if case == "valid":
        target = asyncio.run(p.bounded_target(9.0, None))
        assert target.connect_ip == "8.8.8.8" and process.returncode == 0
    else:
        with pytest.raises((ValueError, TimeoutError)):
            asyncio.run(p.bounded_target(9.0, None))
        assert process.returncode is not None
        if case in ("timeout", "oversize"):
            assert process.killed is True


@pytest.mark.parametrize("field,value", [("scope", "PHASE-1.5-T069"),
    ("package_sha256", "b" * 64), ("limits", {}), ("evidence_ref", None),
    ("human_message", "")])
def test_old_scope_altered_limits_or_missing_approval_evidence_refused(field, value):
    g = grant()
    g[field] = value
    with pytest.raises(p.Refused, match="EXACT_NEW_APPROVAL_REQUIRED"):
        p.check_grant(g, PACKAGE, now=1000)


@pytest.mark.parametrize("attack", ["false_status", "missing_second_observed", "late_terminal",
                                     "unknown_outcome", "changed_target"])
def test_more_rehashed_terminal_and_response_causality_attacks(tmp_path, attack):
    runner, _, _ = execute(tmp_path, [response(), rejected()])
    rows = events(runner.output)
    if attack == "false_status":
        next(r for r in rows if r["kind"] == "observed")["data"]["status"] = 400
    elif attack == "missing_second_observed":
        rows = [r for r in rows if not (r["kind"] == "observed" and r["data"]["name"] == "S2")]
    elif attack == "late_terminal":
        rows[-1]["epoch"] = 1089.0
    elif attack == "unknown_outcome":
        rows[-1]["data"]["outcome"] = "invented_success"
    else:
        pins = [r for r in rows if r["kind"] == "target_pinned"]
        pins[1]["data"]["addresses"] = ["1.1.1.1"]
    rows = rehash(rows)
    if attack == "missing_second_observed":
        for path in runner.output.glob("event-*.json"):
            path.unlink()
        for i, row in enumerate(rows):
            path = runner.output / f"event-{i:03}.json"
            path.write_bytes(p.canonical(row))
            path.chmod(0o600)
        with pytest.raises(p.Refused, match="COMPLETE_PAIR_REQUIRED"):
            p.verify_results(runner.output, PACKAGE, grant(), bodies())
    else:
        with pytest.raises(p.Refused):
            p.replay(rows, PACKAGE, grant(), bodies())
