"""Fixed-focus integration with synthetic credentials and intercepted HTTP only."""

import asyncio
import copy
import json
import shutil
import socket
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import prepare_t040_focus as prepare  # noqa: E402
import run_t040_focus as runner  # noqa: E402
from acceptance_support import claim_review_prototype as p  # noqa: E402
from acceptance_support.fixed_focus_gate import FixedFocusGate  # noqa: E402
from acceptance_support.phase1_budget import GateFailure  # noqa: E402


@pytest.fixture
def rig(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Real DNS/socket prohibited")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    old_rel = "docs/acceptance/phase-1-t040-derived-calibration-r09/run-r09.json"
    old = json.loads((REPO / old_rel).read_bytes())
    files = set(old["files"]) | {old_rel}
    files.update(str(f.relative_to(REPO)) for f in (REPO / prepare.SOURCE_REL).glob("*.json"))
    files.update(
        {
            "scripts/prepare_t040_focus.py",
            "scripts/run_t040_focus.py",
            "scripts/acceptance_support/fixed_focus_gate.py",
            "scripts/acceptance_support/span_review_offline.py",
            "backend/tests/test_fixed_focus.py",
            prepare.BASE_REL + "/token-cost-proof.json",
        }
    )
    for name in files:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, dest)
    (tmp_path / ".env").write_text(
        "EDUMIND_PROVIDER_BASE_URL=https://api.deepseek.com\n"
        "EDUMIND_PROVIDER_MODEL=deepseek-flash\n"
        "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT=responses_json_schema\n"
        "EDUMIND_PROVIDER_API_KEY=synthetic-fixture-secret\n"
    )
    base = tmp_path / prepare.BASE_REL
    base.mkdir(parents=True, exist_ok=True)
    data = prepare.build(tmp_path)
    for name, value in data.items():
        (base / name).write_bytes(p.encoded(value))
    m, plan, requests = runner.load(tmp_path)
    record = {
        "version": "fixed-focus-run-approval-v1",
        "root_sha256": p.digest(m),
        "requests": 4,
        "cost_micro_cny": plan["cost_cap_micro_cny"],
        "scope_sha256": plan["scope_sha256"],
        "expires_at": plan["expires_at"],
        "exit_limits": plan["exit_limits"],
        "confirmed_by": "Lee",
        "user_confirmation": "Synthetic test approval; no real authorization",
        "source_message_id": "synthetic-fixture",
        "terms_verified_on": time.strftime("%Y-%m-%d", time.localtime()),
    }
    state = {"sends": [], "edit": None, "record": record}

    def authorize():
        (base / "run-approval.json").write_bytes(p.encoded(state["record"]))
        return runner.approval(tmp_path, m, plan)

    def gate():
        return FixedFocusGate(tmp_path, m, plan, requests, runner.approval(tmp_path, m, plan))

    async def handle(req):
        state["sends"].append(req)
        body = json.loads(req.content)
        payload = json.loads(body["input"][1]["content"])
        number = len(state["sends"])
        defect = number <= 2
        value = {
            "version": "span-focus-review-v1",
            "request_id": payload["request_id"],
            "verdict": "revise" if defect else "pass",
            "findings": [{"area": "fact", "severity": "major", "message": "Synthetic finding"}]
            if defect
            else [],
            "other_findings": [],
            "uncertain": False,
        }
        response = {
            "model": "deepseek-flash",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(value)}],
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
        if state["edit"]:
            state["edit"](response)
        return httpx.Response(200, stream=httpx.ByteStream(p.encoded(response)))

    def step():
        return asyncio.run(
            runner.step(
                tmp_path,
                transport=httpx.MockTransport(handle),
                resolver=lambda host, port: ("8.8.8.8",),
            )
        )

    def evidence(passed=True):
        report = runner.report(tmp_path)
        last = report["attempts"][-1]
        return {
            "root_sha256": report["root_sha256"],
            "number": last["number"],
            "value_hash": last["value_hash"],
            "passed": passed,
            "confirmed_by": "Lee",
            "user_confirmation": "Synthetic fixture fact check",
            "source_message_id": "synthetic-only",
            "observation": "Synthetic; not model quality",
        }

    return tmp_path, m, plan, requests, state, authorize, gate, step, evidence


