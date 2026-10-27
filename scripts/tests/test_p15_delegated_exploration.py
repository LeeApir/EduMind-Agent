"""Assistant delegation is explicitly typed, and original workflow bounds still count."""

# ruff: noqa: E402
import asyncio
import hashlib
import json
import socket
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
from isolated_diagnostics import p15_delegated_exploration as x
import run_p15_split_exploration_r02 as cli


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("No live requests")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


@pytest.fixture
def setup(tmp_path):
    grant = {
        "scope": "PHASE-1.5-T038",
        "package_sha256": "a" * 64,
        "batch_id": "p15-split-experiment-unit-r02",
        "limits": asdict(x.ExplorationLimits()),
        "evidence_ref": "SYNTHETIC_TEST_NOT_AUTHORITY",
        "fee_cap_waiver": True,
    }
    j = x.ExplorationJournal.create(
        tmp_path / "wire", grant["batch_id"], "a" * 64, grant
    )
    yield j, grant
    j.ledger.close()


def test_shared_request_budget_preserves_prior_three_calls(setup):
    j, _ = setup
    for n in range(247):
        j.ledger.reserve(
            j.batch, j.package, str(n), input_max=0, output_max=0, fee_max=0
        )
    assert j.ledger.usage(j.batch)["workflow_requests"] == 250
    with pytest.raises(x.Refused, match="BUDGET_EXHAUSTED"):
        j.ledger.reserve(
            j.batch, j.package, "overflow", input_max=0, output_max=0, fee_max=0
        )


def test_no_human_event_can_be_forged_by_delegation(setup):
    j, _ = setup
    with pytest.raises(x.Refused, match="DELEGATED_ASSISTANT_PROVENANCE_REQUIRED"):
        j.record("human_review", {"reviewer": "Lee"})
    j.record(
        "human_review",
        {
            "reviewer": "Codex assistant",
            "review_type": "delegated_assistant",
            "independent_human_truth": False,
        },
    )
    assert len(j.events("human_review")) == 0 and len(j.events("assistant_review")) == 1
    e = x.SplitExecution(j, [])
    assert e.events("human_review") == j.events("assistant_review")


def test_review_requires_explicit_assistant_role_and_failed_output_cannot_pass(setup):
    j, _ = setup
    e = x.SplitExecution(j, [])
    with pytest.raises(x.Refused, match="DELEGATED_ASSISTANT_PROVENANCE_REQUIRED"):
        e.review({"reviewer": "Lee"})
    raw = json.dumps({"engineering_pass": False}).encode()
    (j.output / "slot.json").write_bytes(raw)
    j.record(
        "slot_output", {"slot_id": "slot", "sha256": hashlib.sha256(raw).hexdigest()}
    )
    with pytest.raises(
        x.Refused, match="ENGINEERING_FAILURE_CANNOT_BE_REVIEWED_AS_SUCCESS"
    ):
        e.review(
            {
                "reviewer": "Codex assistant",
                "review_type": "delegated_assistant",
                "independent_human_truth": False,
            }
        )


def test_shared_deadline_is_not_reset_by_new_batch(setup, monkeypatch):
    j, _ = setup
    monkeypatch.setattr(
        j.ledger, "clock", lambda: (x.PLAN["workflow_deadline_epoch"] + 1, 0)
    )
    with pytest.raises(x.Refused, match="SHARED_WORKFLOW_WALL_LIMIT"):
        j.guard()


def test_stopped_cli_never_reports_pending_review_or_reads_credentials(
    setup, monkeypatch
):
    j, grant = setup
    j.ledger.stop(j.batch, "threshold_unreachable")
    monkeypatch.setattr(cli, "OUTPUT", j.output)
    monkeypatch.setattr(cli, "BATCH", j.batch)
    monkeypatch.setattr(cli, "gate", lambda: ("a" * 64, grant, {}, []))
    monkeypatch.setattr(cli, "database", lambda: "synthetic-unused")

    def deny():
        raise AssertionError("Stopped run must not read credentials")

    monkeypatch.setattr(cli, "keys", deny)
    result = asyncio.run(cli.step())
    assert result["state"] == "stopped" and result["provider_calls_this_step"] == 0


def test_actual_review_import_does_not_claim_independent_human_truth(setup):
    j, _ = setup
    slot = {"slot_id": "slot", "kind": "course"}
    raw = json.dumps({"engineering_pass": True}).encode()
    (j.output / "slot.json").write_bytes(raw)
    j.record(
        "slot_output", {"slot_id": "slot", "sha256": hashlib.sha256(raw).hexdigest()}
    )
    report = {
        "slot_id": "slot",
        "output_sha256": hashlib.sha256(raw).hexdigest(),
        "reviewer": "Codex assistant",
        "review_type": "delegated_assistant",
        "independent_human_truth": False,
        "reviewed_at": "SYNTHETIC_TEST",
        "evidence_ref": "SYNTHETIC_TEST_NOT_REAL_REVIEW",
        "exhaustive_coverage_attested": True,
        "natural_severe_errors": 0,
        "items": [
            {
                "area": a,
                "location": "SYNTHETIC",
                "reason": "SYNTHETIC_TEST",
                "verdict": "pass",
            }
            for a in ["requirements", "learnability", "facts", "answers", "profile"]
        ],
    }
    x.SplitExecution(j, [slot]).review(report)
    assert len(j.events("assistant_review")) == 1 and not j.events("human_review")


def test_generation_role_quota_includes_prior_three_requests(setup):
    j, _ = setup
    for _ in range(179):
        j.record("live_dispatch_reserved", {"provider": "generation"})
    adapter = x.ExplorationAdapter(
        j,
        {"generation": "TEST_ONLY_DEEPSEEK_KEY", "review": "TEST_ONLY_AIAPI_KEY"},
        lambda role: None,
        lambda: None,
    )
    from app.agents.free_course_planning import SCHEMA
    from app.services.provider_gateway import (
        StructuredRequest,
        TextRequest,
        ChatMessage,
    )

    request = StructuredRequest(
        TextRequest((ChatMessage("user", "Synthetic"),)),
        SCHEMA,
        "free_course_plan_generation",
    )
    with pytest.raises(x.Refused, match="SHARED_ROLE_REQUEST_LIMIT"):
        asyncio.run(adapter.send(None, request, retry_safe=False))
