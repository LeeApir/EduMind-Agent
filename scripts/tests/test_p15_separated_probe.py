"""Actual separated controller under HTTP MockTransport; R0 never auto-succeeds."""

import asyncio
from copy import deepcopy
import json
import math
import socket

import httpx
import pytest

from scripts import run_p15_separated_probe as cli
from scripts.isolated_diagnostics import p15_separated_probe as p
from scripts.isolated_diagnostics import p15_separated_probe_contract as c

PACKAGE = "e" * 64
KEYS = {"generation": "synthetic-dedicated-generation-key"}
REPAIRS = json.loads((c.DESIGN / "repair-output-examples.json").read_bytes())[
    "examples"
]
BAD_TEXT = (c.DESIGN / "fixtures/t085-s5-output-text.txt").read_bytes().decode()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("No real DNS/network allowed")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def grant():
    return dict(
        accepted=True,
        scope="PHASE-1.5-T088",
        package_sha256=PACKAGE,
        limits=deepcopy(c.LIMITS),
        human_message="test-only authorization",
        evidence_ref="synthetic fixture",
        fee_exception_human_message="test-only new exact fee exception",
        **{k: True for k in p.FLAGS},
        window_started_epoch=999.0,
        deadline_epoch=1899.0,
    )


def payload(name):
    return json.loads(json.loads(c.bodies()[name])["input"][1]["content"])


def reply(name, repair=0):
    body = json.loads(c.bodies()[name])
    value = deepcopy(
        REPAIRS[repair]["value"] if name == "R0" else payload(name)["expected_output"]
    )
    return dict(
        model="deepseek-flash",
        status="completed",
        store=False,
        error=None,
        reasoning={"effort": "none"},
        text={"format": deepcopy(body["text"]["format"])},
        usage=dict(
            input_tokens=100,
            output_tokens=80,
            total_tokens=180,
            output_tokens_details={"reasoning_tokens": 0},
        ),
        output=[
            dict(
                type="message",
                id="synthetic",
                role="assistant",
                status="completed",
                phase="final_answer",
                content=[
                    dict(type="output_text", text=json.dumps(value, ensure_ascii=False))
                ],
            )
        ],
    )


def execute(
    tmp_path, *, repair=0, fail_at=None, attack=None, clock=None, resolver=None
):
    seen = []
    dns = []

    def handler(request):
        i = len(seen)
        name = c.ORDER[i]
        seen.append(request)
        value = reply(name, repair)
        if i == fail_at:
            if attack == "http":
                return httpx.Response(400, json={"error": "synthetic"})
            if attack == "timeout":
                raise httpx.ReadTimeout("synthetic")
            if attack == "redirect":
                return httpx.Response(302, headers={"Location": "https://example.com"})
            if attack == "malformed":
                value["output"][0]["content"][0]["text"] = BAD_TEXT
            elif attack == "schema":
                value["output"][0]["content"][0]["text"] = json.dumps(
                    json.loads(c.bodies()[name])["text"]["format"]["schema"]
                )
            elif attack == "extra_field":
                v = json.loads(value["output"][0]["content"][0]["text"])
                v["unexpected"] = True
                value["output"][0]["content"][0]["text"] = json.dumps(v)
            elif attack == "duplicate":
                value["output"][0]["content"][0]["text"] = '{"x":1,"x":2}'
            elif attack == "model":
                value["model"] = "foreign"
            elif attack == "echo_absent":
                value.pop("text")
            elif attack == "echo_wrong":
                value["text"]["format"]["schema"] = {}
            elif attack == "phase":
                value["output"][0]["phase"] = "commentary"
            elif attack == "usage":
                value["usage"] = None
            elif attack in ("input", "output"):
                value["usage"][attack + "_tokens"] = 8193 if attack == "input" else 4097
                value["usage"]["total_tokens"] = (
                    value["usage"]["input_tokens"] + value["usage"]["output_tokens"]
                )
            elif attack == "wrong_target":
                v = json.loads(value["output"][0]["content"][0]["text"])
                v["paragraphs"][0]["text"] = "Different but schema-valid."
                value["output"][0]["content"][0]["text"] = json.dumps(v)
            elif attack == "secret":
                value["extra"] = KEYS["generation"]
            elif callable(attack):
                attack(value)
        return httpx.Response(200, json=value)

    def lookup(host, port):
        dns.append(host)
        return ["8.8.8.8"]

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
            transport_factory=lambda: httpx.MockTransport(handler),
            resolver=resolver or lookup,
        )
    )
    return runner, result, seen, dns


