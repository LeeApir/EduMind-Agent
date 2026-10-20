"""Real-path Mock capture and fail-closed four-slot authority tests; no Provider calls."""

# ruff: noqa: E402
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import socket
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import run_luna_process_calibration as run
from prepare_luna_process_execution import build
from acceptance_support.luna_admission_gate import private_write
from acceptance_support.qwen_review_budget import canonical, sha
from acceptance_support.om_diagnostic import valid_review


def get(path):
    return json.loads(path.read_bytes())


def test_actual_execution_capture_reproduces_without_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: pytest.fail("no DNS"))
    captured = asyncio.run(build())
    assert captured == {name: get(ROOT / run.BASE / name) for name in captured}
    for slot, value in captured["requests.json"].items():
        preview = get(ROOT / run.MATERIALS / "request-previews.json")[slot]
        assert value["wire_hex"] == preview["wire_hex"]
        assert value["host"] == value["sni"] == "www.cbbb.fun"
        assert value["target_url"] == "https://8.8.8.8/v1/responses"
        assert value["matches_confirmed_preview"] is True


def fixture_root(tmp_path, monkeypatch):
    requests = get(ROOT / run.BASE / "requests.json")
    cases = get(ROOT / run.MATERIALS / "cases.json")
    plan = get(ROOT / run.BASE / "plan.json")
    for relative, value in (
        (run.BASE + "/requests.json", requests),
        (run.BASE + "/plan.json", plan),
        (run.MATERIALS + "/cases.json", cases),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    m = {
        "request_sha256": {s: v["wire_sha256"] for s, v in requests.items()},
        "expires_at_epoch": run.time.time() + 3600,
    }
    monkeypatch.setattr(run, "authorize", lambda root: (m, "a" * 64))
    monkeypatch.setattr(run, "historical_stop", lambda root: None)
    return requests, plan


def outcome(wire, verdict="pass"):
    value = valid_review("unit")
    value["verdict"] = verdict
    if verdict == "needs_human":
        value["unresolved"] = [
            "specific missing teaching or assessment; scripted test value only"
        ]
    return dict(
        sent=1,
        http_status=200,
        raw_complete=True,
        model="gpt-6-luna",
        input_tokens=100,
        output_tokens=100,
        record=dict(
            result=value, request_digest=sha(wire), local_routing={"verdict": verdict}
        ),
    )


def sign(tmp_path, slot, passed=True):
    receipt = get(tmp_path / run.PRIVATE / f"{slot}-receipt.json")
    folder = tmp_path / run.BASE / "assessments"
    folder.mkdir(exist_ok=True)
    (folder / f"{slot}.json").write_text(
        json.dumps(
            dict(
                manifest_sha256="a" * 64,
                slot=slot,
                receipt_sha256=sha(canonical(receipt)),
                reviewer="Lee",
                source_user_message="TEST ONLY explicit result confirmation",
                integrity=True,
                all_claims=passed,
                all_citations=True,
                criterion=True,
                issues=[] if passed else ["unsupported assertion"],
            )
        )
    )


def test_four_requests_need_each_actual_human_check_and_stop(tmp_path, monkeypatch):
    _, plan = fixture_root(tmp_path, monkeypatch)
    sends = []

    async def attempt(root, manifest, case, wire, auth):
        auth()
        slot = run.SLOTS[len(sends)]
        sends.append(slot)
        return outcome(wire, plan["expected"][slot])

    for slot in run.SLOTS:
        assert (
            asyncio.run(run.step(tmp_path, attempt))["state"] == "WAITING_HUMAN_REVIEW"
        )
        with pytest.raises(ValueError, match="HUMAN_CHECK_REQUIRED"):
            asyncio.run(run.step(tmp_path, attempt))
        sign(tmp_path, slot)
    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "CALIBRATION_COMPLETE"
    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    assert sends == list(run.SLOTS)


@pytest.mark.parametrize(
    "failure",
    [
        "timeout",
        "wrong_verdict",
        "missing_usage",
        "incomplete",
        "missing_check",
        "extra_finding",
        "no_send_auth",
    ],
)
def test_failure_is_durable_and_never_retries(tmp_path, monkeypatch, failure):
    fixture_root(tmp_path, monkeypatch)
    calls = []

    async def attempt(root, manifest, case, wire, auth):
        calls.append(1)
        if failure != "no_send_auth":
            auth()
        if failure == "timeout":
            raise TimeoutError()
        result = outcome(wire)
        if failure == "wrong_verdict":
            result = outcome(wire, "needs_human")
        if failure == "missing_usage":
            result["output_tokens"] = None
        if failure == "incomplete":
            result["raw_complete"] = False
        if failure == "missing_check":
            result["record"]["result"]["coverage"]["checked"].pop()
        if failure == "extra_finding":
            result["record"]["result"]["findings"] = [{"made_up": True}]
        return result

    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    assert calls == [1]


def test_failed_actual_human_review_halts(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)

    async def attempt(root, manifest, case, wire, auth):
        auth()
        return outcome(wire)

    asyncio.run(run.step(tmp_path, attempt))
    sign(tmp_path, "cal-01", False)
    with pytest.raises(ValueError, match="CANDIDATE_FAILED"):
        asyncio.run(run.step(tmp_path, attempt))
    assert (
        get(tmp_path / run.PRIVATE / "halt.json")["reason"]
        == "SEMANTIC_OR_CITATION_FAILURE"
    )


def test_uncertain_reservation_cannot_replay(tmp_path, monkeypatch):
    requests, _ = fixture_root(tmp_path, monkeypatch)
    p = tmp_path / run.PRIVATE
    p.mkdir(parents=True, mode=0o700)
    private_write(
        p / "cal-01-reservation.json",
        dict(
            manifest_sha256="a" * 64,
            slot="cal-01",
            request_sha256=requests["cal-01"]["wire_sha256"],
            created_epoch=run.time.time(),
        ),
    )
    with pytest.raises(ValueError, match="SEND_STATE_UNCERTAIN"):
        asyncio.run(run.step(tmp_path))
    assert get(p / "halt.json")["reason"] == "SEND_STATE_UNCERTAIN"


def test_wall_timeout_cannot_start_next_request(tmp_path, monkeypatch):
    requests, _ = fixture_root(tmp_path, monkeypatch)
    p = tmp_path / run.PRIVATE
    p.mkdir(parents=True, mode=0o700)
    private_write(
        p / "cal-01-reservation.json",
        dict(
            manifest_sha256="a" * 64,
            slot="cal-01",
            request_sha256=requests["cal-01"]["wire_sha256"],
            created_epoch=run.time.time() - 1801,
        ),
    )
    assert asyncio.run(run.step(tmp_path))["reason"] == "WALL_TIME_EXPIRED"


def test_real_authority_requires_new_exact_approval_before_private_state(
    tmp_path, monkeypatch
):
    manifest = {
        "expires_at_epoch": run.time.time() + 100,
        "files": {
            run.MATERIALS + "/" + n: "x" * 64
            for n in (
                "cases.json",
                "proposed-labels.json",
                "criteria.md",
                "materials-review.md",
                "labels-review.md",
            )
        },
    }
    monkeypatch.setattr(run, "verify", lambda root: (manifest, "a" * 64))
    monkeypatch.setattr(
        run, "historical_stop", lambda root: pytest.fail("not authorized")
    )
    with pytest.raises(ValueError, match="FILE_REQUIRED"):
        asyncio.run(run.step(tmp_path))
    assert not (tmp_path / run.PRIVATE).exists()


@pytest.mark.parametrize(
    "change", ["hash", "bool_count", "source", "decision", "expiry", "label"]
)
def test_wrong_or_stale_authority_rejected(tmp_path, monkeypatch, change):
    names = (
        "cases.json",
        "proposed-labels.json",
        "criteria.md",
        "materials-review.md",
        "labels-review.md",
    )
    m = {
        "expires_at_epoch": run.time.time() + 100,
        "files": {run.MATERIALS + "/" + n: "x" * 64 for n in names},
    }
    monkeypatch.setattr(run, "verify", lambda root: (m, "a" * 64))
    base = tmp_path / run.BASE
    base.mkdir(parents=True)
    approval = dict(
        manifest_sha256="a" * 64,
        requests=4,
        decision="approve_four_calibration_requests",
        reviewer="Lee",
        source_user_message="TEST ONLY",
        cost_policy="uncapped_by_explicit_user_instruction",
    )
    labels = dict(
        reviewer="Lee",
        source_user_message="TEST ONLY",
        decision="accept_all_four_calibration_materials_and_labels",
        material_files={n: "x" * 64 for n in names},
    )
    if change == "hash":
        approval["manifest_sha256"] = "b" * 64
    if change == "bool_count":
        approval["requests"] = True
    if change == "source":
        approval["source_user_message"] = ""
    if change == "decision":
        approval["decision"] = "old12"
    if change == "expiry":
        m["expires_at_epoch"] = 0
    if change == "label":
        labels["material_files"]["cases.json"] = "bad"
    (base / "run-approval.json").write_text(json.dumps(approval))
    (base / "labels-human.json").write_text(json.dumps(labels))
    with pytest.raises(ValueError):
        run.authorize(tmp_path)
    assert not (tmp_path / run.PRIVATE).exists()


def test_material_confirmation_is_not_request_authority():
    labels = get(ROOT / run.BASE / "labels-human.json")
    assert labels["source_user_message"] == "全部确认"
    assert labels["actual_results_signed"] is False
    assert labels["requests_authorized"] == 0


def test_structure_rejects_output_over_budget_and_bool_usage():
    wire = b"test"
    good = outcome(wire)
    for value in (8193, True, -1):
        bad = deepcopy(good)
        bad["output_tokens"] = value
        with pytest.raises(ValueError):
            run.structural_criterion(bad, "pass", sha(wire))


def test_second_send_authority_in_same_attempt_is_forbidden(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    authorities = []

    async def attempt(root, manifest, case, wire, auth):
        auth()
        authorities.append(True)
        auth()
        pytest.fail("second authorization must be rejected")

    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    assert authorities == [True]


def test_concurrent_entry_stops_uncertain_slot_without_second_attempt(
    tmp_path, monkeypatch
):
    fixture_root(tmp_path, monkeypatch)
    attempts = []

    async def attempt(root, manifest, case, wire, auth):
        attempts.append(True)
        with pytest.raises(ValueError, match="SEND_STATE_UNCERTAIN"):
            await run.step(tmp_path, lambda *a: pytest.fail("no concurrent send"))
        auth()  # concurrent invocation has already persisted a halt
        pytest.fail("halt must prevent original pending send")

    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "STOPPED"
    assert attempts == [True]


@pytest.mark.parametrize("tamper", ["root", "source", "env"])
def test_verify_rejects_changed_root_source_or_environment(
    tmp_path, monkeypatch, tamper
):
    base = tmp_path / run.BASE
    base.mkdir(parents=True)
    evidence = tmp_path / "source.txt"
    evidence.write_text("frozen")
    m = dict(
        execution_root=str(tmp_path.resolve()),
        requests_max=4,
        slots=list(run.SLOTS),
        files={"source.txt": sha(evidence.read_bytes())},
        env_metadata={"identity": 1},
    )
    monkeypatch.setattr(run, "env_metadata", lambda p: {"identity": 1})
    if tamper == "root":
        m["execution_root"] = "/different/root"
    if tamper == "source":
        evidence.write_text("changed")
    if tamper == "env":
        monkeypatch.setattr(run, "env_metadata", lambda p: {"identity": 2})
    (base / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ValueError):
        run.verify(tmp_path)


def test_call_timeout_shrinks_near_absolute_deadline(tmp_path, monkeypatch):
    fixture_root(tmp_path, monkeypatch)
    m, h = run.authorize(tmp_path)
    m["expires_at_epoch"] = run.time.time() + 8
    monkeypatch.setattr(run, "authorize", lambda root: (m, h))
    original_timeout = asyncio.timeout
    limits = []

    def timeout(seconds):
        limits.append(seconds)
        return original_timeout(seconds)

    monkeypatch.setattr(run.asyncio, "timeout", timeout)

    async def attempt(root, manifest, case, wire, auth):
        auth()
        return outcome(wire)

    assert asyncio.run(run.step(tmp_path, attempt))["state"] == "WAITING_HUMAN_REVIEW"
    assert len(limits) == 1 and 0 < limits[0] <= 3
