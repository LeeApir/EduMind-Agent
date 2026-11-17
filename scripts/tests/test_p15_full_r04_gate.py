"""Exact new whole-batch scope/window approval is required before side effects."""

# ruff: noqa: E402
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import run_p15_full_diagnostic_r04 as cli
from test_p15_full_diagnostic_r04 import journal as journal, course_pending


def test_pending_full_batch_cannot_read_keys_database_or_create_output(monkeypatch):
    monkeypatch.setattr(cli, "keys", lambda: pytest.fail("No keys before approval"))
    monkeypatch.setattr(
        cli, "database", lambda: pytest.fail("No database before approval")
    )
    assert not cli.OUTPUT.exists()
    with pytest.raises(
        cli.Refused, match="EXACT_FULL_BATCH_AND_NEW_WINDOW_APPROVAL_REQUIRED"
    ):
        asyncio.run(cli.step())
    assert not cli.OUTPUT.exists()


@pytest.mark.parametrize(
    "fault",
    [
        "expired",
        "oversized_window",
        "future_start",
        "missing_transfer",
        "missing_contract",
        "wrong_hash",
        "old_budget",
    ],
)
def test_other_scope_expiry_or_old_limits_never_reach_dependencies(monkeypatch, fault):
    package, grant, _, _ = cli.gate()
    raw = (cli.BASE / "execution-approval.json").read_bytes()
    original_parse = cli.parse
    grant.update(
        approved=True,
        package_sha256=package,
        new_time_window_approved=True,
        full_review_contract_approved=True,
        synthetic_course_transfer_approved=True,
        fee_cap_waiver=True,
        token_bound_proof_waiver=True,
        human_message="SYNTHETIC ONLY",
        evidence_ref="NO HUMAN AUTHORITY",
        window_start_epoch=time.time() - 10,
        window_deadline_epoch=time.time() + 10780,
    )
    if fault == "expired":
        grant.update(
            window_start_epoch=time.time() - 10800,
            window_deadline_epoch=time.time() - 1,
        )
    if fault == "oversized_window":
        grant["window_deadline_epoch"] = time.time() + 10801
    if fault == "future_start":
        grant["window_start_epoch"] = time.time() + 100
    if fault == "missing_transfer":
        grant["synthetic_course_transfer_approved"] = False
    if fault == "missing_contract":
        grant["full_review_contract_approved"] = False
    if fault == "wrong_hash":
        grant["package_sha256"] = "f" * 64
    if fault == "old_budget":
        grant["limits"] = {**grant["limits"], "requests": 14}
    monkeypatch.setattr(
        cli,
        "parse",
        lambda content: grant if content == raw else original_parse(content),
    )
    monkeypatch.setattr(cli, "keys", lambda: pytest.fail("Unexpected credential read"))
    monkeypatch.setattr(
        cli, "database", lambda: pytest.fail("Unexpected database read")
    )
    with pytest.raises(cli.Refused):
        asyncio.run(cli.step())


def test_local_report_rejection_never_uses_provider_or_stops_valid_batch(
    request, monkeypatch, tmp_path
):
    j = request.getfixturevalue("journal")
    course_pending(j)
    monkeypatch.setattr(
        cli,
        "gate",
        lambda **kwargs: ("a" * 64, {}, {}, [dict(slot_id="course", kind="course")]),
    )
    monkeypatch.setattr(cli, "OUTPUT", j.output)
    monkeypatch.setattr(cli, "BATCH", j.batch)
    monkeypatch.setattr(cli, "database", lambda: "SYNTHETIC_UNUSED")
    monkeypatch.setattr(cli, "ExplorationLedger", lambda *args: j.ledger)
    monkeypatch.setattr(cli, "keys", lambda: pytest.fail("No keys for local reports"))
    report = tmp_path / "invalid.json"
    report.write_text(json.dumps({"not": "a valid review"}))
    result = asyncio.run(cli.step(review_path=report))
    assert (
        result["state"] == "local_review_rejected_no_calls"
        and result["provider_calls_this_step"] == 0
    )
    db = sqlite3.connect(j.output / "ledger.sqlite")
    try:
        assert db.execute("SELECT state FROM batches").fetchone()[0] == "running"
    finally:
        db.close()