def rehash(rows):
    previous = None
    for i, row in enumerate(rows):
        row.update(seq=i, previous=previous)
        row.pop("digest", None)
        row["digest"] = p.sha(p.canonical(row))
        previous = row["digest"]
    return rows


@pytest.mark.parametrize(
    "repair",
    [0, 1, 2],
    ids=["different_good_a", "different_good_b", "false_prose_not_auto_certified"],
)
def test_whole_actual_controller_R0_ends_only_pending_semantic_review(tmp_path, repair):
    runner, result, seen, dns = execute(tmp_path, repair=repair)
    assert [json.loads(r.content)["input"] for r in seen] == [
        json.loads(c.bodies()[n])["input"] for n in c.ORDER
    ]
    assert result["network_phase_complete"] is True
    assert result["repair_status"] == "pending_independent_semantic_review"
    assert result["repair_success"] is result["diagnostic_success"] is False
    assert result["independent_semantic_review_pending"] is True
    assert result["validated_samples"] == len(seen) == 7
    assert (
        result["full_role_admission_complete"] is result["teaching_evaluated"] is False
    )
    assert dns == ["api.deepseek.com"]
    assert result["transport_kinds"] == {"mock": 7}
    assert cli.result_exit_code(result) == 3
    for name, observation in result["observations"].items():
        assert (
            observation["repair_success"] is False
            and observation["semantic_evaluated"] is False
        )
        if name == "R0":
            assert observation["fixed_echo_verified"] is False
            assert observation["sample_status"] == "pending_independent_semantic_review"
        else:
            assert observation["fixed_echo_verified"] is True
    readonly = p.verify_results(runner.output, PACKAGE, grant(), require_real=False)
    assert readonly == result
    with pytest.raises(p.Refused, match="MOCK_NOT_REAL"):
        p.verify_results(runner.output, PACKAGE, grant())


@pytest.mark.parametrize(
    "repair", [3, 4], ids=["unauthorized_answer_change", "no_repair"]
)
def test_R0_mechanical_failures_stop_without_retry_or_success(tmp_path, repair):
    _, result, seen, _ = execute(tmp_path, repair=repair)
    assert len(seen) == 7 and result["validated_samples"] == 6
    assert result["outcome"] == "inconclusive_stopped"
    assert result["repair_status"] == "not_mechanically_accepted"
    assert result["repair_success"] is False and cli.result_exit_code(result) == 2


@pytest.mark.parametrize("index", range(7))
@pytest.mark.parametrize(
    "attack",
    [
        "http",
        "timeout",
        "redirect",
        "malformed",
        "schema",
        "duplicate",
        "extra_field",
        "model",
        "echo_absent",
        "echo_wrong",
        "phase",
        "usage",
        "input",
        "output",
        "secret",
    ],
)
def test_every_slot_and_actual_postcondition_failure_stops_global_batch(
    tmp_path, index, attack
):
    runner, result, seen, _ = execute(tmp_path, fail_at=index, attack=attack)
    assert len(seen) == index + 1
    assert result["validated_samples"] == index
    assert result["unrun_samples"] == 6 - index
    assert (
        result["outcome"] == "inconclusive_stopped"
        and result["repair_success"] is False
    )
    if index < 6:
        assert not (runner.output / (c.ORDER[index + 1] + "-request.json")).exists()


@pytest.mark.parametrize("index", range(6))
def test_P_W_actual_controller_still_requires_exact_echo_not_just_schema(
    tmp_path, index
):
    _, result, seen, _ = execute(tmp_path, fail_at=index, attack="wrong_target")
    assert len(seen) == index + 1 and result["validated_samples"] == index
    assert result["outcome"] == "inconclusive_stopped"


def test_R0_is_not_sent_expected_output_and_two_valid_wordings_are_not_exact_matches(
    tmp_path,
):
    runner, result, seen, _ = execute(tmp_path, repair=1)
    given = json.loads(json.loads(seen[-1].content)["input"][1]["content"])
    assert "expected_output" not in given
    assert REPAIRS[0]["value"] != REPAIRS[1]["value"]
    assert result["observations"]["R0"]["output_digest"] != c.local.digest(
        REPAIRS[0]["value"]
    )


