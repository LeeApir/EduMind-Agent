"""Synthetic approval/credential/fact gate composition. Real env, DNS and API forbidden."""

import asyncio
import json
import shutil
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from test_derived_diagnostic_budget import bound_value, sample_value

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import prepare_t040_derived_run as prepare  # noqa: E402
import run_t040_derived_calibration as run  # noqa: E402
from acceptance_support import claim_review_prototype as p  # noqa: E402
from acceptance_support.derived_diagnostic_budget import (  # noqa: E402
    GateFailure,
    price,
)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[2]
    old = json.loads(
        (
            repo / "docs/acceptance/phase-1-t040-review-coverage-check/run-review_scope-r08.json"
        ).read_text()
    )
    paths = set(old["files"]) | {
        "scripts/prepare_t040_derived_calibration.py",
        "scripts/prepare_t040_derived_run.py",
        "scripts/run_t040_derived_calibration.py",
        "scripts/acceptance_support/claim_review_prototype.py",
        "scripts/acceptance_support/derived_diagnostic_budget.py",
        "scripts/acceptance_support/derived_review_contracts.py",
        "scripts/acceptance_support/derived_responses_sender.py",
        "backend/tests/test_t040_derived_run.py",
        "backend/tests/test_derived_responses_sender.py",
        "backend/tests/test_derived_diagnostic_budget.py",
        "docs/ADR/0014-derived-budget-approval-20261015.json",
        "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
        prepare.BASE_REL + "/token-cost-proof.json",
        "docs/acceptance/phase-1-t040-review-coverage-check/run-review_scope-r08.json",
    }
    for name in paths:
        dst = tmp_path / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / name, dst)
    (tmp_path / ".env").write_text(
        "EDUMIND_PROVIDER_BASE_URL=https://api.deepseek.com\n"
        "EDUMIND_PROVIDER_MODEL=deepseek-flash\n"
        "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT=responses_json_schema\n"
        "EDUMIND_PROVIDER_API_KEY=synthetic-private-key\n"
    )
    artifacts = prepare.artifacts(tmp_path)
    m = artifacts["run-r09.json"]
    for case in m["cases"]:
        case["content"] = {"markdown": "First assertion. Second assertion."}
    for name, value in artifacts.items():
        (tmp_path / prepare.BASE_REL / name).write_bytes(p.encoded(value))
    target = artifacts["target.json"]
    approval = {
        "version": "derived-calibration-run-approval-v1",
        "root_sha256": p.digest(m),
        "requests": 38,
        "cost_micro_cny": m["bounds"]["cost_micro"],
        "expires_at": m["bounds"]["expires_at"],
        "target_sha256": p.digest(target),
        "consent_sha256": target["consent_sha256"],
        "proof_sha256": m["stages"]["inventory"]["proof_sha256"],
        "confirmed_by": "Lee",
        "user_confirmation": "SYNTHETIC ONLY, no actual human approval",
        "source_message_id": "synthetic-test-only",
        "terms_verified_on": time.strftime("%Y-%m-%d"),
    }
    state = {"sends": [], "approval": approval, "m": m, "root": tmp_path}

    def no_network(*a, **kw):
        pytest.fail("Real DNS/socket forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)

    async def handle(request):
        state["sends"].append(request)
        body = json.loads(request.content)
        data = json.loads(body["input"][1]["content"])
        req = {"slot": data["request_binding"]["slot"], "wire": request.content}
        value = sample_value(SimpleNamespace(manifest=m), req)
        if data["request_binding"]["slot"].startswith("queue-error") and "focus" in data:
            value.update(
                verdict="revise",
                findings=[
                    {
                        "area": "fact",
                        "severity": "major",
                        "message": "Synthetic explicit defect evidence",
                    }
                ],
            )
        response = {
            "model": "deepseek-flash",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {"type": "output_text", "text": json.dumps(bound_value(req, value))}
                    ],
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "output_tokens_details": {"reasoning_tokens": 150},
            },
        }
        return httpx.Response(200, stream=httpx.ByteStream(p.encoded(response)))

    state["transport"] = httpx.MockTransport(handle)
    return state


