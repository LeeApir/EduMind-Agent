"""Pending exact approval and expired windows fail before side effects."""

# ruff: noqa: E402
import asyncio
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
import run_p15_course_recheck_r03 as cli


def test_pending_package_cannot_read_keys_or_create_output(monkeypatch):
    monkeypatch.setattr(
        cli, "keys", lambda: pytest.fail("Credential read before approval")
    )
    monkeypatch.setattr(
        cli, "database", lambda: pytest.fail("Database accessed before approval")
    )
    assert not cli.OUTPUT.exists()
    with pytest.raises(
        cli.Refused, match="EXACT_FIRST_SLOT_AND_NEW_WINDOW_APPROVAL_REQUIRED"
    ):
        asyncio.run(cli.step())
    assert not cli.OUTPUT.exists()


@pytest.mark.parametrize(
    "fault",
    ["expired", "oversized_window", "future_start", "missing_transfer", "wrong_hash"],
)
def test_synthetic_grant_cannot_bypass_expiry_scope_or_exact_hash(monkeypatch, fault):
    package, _, _, _ = cli.gate()
    oldparse = cli.parse
    registry = (cli.BASE / "execution-approval.json").read_bytes()
    grant = oldparse(registry)
    grant.update(
        approved=True,
        package_sha256=package,
        new_time_window_approved=True,
        synthetic_course_transfer_approved=True,
        fee_cap_waiver=True,
        token_bound_proof_waiver=True,
        human_message="SYNTHETIC TEST ONLY",
        evidence_ref="NOT HUMAN AUTHORITY",
        window_start_epoch=time.time() - 10,
        window_deadline_epoch=time.time() + 800,
    )
    if fault == "expired":
        grant.update(
            window_start_epoch=time.time() - 1000,
            window_deadline_epoch=time.time() - 100,
        )
    if fault == "oversized_window":
        grant["window_deadline_epoch"] = time.time() + 901
    if fault == "future_start":
        grant["window_start_epoch"] = time.time() + 100
    if fault == "missing_transfer":
        grant["synthetic_course_transfer_approved"] = False
    if fault == "wrong_hash":
        grant["package_sha256"] = "f" * 64
    monkeypatch.setattr(
        cli, "parse", lambda raw: grant if raw == registry else oldparse(raw)
    )
    monkeypatch.setattr(cli, "keys", lambda: pytest.fail("Unexpected key read"))
    monkeypatch.setattr(cli, "database", lambda: pytest.fail("Unexpected DB read"))
    with pytest.raises(cli.Refused):
        asyncio.run(cli.step())
