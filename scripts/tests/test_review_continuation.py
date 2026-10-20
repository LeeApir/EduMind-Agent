"""Continuation preserves five exact wires, human gates and terminal failure."""

# ruff: noqa: E402
import asyncio
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import run_review_continuation as run
from acceptance_support.qwen_review_budget import canonical, sha
from test_final_review_execution import outcome


def fixture(tmp_path, monkeypatch):
    for name in (
        run.BASE + "/requests.json",
        run.BASE + "/plan.json",
        run.parent.MATERIALS + "/cases.json",
    ):
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((ROOT / name).read_bytes())
    requests = run.read(tmp_path / run.BASE / "requests.json")
    m = dict(
        request_sha256={s: v["wire_sha256"] for s, v in requests.items()},
        expires_at_epoch=run.time.time() + 86400,
    )
    monkeypatch.setattr(run, "authorize", lambda root: (m, "a" * 64))
    monkeypatch.setattr(run, "old_stopped", lambda root: None)
    return run.read(tmp_path / run.BASE / "plan.json")["expected"]


def sign(root, slot, passed=True):
    receipt = run.read(root / run.PRIVATE / f"{slot}-receipt.json")
    p = root / run.BASE / "assessments"
    p.mkdir(exist_ok=True)
    (p / f"{slot}.json").write_text(
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
                issues=[] if passed else ["unsupported assertion"],
            )
        )
    )


def test_five_calls_require_each_actual_human_result(tmp_path, monkeypatch):
    expected = fixture(tmp_path, monkeypatch)
    calls = []

    async def attempt(root, m, case, wire, auth):
        auth()
        slot = run.SLOTS[len(calls)]
        calls.append(slot)
        return outcome(wire, expected[slot])

    for slot in run.SLOTS:
        assert (
            asyncio.run(run.step(tmp_path, attempt))["state"] == "WAITING_HUMAN_REVIEW"
        )
        with pytest.raises(ValueError, match="HUMAN_CHECK_REQUIRED"):
            asyncio.run(run.step(tmp_path, attempt))
        sign(tmp_path, slot)
    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    assert calls == list(run.SLOTS)


@pytest.mark.parametrize("failure", ["timeout", "severe_miss", "citation"])
def test_first_failure_stops_no_more_calls(tmp_path, monkeypatch, failure):
    fixture(tmp_path, monkeypatch)
    calls = []

    async def attempt(root, m, case, wire, auth):
        auth()
        calls.append(True)
        if failure == "timeout":
            raise TimeoutError()
        return outcome(wire, "pass" if failure == "severe_miss" else "reject")

    result = asyncio.run(run.step(tmp_path, attempt))
    if failure == "citation":
        assert result["state"] == "WAITING_HUMAN_REVIEW"
        sign(tmp_path, run.SLOTS[0], False)
        with pytest.raises(ValueError, match="CANDIDATE_FAILED"):
            asyncio.run(run.step(tmp_path, attempt))
    else:
        assert result["state"] == "STOPPED"
    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    assert calls == [True]


def test_no_authority_before_private_or_key_access(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "verify", lambda root: ({}, "a" * 64))
    monkeypatch.setattr(run, "old_stopped", lambda root: pytest.fail("must deny first"))
    with pytest.raises(ValueError, match="FILE_REQUIRED"):
        asyncio.run(run.step(tmp_path))
    assert not (tmp_path / run.PRIVATE).exists()


def test_exact_five_wires_no_material_or_config_changes():
    actual = run.read(ROOT / run.BASE / "requests.json")
    original = run.read(ROOT / run.parent.BASE / "requests.json")
    assert list(actual) == list(run.SLOTS) and len(actual) == 5
    assert all(actual[s] == original[s] for s in run.SLOTS)
    assert run.PRIVATE not in (run.parent.PRIVATE, run.retry.PRIVATE)


def test_uncertain_send_consumes_slot_and_stops(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    p = tmp_path / run.PRIVATE
    p.mkdir(parents=True, mode=0o700)
    slot = run.SLOTS[0]
    request = run.read(tmp_path / run.BASE / "requests.json")[slot]
    run.private_write(
        p / f"{slot}-reservation.json",
        dict(
            manifest_sha256="a" * 64,
            slot=slot,
            request_sha256=request["wire_sha256"],
            created_epoch=run.time.time(),
        ),
    )
    with pytest.raises(ValueError, match="SEND_STATE_UNCERTAIN"):
        asyncio.run(run.step(tmp_path))
    assert asyncio.run(run.step(tmp_path))["state"] == "STOPPED"


def test_exact_new_five_authority(tmp_path, monkeypatch):
    monkeypatch.setattr(
        run,
        "verify",
        lambda root: (dict(expires_at_epoch=run.time.time() + 60), "a" * 64),
    )
    p = tmp_path / run.BASE
    p.mkdir(parents=True)
    a = dict(
        manifest_sha256="a" * 64,
        requests=5,
        reviewer="Lee",
        source_user_message=run.USER_MESSAGE,
        decision="continue_exact_remaining_five",
        old_run_resume=False,
        per_result_actual_human_gate=True,
    )
    for count in (True, 1, 6):
        a["requests"] = count
        (p / "run-approval.json").write_text(json.dumps(a))
        with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
            run.authorize(tmp_path)
    a["requests"] = 5
    (p / "run-approval.json").write_text(json.dumps(a))
    assert run.authorize(tmp_path)[1] == "a" * 64