def approve(rig):
    (rig["root"] / prepare.BASE_REL / "run-approval.json").write_bytes(p.encoded(rig["approval"]))


def step(rig):
    return asyncio.run(
        run.step(rig["root"], transport=rig["transport"], resolver=lambda h, port: ("8.8.8.8",))
    )


def assessment(report, *, passed=True):
    refs = [f["ref"] for f in report["findings"]]
    return {
        "version": "derived-case-assessment-v1",
        "root_sha256": report["root_sha256"],
        "case_id": report["case_id"],
        "report_sha256": p.digest(report),
        "confirmed_by": "Lee",
        "user_confirmation": "Synthetic fact confirmation, not a real pass",
        "source_message_id": "synthetic-facts-only",
        "criteria": [
            {
                "criterion": cid,
                "passed": passed,
                "finding_refs": refs if passed else [],
                "observation": "Synthetic located observation",
            }
            for cid in report["criteria"]
        ],
    }


def test_full_plan_uses_context_contract_not_byte_token_equivalence(rig):
    m = rig["m"]
    assert m["bounds"]["requests"] == 38 and m["corrections"] == 0
    assert m["bounds"]["cost_micro"] == 2 * sum(
        price(m["stages"][s], m["stages"][s]["max_wire_bytes"]) * (16 if s == "claim" else 1)
        for s in ("inventory", "coverage", "claim", "overall")
    )
    assert all(s["input_overhead_tokens"] >= 1048576 for s in m["stages"].values())
    assert m["bounds"]["cost_micro"] > 82000000  # Intentionally conservative, not expected spend.
    assert not (rig["root"] / prepare.PRIVATE_REL).exists()


def test_no_approval_before_credentials_dns_or_enrollment(rig, monkeypatch):
    monkeypatch.setattr(run, "leases", lambda *a: pytest.fail("Credential access before approval"))
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        step(rig)
    assert not rig["sends"] and not (rig["root"] / prepare.PRIVATE_REL).exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("requests", True),
        ("requests", 39),
        ("cost_micro_cny", 1),
        ("root_sha256", "a" * 64),
        ("consent_sha256", "d" * 64),
        ("target_sha256", "e" * 64),
        ("proof_sha256", "b" * 64),
        ("terms_verified_on", "2026-01-01"),
        ("source_message_id", ""),
        ("confirmed_by", "model"),
        ("user_confirmation", ""),
    ],
)
def test_wrong_or_stale_approval_cannot_enroll_or_send(rig, field, value):
    rig["approval"][field] = value
    approve(rig)
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        step(rig)
    assert not rig["sends"] and not (rig["root"] / prepare.PRIVATE_REL).exists()


def test_approved_true_is_not_a_run_approval(rig):
    path = rig["root"] / prepare.BASE_REL / "run-approval.json"
    path.write_text('{"approved":true}')
    with pytest.raises(GateFailure):
        step(rig)
    assert not rig["sends"]


def test_env_rotation_after_freeze_denies_without_sending(rig):
    approve(rig)
    path = rig["root"] / ".env"
    path.write_text(path.read_text().replace("synthetic-private-key", "rotated-test-key"))
    with pytest.raises(GateFailure, match="SAFETY_FAILURE"):
        step(rig)
    assert not rig["sends"]
    r = run.reports(rig["root"])[0]
    assert r["run_halted"] == "SAFETY_FAILURE" and not r["complete"]
    assert "rotated-test-key" not in json.dumps(r)


def test_revoked_approval_denied_before_lease_key_read(rig):
    approve(rig)
    a = run.run_approval(rig["root"], rig["m"])
    get = run.leases(rig["root"], rig["m"], a)
    (rig["root"] / prepare.BASE_REL / "run-approval.json").unlink()
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        get()


