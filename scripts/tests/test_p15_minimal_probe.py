"""Seven-slot protocol admission, budgets and authority: Mock-only, no real DNS or keys."""

import asyncio
from copy import deepcopy
import json
import math
import socket

import httpx
import pytest

from scripts import run_p15_minimal_probe as cli
from scripts.isolated_diagnostics import p15_minimal_probe_contract as c
from scripts.isolated_diagnostics import p15_minimal_probe as p

PACKAGE = "c" * 64
KEYS = dict(
    generation="synthetic-generation-key-only", review="synthetic-review-key-only"
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Live DNS/network forbidden in this regression")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def grant():
    return dict(
        accepted=True,
        scope="PHASE-1.5-T085",
        package_sha256=PACKAGE,
        limits=deepcopy(c.LIMITS),
        human_message="synthetic authority only",
        evidence_ref="test only",
        fee_exception_human_message="接受本批费用例外并执行",
        **{k: True for k in p.FLAGS},
        window_started_epoch=999.0,
        deadline_epoch=1899.0,
    )


def response(name):
    body = json.loads(c.bodies()[name])
    role = c.ROLES[name]
    return dict(
        model=p.wire.ROUTES[role]["model"],
        status="completed",
        store=False,
        error=None,
        reasoning=dict(effort=p.wire.ROUTES[role]["reasoning"]),
        text=dict(format=deepcopy(body["text"]["format"])),
        usage=dict(
            input_tokens=100,
            output_tokens=60,
            total_tokens=160,
            output_tokens_details=dict(reasoning_tokens=5 if role == "review" else 0),
        ),
        output=[
            dict(
                id="synthetic",
                type="message",
                role="assistant",
                status="completed",
                phase="final_answer",
                content=[dict(type="output_text", text=json.dumps(c.FIXTURES[name]))],
            )
        ],
    )


def execute(tmp_path, fail_at=None, attack=None, clock=None):
    seen = []
    dns = []

    def handler(request):
        index = len(seen)
        seen.append(request)
        name = c.ORDER[index]
        value = response(name)
        if index == fail_at:
            if attack == "http":
                return httpx.Response(400, json=dict(error="synthetic"))
            if attack == "timeout":
                raise httpx.ReadTimeout("synthetic")
            if attack == "redirect":
                return httpx.Response(302, headers={"Location": "https://example.com"})
            if attack == "echo_absent":
                value.pop("text")
            elif attack == "echo_wrong":
                value["text"]["format"]["schema"] = {}
            elif attack == "echo_name":
                value["text"]["format"]["name"] = "foreign"
            elif attack == "model":
                value["model"] = "foreign"
            elif attack == "phase":
                value["output"][0]["phase"] = "commentary"
            elif attack == "usage":
                value["usage"] = None
            elif attack in ("input", "output"):
                dimension = attack + "_tokens"
                value["usage"][dimension] = (
                    c.CAPS[name][0 if attack == "input" else 1] + 1
                )
                value["usage"]["total_tokens"] = (
                    value["usage"]["input_tokens"] + value["usage"]["output_tokens"]
                )
            elif attack == "fixture":
                value["output"][0]["content"][0]["text"] = "{}"
            elif attack == "secret":
                value["extra"] = KEYS["generation"]
            elif callable(attack):
                attack(value)
        return httpx.Response(200, json=value)

    def resolver(host, port):
        dns.append(host)
        return ["1.1.1.1" if host == "aiapi.world" else "8.8.8.8"]

    runner = p.Runner(
        tmp_path / "out",
        PACKAGE,
        grant(),
        KEYS,
        clock=clock or (lambda: 1000.0),
        monotonic=lambda: 500.0,
    )
    result = asyncio.run(
        runner.run(
            transport_factory=lambda: httpx.MockTransport(handler), resolver=resolver
        )
    )
    return runner, result, seen, dns


def test_all_seven_pass_exact_bytes_pinned_transport_and_no_course(tmp_path):
    runner, result, seen, dns = execute(tmp_path)
    assert result["admitted_roles"] == result["dispatch_markers"] == 7
    assert result["protocol_admission_complete"]
    assert result["transport_kinds"] == {"mock": 7}
    assert dns == ["api.deepseek.com", "aiapi.world"]
    assert not result["course_requests_authorized"] and not result["teaching_evaluated"]
    for name, request in zip(c.ORDER, seen):
        assert request.content == c.bodies()[name]
        host = "aiapi.world" if c.ROLES[name] == "review" else "api.deepseek.com"
        assert request.headers["Host"] == request.extensions["sni_hostname"] == host
        assert request.headers["Authorization"] == "Bearer " + KEYS[c.ROLES[name]]
    with pytest.raises(p.Refused, match="MOCK_NOT_REAL"):
        p.verify_results(runner.output, PACKAGE, grant())


@pytest.mark.parametrize("index", range(7))
@pytest.mark.parametrize(
    "attack",
    [
        "http",
        "timeout",
        "redirect",
        "echo_absent",
        "echo_wrong",
        "echo_name",
        "model",
        "phase",
        "usage",
        "input",
        "output",
        "fixture",
        "secret",
    ],
)
def test_every_slot_failure_stops_and_preserves_remaining(tmp_path, index, attack):
    runner, result, seen, _ = execute(tmp_path, index, attack)
    assert len(seen) == index + 1
    assert result["admitted_roles"] == index
    assert result["outcome"] == "inconclusive_stopped"
    assert result["unrun_roles"] == 6 - index
    assert result["unknown_protocol_or_usage"] == 1
    assert not (runner.output / f"S{index + 2}-request.json").exists()


@pytest.mark.parametrize("flag", ["accepted", *p.FLAGS, "fee_exception_human_message"])
def test_each_approval_and_fee_condition_required(flag):
    g = grant()
    g[flag] = False
    with pytest.raises(p.Refused):
        p.check_grant(g, PACKAGE, now=1000)


@pytest.mark.parametrize(
    "update",
    [
        dict(scope="PHASE-1.5-T078"),
        dict(scope="PHASE-1.5-T083"),
        dict(package_sha256="b" * 64),
        dict(limits={}),
        dict(deadline_epoch=1898),
        dict(deadline_epoch=math.nan),
        dict(window_started_epoch=True),
    ],
)
def test_old_scope_budget_window_cannot_be_reused(update):
    g = grant()
    g.update(update)
    with pytest.raises(p.Refused):
        p.check_grant(g, PACKAGE, now=1000)


def test_cli_pending_fee_fails_before_keys_or_output(monkeypatch, tmp_path, capsys):
    g = grant()
    g["unverified_limits_and_fee_waiver_accepted"] = False
    (tmp_path / "execution-approval.json").write_text(json.dumps(g))
    monkeypatch.setattr(cli, "BASE", tmp_path)
    monkeypatch.setattr(cli, "OUTPUT", tmp_path / "out")
    monkeypatch.setattr(cli, "load_package", lambda: (PACKAGE, c.bodies()))
    monkeypatch.setattr(
        cli, "credential", lambda: pytest.fail("No key read before fee approval")
    )
    monkeypatch.setattr("sys.argv", ["probe", "--run"])
    assert cli.main() == 2
    assert not (tmp_path / "out").exists()
    assert "APPROVAL_REQUIRED" in capsys.readouterr().out


def test_known_review_metadata_bounded_and_quarantined():
    name = "S6"
    body = json.loads(c.bodies()[name])
    value = response(name)
    value["instructions"] = body["input"][0]["content"] + p.wire.SUFFIX
    turn = "11111111-2222-3333-4444-555555555555"
    value["output"].insert(
        0,
        dict(
            type="reasoning",
            summary=[dict(type="summary_text", text="synthetic")],
            metadata=dict(turn_id=turn),
            internal_chat_message_metadata_passthrough=dict(turn_id=turn),
        ),
    )
    obs = p.observe(name, body, p.canonical(value))
    assert (
        obs["known_suffix_observed"]
        and obs["summary_quarantined"]
        and obs["opaque_turn_metadata_quarantined"]
    )
    assert (
        not obs["opaque_identity_verified"]
        and not obs["provider_schema_enforcement_verified"]
    )
    value["output"][0]["summary"][0]["text"] = "x" * 4097
    with pytest.raises(ValueError):
        p.observe(name, body, p.canonical(value))


@pytest.mark.parametrize(
    "attack",
    ["remove_validation", "after_stop", "late", "changed_ip", "duplicate_send"],
)
def test_rehashed_event_attacks_still_fail(tmp_path, attack):
    runner, _, _, _ = execute(tmp_path)
    rows = [
        json.loads(f.read_bytes()) for f in sorted(runner.output.glob("event-*.json"))
    ]
    if attack == "remove_validation":
        rows = [
            r
            for r in rows
            if not (r["kind"] == "validated" and r["data"]["name"] == "S1")
        ]
    elif attack == "after_stop":
        rows.append(deepcopy(rows[1]))
    elif attack == "late":
        next(r for r in rows if r["kind"] == "validated")["epoch"] = 1899
    elif attack == "changed_ip":
        [r for r in rows if r["kind"] == "target_pinned"][1]["data"]["addresses"] = [
            "1.1.1.1"
        ]
    else:
        i = next(i for i, r in enumerate(rows) if r["kind"] == "sent")
        rows.insert(i + 1, deepcopy(rows[i]))
    previous = None
    for i, row in enumerate(rows):
        row.update(seq=i, previous=previous)
        row.pop("digest", None)
        row["digest"] = p.sha(p.canonical(row))
        previous = row["digest"]
    with pytest.raises(p.Refused):
        p.replay(rows, PACKAGE, grant(), c.bodies())


def test_readonly_tamper_and_no_restart(tmp_path):
    runner, _, _, _ = execute(tmp_path)
    with pytest.raises(FileExistsError):
        asyncio.run(runner.run())
    (runner.output / "S7-response.bin").write_text("{}")
    with pytest.raises(p.Refused):
        p.verify_results(runner.output, PACKAGE, grant(), require_real=False)


def test_symlink_parent_refused_without_writes(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    runner = p.Runner(
        link / "out", PACKAGE, grant(), KEYS, clock=lambda: 1000, monotonic=lambda: 500
    )
    with pytest.raises(p.Refused, match="SYMLINK"):
        asyncio.run(runner.run())
    assert list(real.iterdir()) == []


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_ssrf_refused_before_http(tmp_path, address):
    runner = p.Runner(
        tmp_path / "out",
        PACKAGE,
        grant(),
        KEYS,
        clock=lambda: 1000,
        monotonic=lambda: 500,
    )

    def denied():
        pytest.fail("No transport before public target")

    result = asyncio.run(
        runner.run(transport_factory=denied, resolver=lambda *a: [address])
    )
    assert result["dispatch_markers"] == 0 and not result["protocol_admission_complete"]


@pytest.mark.parametrize("late", [1899.0, 998.0, math.nan])
def test_late_rollback_nonfinite_cannot_validate_or_advance(tmp_path, late):
    wall = [1000.0]

    def delayed(value):
        wall[0] = late

    _, result, seen, _ = execute(tmp_path, 0, delayed, clock=lambda: wall[0])
    assert (
        len(seen) == 1
        and result["admitted_roles"] == 0
        and result["outcome"] == "inconclusive_stopped"
    )
