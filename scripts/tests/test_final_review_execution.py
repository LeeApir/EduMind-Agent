"""New high-only twelve-slot execution: prior failures cannot be waived or reused."""

# ruff: noqa: E402
import asyncio
import json
from pathlib import Path
import socket
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import run_final_review_candidate as run
from prepare_final_review_execution import build
from acceptance_support.luna_admission_gate import private_write
from acceptance_support.qwen_review_budget import canonical, sha
from acceptance_support.om_diagnostic import valid_review


def read(path):
    return json.loads(path.read_bytes())


def fixture(tmp_path, monkeypatch):
    for relative in (
        run.BASE + "/requests.json",
        run.BASE + "/plan.json",
        run.MATERIALS + "/cases.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    requests = read(tmp_path / run.BASE / "requests.json")
    m = dict(
        request_sha256={k: v["wire_sha256"] for k, v in requests.items()},
        expires_at_epoch=run.time.time() + 86400,
    )
    monkeypatch.setattr(run, "authorize", lambda root: (m, "a" * 64))
    monkeypatch.setattr(run, "historical_stop", lambda root: None)
    return read(tmp_path / run.BASE / "plan.json")


def outcome(wire, expected):
    value = valid_review("unit")
    value["verdict"] = expected
    if expected == "needs_human":
        value["unresolved"] = ["scripted specific teaching gap"]
    if expected == "reject":
        value["findings"] = [
            dict(
                category="code_safety",
                severity="major",
                anchors=["a1"],
                condition_or_counterexample="scripted reachable failure",
                impact="scripted test fixture",
            )
        ]
    return dict(
        sent=1,
        http_status=200,
        raw_complete=True,
        model="gpt-6-luna",
        requested_reasoning="high",
        input_tokens=100,
        output_tokens=100,
        record=dict(
            result=value, request_digest=sha(wire), local_routing=dict(verdict=expected)
        ),
    )


def sign(root, slot, passed=True):
    receipt = read(root / run.PRIVATE / (slot + "-receipt.json"))
    folder = root / run.BASE / "assessments"
    folder.mkdir(exist_ok=True)
    (folder / (slot + ".json")).write_text(
        json.dumps(
            dict(
                manifest_sha256="a" * 64,
                slot=slot,
                receipt_sha256=sha(canonical(receipt)),
                reviewer="Lee",
                source_user_message="TEST ONLY actual-result confirmation",
                integrity=True,
                all_claims=passed,
                all_citations=True,
                criterion=True,
                issues=[]
                if passed
                else ["invented requirement or false evidence claim"],
            )
        )
    )


def test_actual_high_attempt_path_matches_proposal_without_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: pytest.fail("no DNS"))
    actual = asyncio.run(build())
    assert actual == {n: read(ROOT / run.BASE / n) for n in actual}
    assert all(
        v["requested_effort"] == "high"
        for v in actual["execution-capture.json"].values()
    )


def test_twelve_calls_all_human_gated_and_no_formal_advance(tmp_path, monkeypatch):
    plan = fixture(tmp_path, monkeypatch)
    calls = []

    async def attempt(root, m, case, wire, auth):
        auth()
        slot = run.SLOTS[len(calls)]
        calls.append(slot)
        return outcome(wire, plan["expected"][slot])

    for slot in run.SLOTS:
        assert (
            asyncio.run(run.step(tmp_path, attempt))["state"] == "WAITING_HUMAN_REVIEW"
        )
        with pytest.raises(ValueError, match="HUMAN_CHECK_REQUIRED"):
            asyncio.run(run.step(tmp_path, attempt))
        sign(tmp_path, slot)
    assert len(calls) == 12
    assert (
        asyncio.run(run.step(tmp_path, attempt))["state"]
        == "DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION"
    )
    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    assert (
        read(tmp_path / run.PRIVATE / "halt.json")["research_batch"]
        == "DIAGNOSTIC_COMPLETE_PENDING_ADMISSION"
    )


@pytest.mark.parametrize(
    "failure",
    [
        "timeout",
        "false_requirement",
        "truncated",
        "missing_usage",
        "wrong_model",
        "wrong_effort",
    ],
)
def test_compatibility_failure_stops_whole_research_batch(
    tmp_path, monkeypatch, failure
):
    fixture(tmp_path, monkeypatch)
    calls = []

    async def attempt(root, m, case, wire, auth):
        auth()
        calls.append(True)
        if failure == "timeout":
            raise TimeoutError()
        value = outcome(
            wire, "needs_human" if failure == "false_requirement" else "pass"
        )
        if failure == "truncated":
            value["raw_complete"] = False
        if failure == "missing_usage":
            value["output_tokens"] = None
        if failure == "wrong_model":
            value["model"] = "another"
        if failure == "wrong_effort":
            value["requested_reasoning"] = "low"
        return value

    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    stop = read(tmp_path / run.PRIVATE / "halt.json")
    assert (
        stop["research_batch"] == "STOPPED_SCOPE_DISCUSSION_REQUIRED"
        and stop["next_candidates_allowed"] == 0
    )
    assert calls == [True]