def test_whole_two_case_flow_pauses_at_each_human_gate(rig):
    approve(rig)
    for _ in range(5):
        step(rig)
    with pytest.raises(GateFailure, match="CASE_REVIEW_REQUIRED"):
        step(rig)
    assert len(rig["sends"]) == 5
    reports = run.reports(rig["root"])
    assert reports[0]["complete"] and not reports[1]["complete"]
    assert run.assess(rig["root"], assessment(reports[0]))["human_gate_passed"]
    for _ in range(5):
        step(rig)
    with pytest.raises(GateFailure, match="CASE_REVIEW_REQUIRED"):
        step(rig)
    second = run.reports(rig["root"])[1]
    assert not second["findings"]
    assert run.assess(rig["root"], assessment(second))["t040_complete"] is False
    with pytest.raises(GateFailure, match="RUN_COMPLETE"):
        step(rig)
    assert len(rig["sends"]) == 10
    assert "synthetic-private-key" not in json.dumps(run.reports(rig["root"]))


@pytest.mark.parametrize(
    "edit", ["old_digest", "fake_ref", "missing_criterion", "bool_not_int", "no_user"]
)
def test_invalid_fact_evidence_cannot_advance_case(rig, edit):
    approve(rig)
    for _ in range(5):
        step(rig)
    evidence = assessment(run.reports(rig["root"])[0])
    if edit == "old_digest":
        evidence["report_sha256"] = "a" * 64
    elif edit == "fake_ref":
        evidence["criteria"][0]["finding_refs"] = ["900:made-up"]
    elif edit == "missing_criterion":
        evidence["criteria"].pop()
    elif edit == "bool_not_int":
        evidence["criteria"][0]["passed"] = 1
    else:
        evidence["user_confirmation"] = ""
    with pytest.raises(GateFailure, match="INVALID_ASSESSMENT"):
        run.assess(rig["root"], evidence)
    with pytest.raises(GateFailure, match="CASE_REVIEW_REQUIRED"):
        step(rig)
    assert len(rig["sends"]) == 5


def test_failed_fact_gate_halts_and_report_remains_readable(rig):
    approve(rig)
    for _ in range(5):
        step(rig)
    evidence = assessment(run.reports(rig["root"])[0], passed=False)
    with pytest.raises(GateFailure, match="ADMISSION_FAILED"):
        run.assess(rig["root"], evidence)
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        step(rig)
    assert run.reports(rig["root"])[0]["run_halted"] == "ADMISSION_FAILED"
    assert len(rig["sends"]) == 5


def test_prior_assessment_cannot_unlock_later_case(rig):
    approve(rig)
    for _ in range(5):
        step(rig)
    evidence = assessment(run.reports(rig["root"])[0])
    run.assess(rig["root"], evidence)
    with pytest.raises(GateFailure, match="INVALID_ASSESSMENT"):
        run.assess(rig["root"], evidence)
    assert len(rig["sends"]) == 5


def test_premature_assessment_refused(rig):
    approve(rig)
    step(rig)
    r = run.reports(rig["root"])[0]
    with pytest.raises(GateFailure, match="INVALID_ASSESSMENT"):
        run.assess(rig["root"], assessment(r))


def test_receipt_tampering_is_not_human_evidence(rig):
    import sqlite3

    approve(rig)
    step(rig)
    with sqlite3.connect(rig["root"] / rig["m"]["ledger_path"]) as db:
        db.execute("UPDATE children SET value_hash=?", ("a" * 64,))
    with pytest.raises(GateFailure, match="PARENT_HASH_MISMATCH"):
        run.reports(rig["root"])


def test_cross_slot_report_result_even_rehashed_is_rejected(rig):
    import sqlite3

    approve(rig)
    step(rig)
    with sqlite3.connect(rig["root"] / rig["m"]["ledger_path"]) as db:
        value = json.loads(db.execute("SELECT value FROM children WHERE number=1").fetchone()[0])
        value["request_binding"]["slot"] = "correct-control.r0.inventory.0"
        db.execute(
            "UPDATE children SET value=?,value_hash=? WHERE number=1",
            (p.encoded(value).decode(), p.digest(value)),
        )
    with pytest.raises(GateFailure, match="PARENT_BINDING_MISMATCH"):
        run.reports(rig["root"])


def test_private_fact_record_cannot_follow_symlink(tmp_path):
    original = tmp_path / "source"
    original.write_text("unrelated existing content")
    alias = tmp_path / "alias"
    alias.symlink_to(original)
    with pytest.raises(GateFailure, match="UNSAFE_PATH"):
        run.private_record(alias, {"pass": True})
    assert original.read_text() == "unrelated existing content"