def test_scope_is_not_call_authorization_and_check_has_no_runtime_state(rig):
    root, _, plan, requests, state, _, _, step, _ = rig
    assert plan["provider_requests_authorized"] == plan["provider_cost_authorized"] == 0
    assert len(requests) == 4
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        step()
    assert not (root / "local-materials").exists() and not state["sends"]
    assert prepare.build(root)["run.json"] == runner.load(root)[0]
    for body in requests.values():
        assert body["reasoning"] == {"effort": "none"}
        assert body["max_output_tokens"] == 2048
        payload = json.loads(body["input"][1]["content"])
        assert "expected" not in payload and "historical_case_id" not in payload
    assert sum(plan["slot_cost_micro_cny"].values()) == plan["cost_cap_micro_cny"]


@pytest.mark.parametrize(
    "key,bad",
    [
        ("root_sha256", "0" * 64),
        ("requests", True),
        ("requests", 5),
        ("cost_micro_cny", 1),
        ("scope_sha256", "0" * 64),
        ("confirmed_by", "assistant"),
        ("exit_limits", {"max_rounds": 3}),
        ("terms_verified_on", "2000-01-01"),
        ("source_message_id", ""),
    ],
)
def test_wrong_approval_before_state_and_sending(rig, key, bad):
    root, _, _, _, state, authorize, _, step, _ = rig
    state["record"][key] = bad
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        authorize()
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        step()
    assert not (root / "local-materials").exists() and not state["sends"]


def test_four_one_shot_requests_each_need_fresh_fact_gate(rig):
    root, _, _, _, state, authorize, _, step, evidence = rig
    authorize()
    for number in range(1, 5):
        result = step()
        assert result["state"] == "HUMAN_REVIEW_REQUIRED" and result["number"] == number
        with pytest.raises(GateFailure, match="HUMAN_REVIEW_REQUIRED"):
            step()
        assert len(state["sends"]) == number
        assert runner.assess(root, evidence())["fact_gate_passed"]
    with pytest.raises(GateFailure, match="RUN_COMPLETE"):
        step()
    report = runner.report(root)
    assert len(state["sends"]) == len(report["attempts"]) == 4
    assert all(
        x["input_tokens"] == 100 and x["output_tokens"] == 200 and x["assessment_hash"]
        for x in report["attempts"]
    )
    assert report["run"]["halted"] is None and report["t040_complete"] is False


def test_send_consumed_once_and_crash_is_durably_terminal(rig):
    root, _, _, _, state, authorize, gate, step, _ = rig
    authorize()
    b = gate()
    n = b.reserve_next()
    assert b.consume(n)
    with pytest.raises(GateFailure, match="SEND_ALREADY_CONSUMED"):
        b.consume(n)
    with pytest.raises(GateFailure, match="RUN_ACTIVE"):
        gate()
    b.close()
    with pytest.raises(GateFailure, match="SAFETY_FAILURE"):
        step()
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        step()
    assert runner.report(root)["run"]["halted"] == "SAFETY_FAILURE"
    assert len(runner.report(root)["attempts"]) == 1 and not state["sends"]


def test_registered_missing_ledger_never_recreates(rig):
    root, _, _, _, _, authorize, gate, _, _ = rig
    authorize()
    b = gate()
    ledger = b.ledger
    b.close()
    ledger.unlink()
    with pytest.raises(GateFailure, match="LEDGER_MISSING"):
        gate()
    assert not ledger.exists() and (root / "local-materials").exists()