def test_false_evidence_statement_in_actual_result_eliminates_batch(
    tmp_path, monkeypatch
):
    fixture(tmp_path, monkeypatch)

    async def attempt(root, m, case, wire, auth):
        auth()
        return outcome(wire, "pass")

    asyncio.run(run.step(tmp_path, attempt))
    sign(tmp_path, "compat-schema", False)
    with pytest.raises(ValueError, match="CANDIDATE_FAILED"):
        asyncio.run(run.step(tmp_path, attempt))
    assert (
        read(tmp_path / run.PRIVATE / "halt.json")["research_batch"]
        == "STOPPED_SCOPE_DISCUSSION_REQUIRED"
    )
    assert not (tmp_path / run.PRIVATE / "cal-01-reservation.json").exists()


def test_severe_miss_cannot_become_human_accepted_pass(tmp_path, monkeypatch):
    plan = fixture(tmp_path, monkeypatch)
    calls = []

    async def attempt(root, m, case, wire, auth):
        auth()
        slot = run.SLOTS[len(calls)]
        calls.append(slot)
        return outcome(
            wire, "pass" if slot == "screen-safety" else plan["expected"][slot]
        )

    for slot in run.SLOTS:
        result = asyncio.run(run.step(tmp_path, attempt))
        if slot == "screen-safety":
            assert result["state"] == "STOPPED"
            break
        sign(tmp_path, slot)
    assert calls[-1] == "screen-safety"
    assert not (tmp_path / run.PRIVATE / "screen-mixed-reservation.json").exists()
    assert (
        read(tmp_path / run.PRIVATE / "halt.json")["research_batch"]
        == "STOPPED_SCOPE_DISCUSSION_REQUIRED"
    )


def test_missing_new_approval_denies_before_any_private_state(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "verify", lambda root: ({}, "a" * 64))
    monkeypatch.setattr(
        run, "historical_stop", lambda root: pytest.fail("must deny first")
    )
    with pytest.raises(ValueError, match="FILE_REQUIRED"):
        asyncio.run(run.step(tmp_path))
    assert not (tmp_path / run.PRIVATE).exists()


def test_uncertain_send_and_expiry_do_not_reopen_batch(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    p = tmp_path / run.PRIVATE
    p.mkdir(parents=True, mode=0o700)
    request = read(tmp_path / run.BASE / "requests.json")["compat-schema"]
    private_write(
        p / "compat-schema-reservation.json",
        dict(
            slot="compat-schema",
            manifest_sha256="a" * 64,
            request_sha256=request["wire_sha256"],
            created_epoch=run.time.time(),
        ),
    )
    with pytest.raises(ValueError, match="SEND_STATE_UNCERTAIN"):
        asyncio.run(run.step(tmp_path))
    assert (
        read(p / "halt.json")["research_batch"] == "STOPPED_SCOPE_DISCUSSION_REQUIRED"
    )


def test_exact_new_authority_accepts_only_twelve_with_proposal_truth(
    tmp_path, monkeypatch
):
    names = ("cases.json", "labels.json", "requests.json", "plan.json")
    m = dict(
        expires_at_epoch=run.time.time() + 86400,
        files={run.MATERIALS + "/" + n: "x" * 64 for n in names},
    )
    monkeypatch.setattr(run, "verify", lambda root: (m, "a" * 64))
    base = tmp_path / run.BASE
    base.mkdir(parents=True)
    approval = dict(
        manifest_sha256="a" * 64,
        requests=12,
        decision="approve_final_candidate_twelve_requests",
        reviewer="Lee",
        source_user_message="TEST ONLY exact new approval",
        cost_policy="uncapped_by_explicit_user_instruction",
    )
    truth = dict(material_files={n: "x" * 64 for n in names}, results_presigned=False)
    (base / "truth-confirmation.json").write_text(json.dumps(truth))
    for count in (4, True, 13):
        approval["requests"] = count
        (base / "run-approval.json").write_text(json.dumps(approval))
        with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
            run.authorize(tmp_path)
    approval["requests"] = 12
    (base / "run-approval.json").write_text(json.dumps(approval))
    assert run.authorize(tmp_path)[1] == "a" * 64
