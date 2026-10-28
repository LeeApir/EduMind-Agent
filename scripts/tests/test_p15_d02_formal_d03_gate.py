"""Exact new whole-batch scope/window approval is required before side effects."""

# ruff: noqa: E402
import asyncio
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import run_p15_d02_formal_d03 as cli


def test_pending_full_batch_cannot_read_keys_database_or_create_output(monkeypatch):
    monkeypatch.setattr(cli, "keys", lambda: pytest.fail("No keys before approval"))
    monkeypatch.setattr(
        cli, "database", lambda: pytest.fail("No database before approval")
    )
    assert not cli.OUTPUT.exists()
    with pytest.raises(cli.Refused, match="EXACT_D02_AND_NEW_WINDOW_APPROVAL_REQUIRED"):
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
        "old_policy",
        "human_truth",
        "wrong_reviewer",
        "missing_adr0040",
        "missing_stop_rule",
        "missing_patch_scope",
        "missing_test_first",
    ],
)
def test_other_scope_expiry_or_old_limits_never_reach_dependencies(monkeypatch, fault):
    package, grant, _, _ = cli.gate()
    raw = (cli.BASE / "execution-approval.json").read_bytes()
    original_parse = cli.parse
    grant.update(
        approved=True,
        adr0040_A_B_scope_extension_approved=True,
        planning_v2_patch_scope_approved=True,
        test_before_reassessment_approved=True,
        final_one_shot_stop_rule_approved=True,
        package_sha256=package,
        new_time_window_approved=True,
        full_review_contract_approved=True,
        synthetic_course_transfer_approved=True,
        fee_cap_waiver=True,
        token_bound_proof_waiver=True,
        human_message="SYNTHETIC ONLY",
        evidence_ref="NO HUMAN AUTHORITY",
        window_start_epoch=time.time() - 10,
        window_deadline_epoch=time.time() + 1780,
    )
    if fault == "expired":
        grant.update(
            window_start_epoch=time.time() - 1800,
            window_deadline_epoch=time.time() - 1,
        )
    if fault == "oversized_window":
        grant["window_deadline_epoch"] = time.time() + 1801
    if fault == "future_start":
        grant["window_start_epoch"] = time.time() + 100
    if fault == "missing_transfer":
        grant["synthetic_course_transfer_approved"] = False
    if fault == "missing_contract":
        grant["full_review_contract_approved"] = False
    if fault == "wrong_hash":
        grant["package_sha256"] = "f" * 64
    if fault == "human_truth":
        grant["independent_human_truth"] = True
    if fault == "wrong_reviewer":
        grant["reviewer"] = "Lee"
    if fault == "missing_adr0040":
        grant["adr0040_A_B_scope_extension_approved"] = False
    if fault == "missing_patch_scope":
        grant["planning_v2_patch_scope_approved"] = False
    if fault == "missing_test_first":
        grant["test_before_reassessment_approved"] = False
    if fault == "missing_stop_rule":
        grant["final_one_shot_stop_rule_approved"] = False
    if fault == "old_policy":
        grant["observability_policy_version"] = "old-echo-required-policy"
    if fault == "old_budget":
        grant["limits"] = {**grant["limits"], "requests": 250}
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