@pytest.mark.parametrize(
    "field,value",
    [("value_hash", "0" * 64), ("number", 2), ("confirmed_by", "assistant"), ("passed", 1)],
)
def test_stale_or_invalid_fact_check_does_not_advance(rig, field, value):
    root, _, _, _, state, authorize, _, step, evidence = rig
    authorize()
    step()
    bad = evidence()
    bad[field] = value
    with pytest.raises((GateFailure, p.Invalid)):
        runner.assess(root, bad)
    with pytest.raises(GateFailure, match="HUMAN_REVIEW_REQUIRED"):
        step()
    assert len(state["sends"]) == 1
    runner.assess(root, evidence())
    assert step()["number"] == 2


def test_failed_fact_gate_stops_without_refund(rig):
    root, _, _, _, state, authorize, _, step, evidence = rig
    authorize()
    step()
    with pytest.raises(GateFailure, match="ADMISSION_FAILED"):
        runner.assess(root, evidence(False))
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        step()
    report = runner.report(root)
    assert len(state["sends"]) == 1 and report["run"]["halted"] == "ADMISSION_FAILED"
    assert report["attempts"][0]["assessment_hash"]


def change_value(response, **changes):
    text = response["output"][0]["content"][0]
    value = json.loads(text["text"])
    value.update(changes)
    text["text"] = json.dumps(value)


def test_concrete_defect_pass_halts_before_next_call(rig):
    root, _, _, _, state, authorize, _, step, _ = rig
    authorize()
    state["edit"] = lambda r: change_value(r, verdict="pass", findings=[])
    with pytest.raises(GateFailure, match="CONCRETE_DEFECT_MISSED"):
        step()
    assert runner.report(root)["run"]["halted"] == "CONCRETE_DEFECT_MISSED"
    assert len(state["sends"]) == 1


def test_fact_gate_rechecks_quality_after_post_receipt_interruption(rig, monkeypatch):
    root, _, _, _, state, authorize, _, step, evidence = rig
    authorize()
    state["edit"] = lambda r: change_value(r, verdict="pass", findings=[])
    # Simulate persistence followed by interruption before the post-send gate.
    with monkeypatch.context() as patch:
        patch.setattr(FixedFocusGate, "coarse_gate", lambda self, number: None)
        step()
    with pytest.raises(GateFailure, match="CONCRETE_DEFECT_MISSED"):
        runner.assess(root, evidence())
    assert runner.report(root)["run"]["halted"] == "CONCRETE_DEFECT_MISSED"
    assert len(state["sends"]) == 1


def test_correct_control_rejection_halts(rig):
    root, _, _, _, state, authorize, _, step, evidence = rig
    authorize()
    for _ in range(2):
        step()
        runner.assess(root, evidence())
    state["edit"] = lambda r: change_value(
        r,
        verdict="revise",
        findings=[{"area": "fact", "severity": "major", "message": "Synthetic false positive"}],
    )
    with pytest.raises(GateFailure, match="CONTROL_REJECTED"):
        step()
    assert runner.report(root)["run"]["halted"] == "CONTROL_REJECTED"
    assert len(state["sends"]) == 3


@pytest.mark.parametrize("case", ["model", "status", "usage", "reasoning", "binding", "oversize"])
def test_protocol_failures_stop_and_keep_observed_usage(rig, case):
    root, _, _, _, state, authorize, _, step, _ = rig
    authorize()

    def edit(r):
        if case == "model":
            r["model"] = "another-model"
        elif case == "status":
            r["status"] = "incomplete"
        elif case == "usage":
            r["usage"]["input_tokens"] = None
        elif case == "reasoning":
            r["usage"]["output_tokens_details"]["reasoning_tokens"] = 200
        elif case == "binding":
            change_value(r, request_id="0" * 64)
        else:
            r["usage"]["output_tokens"] = 2049

    state["edit"] = edit
    with pytest.raises(GateFailure):
        step()
    report = runner.report(root)
    assert report["run"]["halted"] and len(state["sends"]) == 1
    assert report["attempts"][0]["input_tokens"] == (None if case == "usage" else 100)
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        step()