@pytest.mark.parametrize(
    "field",
    [
        "repair_success",
        "sample_status",
        "fixed_echo_verified",
        "semantic_evaluated",
        "changed_paths",
    ],
)
def test_rehashed_receipt_cannot_promote_R0_to_success_or_echo(tmp_path, field):
    runner, _, _, _ = execute(tmp_path)
    rows = [
        json.loads(f.read_bytes()) for f in sorted(runner.output.glob("event-*.json"))
    ]
    record = next(
        r for r in rows if r["kind"] == "validated" and r["data"]["name"] == "R0"
    )
    record["data"]["observation"][field] = {
        "repair_success": True,
        "sample_status": "repaired_successfully",
        "fixed_echo_verified": True,
        "semantic_evaluated": True,
        "changed_paths": [],
    }[field]
    with pytest.raises(p.Refused):
        p.replay(rehash(rows), PACKAGE, grant(), c.bodies())


def test_summary_repair_success_tamper_is_rejected(tmp_path):
    runner, result, _, _ = execute(tmp_path)
    result["repair_success"] = True
    (runner.output / "summary.json").write_bytes(p.canonical(result))
    with pytest.raises(p.Refused, match="SUMMARY_DRIFT"):
        p.verify_results(runner.output, PACKAGE, grant(), require_real=False)
    with pytest.raises(p.Refused, match="NO_AUTOMATIC_REPAIR_SUCCESS"):
        cli.result_exit_code(result)


@pytest.mark.parametrize(
    "attack",
    [
        "missing_validated",
        "reordered",
        "after_stop",
        "late",
        "duplicate_sent",
        "changed_ip",
        "wrong_terminal",
    ],
)
def test_rehashed_reducer_attacks_still_require_order_time_and_pending_terminal(
    tmp_path, attack
):
    runner, _, _, _ = execute(tmp_path)
    rows = [
        json.loads(f.read_bytes()) for f in sorted(runner.output.glob("event-*.json"))
    ]
    if attack == "missing_validated":
        rows = [
            r
            for r in rows
            if not (r["kind"] == "validated" and r["data"]["name"] == "P0")
        ]
    elif attack == "reordered":
        next(r for r in rows if r["kind"] == "reserved")["data"]["name"] = "W0"
    elif attack == "after_stop":
        rows.append(deepcopy(rows[1]))
    elif attack == "late":
        next(r for r in rows if r["kind"] == "validated")["epoch"] = 1899
    elif attack == "duplicate_sent":
        i = next(i for i, r in enumerate(rows) if r["kind"] == "sent")
        rows.insert(i + 1, deepcopy(rows[i]))
    elif attack == "changed_ip":
        [r for r in rows if r["kind"] == "target_pinned"][1]["data"]["addresses"] = [
            "1.1.1.1"
        ]
    else:
        rows[-1]["data"]["outcome"] = "repair_success"
    with pytest.raises(p.Refused):
        p.replay(rehash(rows), PACKAGE, grant(), c.bodies())


@pytest.mark.parametrize("flag", ["accepted", *p.FLAGS, "fee_exception_human_message"])
def test_each_new_scope_fee_and_pending_semantic_ack_required(flag):
    value = grant()
    value[flag] = False
    with pytest.raises(p.Refused):
        p.check_grant(value, PACKAGE, now=1000)


@pytest.mark.parametrize(
    "scope", ["PHASE-1.5-T085", "PHASE-1.5-T086", "PHASE-1.5-T087"]
)
def test_previous_authority_cannot_start_new_batch(scope):
    value = grant()
    value["scope"] = scope
    with pytest.raises(p.Refused):
        p.check_grant(value, PACKAGE, now=1000)


