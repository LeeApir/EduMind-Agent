"""Synthetic approvals and outputs only; no actual human signatures or model calls."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_p15_development_diagnostic as cli  # noqa: E402
from acceptance_support.p15_diagnostic_execution import Execution, verify_approval  # noqa: E402
from acceptance_support.p15_diagnostic_ledger import Ledger, Refused  # noqa: E402


@pytest.fixture
def setup(tmp_path):
    manifest = dict(
        batch_id="TEST_ONLY",
        limits=dict(
            requests=4,
            input_tokens=1000,
            output_tokens=1000,
            fee_micros=None,
            wall_seconds=600,
        ),
    )
    approval = dict(
        scope="PHASE-1.5-T038",
        batch_id="TEST_ONLY",
        package_sha256="a" * 64,
        limits=manifest["limits"],
        fee_cap_waiver=True,
        human_message="SYNTHETIC_NOT_AUTHORIZATION",
        reviewer="TEST_ONLY",
        received_at="TEST_ONLY",
        evidence_ref="synthetic",
    )
    ledger = Ledger(tmp_path / "offline.sqlite")
    run = Execution(
        ledger, manifest, "a" * 64, [dict(slot_id="D01", kind="course")], tmp_path
    )
    yield run, approval
    ledger.close()


@pytest.mark.parametrize(
    "field", ["package_sha256", "scope", "limits", "fee_cap_waiver", "human_message"]
)
def test_missing_or_changed_exact_approval(setup, field):
    run, approval = setup
    approval[field] = None
    with pytest.raises(Refused):
        run.start(approval)
    assert not run.events("started")


def human(record):
    return dict(
        **{"slot_id": record["slot_id"], "output_sha256": record["sha256"]},
        reviewer="TEST_ONLY",
        reviewed_at="TEST_ONLY",
        evidence_ref="synthetic",
        exhaustive_coverage_attested=True,
        natural_severe_errors=0,
        items=[
            dict(
                area=a, location="synthetic:/all", reason="fixture only", verdict="pass"
            )
            for a in [
                "requirements",
                "learnability",
                "facts",
                "answers",
                "profile",
                "pair",
            ]
        ],
    )


def test_checkpoint_duplicate_start_and_final_stop(setup):
    run, approval = setup
    run.start(approval)
    with pytest.raises(Refused, match="ALREADY_STARTED"):
        run.start(approval)

    async def fake(slot):
        return {"engineering_pass": True, "slot": slot}

    record = asyncio.run(run.advance(fake))
    with pytest.raises(Refused, match="REVIEW_PENDING"):
        asyncio.run(run.advance(fake))
    wrong = human(record)
    wrong["output_sha256"] = "b" * 64
    with pytest.raises(Refused):
        run.review(wrong)
    run.review(human(record))
    assert asyncio.run(run.advance(fake)) is None
    with pytest.raises(Refused, match="STOPPED"):
        asyncio.run(run.advance(fake))


@pytest.mark.parametrize("mode", ["severe", "unresolved", "engineering", "crash"])
def test_failure_is_durable_no_auto_resend(setup, mode):
    run, approval = setup
    run.start(approval)

    async def fake(slot):
        if mode == "crash":
            raise TimeoutError("fixture")
        return {"engineering_pass": mode != "engineering"}

    if mode == "crash":
        with pytest.raises(TimeoutError):
            asyncio.run(run.advance(fake))
    else:
        record = asyncio.run(run.advance(fake))
        if mode in ["severe", "unresolved"]:
            review = human(record)
            if mode == "severe":
                review["natural_severe_errors"] = 1
            else:
                review["items"][0]["verdict"] = "unresolved"
            run.review(review)
    with pytest.raises(Refused, match="STOPPED"):
        asyncio.run(run.advance(fake))
    assert len(run.events("slot_started")) == 1


def test_interrupted_persisted_slot_cannot_be_replayed(setup):
    run, approval = setup
    run.start(approval)
    run.ledger.record(run.batch, "slot_started", {"slot_id": "D01"})
    with pytest.raises(Refused, match="INTERRUPTED"):
        asyncio.run(run.advance(None))


def test_cli_gate_precedes_credentials_and_side_effects(setup, tmp_path, monkeypatch):
    run, approval = setup
    monkeypatch.setattr(cli, "load_package", lambda _: (run.manifest, run.package))
    with pytest.raises(Refused, match="EXACT_T038"):
        cli.gate(tmp_path)
    with pytest.raises(Refused):
        verify_approval(run.manifest, run.package, None)
    assert not (tmp_path / "execution-approval.json").exists()


@pytest.mark.parametrize(
    "mode", ["one_miss_allowed", "two_misses", "false_block", "low_precision"]
)
def test_human_probe_matching_and_fixed_denominators(setup, mode):
    run, approval = setup
    run.slots = [
        dict(
            slot_id=f"R{i}",
            kind="probe",
            proposed_label="severe" if i < 10 else "correct",
        )
        for i in range(20)
    ]
    run.start(approval)

    async def fake(slot):
        return {"engineering_pass": True}

    for i in range(20):
        record = asyncio.run(run.advance(fake))
        review = human(record)
        review["items"] = [
            dict(
                area="true_positive_or_false_block",
                location="synthetic",
                reason="fixture only",
                verdict="pass",
            )
        ]
        detected = i < 10 and not (i == 0 or (mode == "two_misses" and i == 1))
        review.update(
            severe_detected=detected,
            flagged_correct_control=mode == "false_block" and i == 10,
            findings_total=int(detected) + int(mode == "low_precision"),
            findings_true=int(detected),
            matched_issue_quote="fixture" if detected else None,
        )
        run.review(review)
        if (
            (mode == "two_misses" and i == 1)
            or (mode == "false_block" and i == 10)
            or (mode == "low_precision" and i == 19)
        ):
            with pytest.raises(Refused, match="STOPPED"):
                asyncio.run(run.advance(fake))
            break
    else:
        assert mode == "one_miss_allowed" and asyncio.run(run.advance(fake)) is None


def test_changed_output_stops_before_review_or_next_send(setup):
    run, approval = setup
    run.start(approval)

    async def fake(slot):
        return {"engineering_pass": True}

    record = asyncio.run(run.advance(fake))
    (run.output / "D01.json").write_text("changed")
    with pytest.raises(Refused, match="OUTPUT_CHANGED"):
        run.review(human(record))
    with pytest.raises(Refused, match="STOPPED"):
        asyncio.run(run.advance(fake))