@pytest.mark.parametrize("case", ["source", "wire", "env", "revoked"])
def test_rotation_and_tampering_stop_before_http(rig, case):
    root, m, plan, requests, state, authorize, _, step, _ = rig
    a = authorize()
    if case == "source":
        (root / "scripts/run_t040_focus.py").write_text("changed")
    elif case == "wire":
        path = root / prepare.BASE_REL / "requests.json"
        altered = copy.deepcopy(requests)
        altered["focus-01"]["temperature"] = 1
        path.write_bytes(p.encoded(altered))
    elif case == "env":
        (root / ".env").write_text("changed-synthetic-credentials")
    else:
        (root / prepare.BASE_REL / "run-approval.json").unlink()
        with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
            runner.credentials(root, m, plan, a)()
    with pytest.raises(GateFailure):
        step()
    assert not state["sends"]


def test_expiry_and_clock_rollback_cannot_extend_deadline(rig, monkeypatch):
    root, _, _, _, state, authorize, gate, _, _ = rig
    authorize()
    b = gate()
    original = time.time()
    monkeypatch.setattr(time, "time", lambda: original - 10)
    try:
        with pytest.raises(GateFailure, match="TIMEOUT"):
            b.reserve_next()
    finally:
        b.close()
    assert runner.report(root)["run"]["halted"] == "TIMEOUT" and not state["sends"]


def test_execution_root_and_extra_round_are_rejected_before_enrollment(rig):
    root, m, plan, requests, _, authorize, _, _, _ = rig
    a = authorize()
    for change, code in [
        ({"execution_root": "/tmp/another"}, "ROOT_CHANGED"),
        ({"round": 3}, "INVALID_ROUND"),
    ]:
        with pytest.raises(GateFailure, match=code):
            FixedFocusGate(root, m, {**plan, **change}, requests, a)
    assert not (root / "local-materials").exists()


def test_second_round_requires_terminal_first_and_distinct_approval(rig):
    root, m, plan, requests, _, authorize, gate, _, _ = rig
    authorize()
    gate().close()
    second_m = copy.deepcopy(m)
    second_m["run_id"] = "span-focus-r11"
    second_plan = {**plan, "round": 2}
    from acceptance_support.phase1_budget import Approval

    a = Approval(p.digest(second_m), "diagnostic", 4, plan["cost_cap_micro_cny"], "a" * 64, True)
    with pytest.raises(GateFailure, match="PREREQUISITE_MISSING"):
        FixedFocusGate(root, second_m, second_plan, requests, a)
    registry = root / "local-materials/span-selection-redesign-v1/round-2.json"
    assert not registry.exists()
    first = gate()
    try:
        with first._db() as db:
            with pytest.raises(GateFailure, match="ADMISSION_FAILED"):
                first._halt(db, "ADMISSION_FAILED")
    finally:
        first.close()
    second = FixedFocusGate(root, second_m, second_plan, requests, a)
    second.close()
    assert registry.exists()
    a2 = Approval(p.digest(second_m), "diagnostic", 4, plan["cost_cap_micro_cny"], "b" * 64, True)
    with pytest.raises(GateFailure, match="REGISTRY_MISMATCH"):
        FixedFocusGate(root, second_m, second_plan, requests, a2)


def test_absolute_deadline_halts_before_attempt(rig, monkeypatch):
    root, _, _, _, state, authorize, gate, _, _ = rig
    authorize()
    b = gate()
    monkeypatch.setattr(time, "time", lambda: b.deadline + 1)
    try:
        with pytest.raises(GateFailure, match="TIMEOUT"):
            b.reserve_next()
    finally:
        b.close()
    assert not state["sends"] and not runner.report(root)["attempts"]