@pytest.mark.parametrize("late", [1899.0, 998.0, math.nan])
def test_late_or_clock_rollback_cannot_advance(tmp_path, late):
    wall = [1000.0]

    def change_clock(value):
        wall[0] = late

    _, result, seen, _ = execute(
        tmp_path, fail_at=0, attack=change_clock, clock=lambda: wall[0]
    )
    assert (
        len(seen) == 1
        and result["validated_samples"] == 0
        and result["outcome"] == "inconclusive_stopped"
    )


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_nonpublic_DNS_rejected_before_send(tmp_path, ip):
    _, result, seen, _ = execute(tmp_path, resolver=lambda *args: [ip])
    assert seen == [] and result["dispatch_markers"] == 0


def test_pending_cli_refuses_before_key_DNS_and_output(tmp_path, monkeypatch, capsys):
    g = grant()
    g["accepted"] = False
    (tmp_path / "execution-approval.json").write_text(json.dumps(g))
    monkeypatch.setattr(cli, "BASE", tmp_path)
    monkeypatch.setattr(cli, "OUTPUT", tmp_path / "out")
    monkeypatch.setattr(cli, "load_package", lambda: (PACKAGE, c.bodies()))
    monkeypatch.setattr(
        cli, "credential", lambda: pytest.fail("No key before exact execution approval")
    )
    monkeypatch.setattr("sys.argv", ["probe", "--run"])
    assert cli.main() == 2 and not (tmp_path / "out").exists()
    assert "APPROVAL_REQUIRED" in capsys.readouterr().out


def test_changed_body_or_R0_repaired_text_is_not_misused_as_fixed_echo():
    body = json.loads(c.bodies()["R0"])
    body["input"][1]["content"] = "{}"
    with pytest.raises(c.local.ContractError, match="REQUEST_BODY_DRIFT"):
        c.validate_task("R0", REPAIRS[0]["value"], body)


def test_no_restart_or_post_terminal_send(tmp_path):
    runner, result, seen, _ = execute(tmp_path)
    before = {f.name: p.sha(f.read_bytes()) for f in runner.output.iterdir()}
    with pytest.raises(FileExistsError):
        asyncio.run(runner.run())
    assert before == {f.name: p.sha(f.read_bytes()) for f in runner.output.iterdir()}


@pytest.mark.parametrize("field", ["code", "question", "answer", "node", "paragraphs"])
def test_R0_cannot_change_other_protected_values_even_with_good_wording(
    tmp_path, field
):
    def change(value):
        candidate = json.loads(value["output"][0]["content"][0]["text"])
        if field == "code":
            candidate["code"] += "\n"
        elif field == "question":
            candidate["questions"]["caller_head"]["explanation"] = (
                "Different explanation."
            )
        elif field == "answer":
            candidate["answers"]["reachable_prefix"] = [9]
        elif field == "node":
            candidate["actions"]["states"][-1]["nodes"][0]["data"] = 8
        else:
            candidate["paragraphs"].append(
                {"key": "extra", "text": "Additional prose."}
            )
        value["output"][0]["content"][0]["text"] = json.dumps(candidate)

    _, result, seen, _ = execute(tmp_path, fail_at=6, attack=change)
    assert len(seen) == 7 and result["validated_samples"] == 6
    assert (
        result["repair_status"] == "not_mechanically_accepted"
        and result["repair_success"] is False
    )


def test_cli_readonly_pending_review_is_exit3_and_never_loads_keys(
    tmp_path, monkeypatch, capsys
):
    runner, result, _, _ = execute(tmp_path)
    (tmp_path / "execution-approval.json").write_text(json.dumps(grant()))
    original = p.verify_results
    # Test-only Mock reader; real CLI keeps require_real=True and rejects Mock artifacts.
    monkeypatch.setattr(
        p,
        "verify_results",
        lambda output, package, g: original(output, package, g, require_real=False),
    )
    monkeypatch.setattr(cli, "BASE", tmp_path)
    monkeypatch.setattr(cli, "OUTPUT", runner.output)
    monkeypatch.setattr(cli, "load_package", lambda: (PACKAGE, c.bodies()))
    monkeypatch.setattr(
        cli, "credential", lambda: pytest.fail("Readonly never loads credentials")
    )
    monkeypatch.setattr("sys.argv", ["probe", "--check-results"])
    assert cli.main() == 3
    printed = json.loads(capsys.readouterr().out)
    assert printed["repair_status"] == "pending_independent_semantic_review"
    assert printed["repair_success"] is False and printed["transport_kinds"] == {
        "mock": 7
    }
