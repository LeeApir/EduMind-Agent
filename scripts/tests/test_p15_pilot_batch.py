"""Independent hand-authored traces; expectations are never produced by the reducer."""

import json
import socket
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.isolated_diagnostics.p15_pilot_batch import BatchError, reduce_batch

DATA = json.loads(
    (Path(__file__).parent / "fixtures/p15_pilot_batch_manual.json").read_text()
)


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["id"] for c in DATA["cases"]])
def test_independent_handwritten_trace(case):
    initial = deepcopy(DATA["event_pool"]["start"]["payload"])
    ids = DATA["prefixes"][case["prefix"]] + case["append"]
    events = [deepcopy(DATA["event_pool"][key]) for key in ids]
    expected = case["expected"]
    if not expected["accept"]:
        reject_index = ids.index(expected["reject_at"])
        # The prefix must still be valid: rejection is at the independently specified event.
        reduce_batch(initial, events[:reject_index])
        with pytest.raises(BatchError):
            reduce_batch(initial, events[: reject_index + 1])
        return
    state = reduce_batch(initial, events)
    assert state.batch["status"] == expected["status"]
    assert state.batch["position"] == expected["position"]
    if "pending" in expected:
        assert state.batch["pending"] == expected["pending"]
    assert len(state.calls) == expected["reserved_calls"]
    assert (
        sum(c["state"] == "complete" for c in state.calls.values())
        == expected["trusted_settlements"]
    )
    assert state.independent_accepts == expected["independent_accepts"]
    if "call_states" in expected:
        assert {k: v["state"] for k, v in state.calls.items()} == expected[
            "call_states"
        ]
    if "late_slot_observations" in expected:
        assert state.late_slot_observations == expected["late_slot_observations"]


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("No real network in batch tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def journal_fixture(tmp_path):
    # Imported helpers only produce synthetic protocol payloads through HTTPX MockTransport.
    from scripts.tests.test_p15_pilot_wire_execution import e, SPEC

    inputs = dict(
        version="pilot-inputs-v1",
        slots=[
            dict(slot_id="slot", kind="supported", spec=deepcopy(SPEC), question=None)
        ],
    )
    j = e.Journal.start(
        tmp_path / "batch",
        "a" * 64,
        dict(window_started_epoch=0, deadline_epoch=1000),
        inputs,
        clock=lambda: 100,
    )
    yield j, inputs
    j.db.close()


def rechain_database(j, rows):
    from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest

    j.db.execute("DELETE FROM events")
    previous = None
    for sequence, row in enumerate(rows):
        payload = json.loads(row["payload"])
        sha = digest(
            dict(
                seq=sequence,
                kind=row["kind"],
                payload=payload,
                previous=previous,
                epoch=row["epoch"],
            )
        )
        j.db.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?)",
            (
                sequence,
                row["kind"],
                canonical(payload).decode(),
                previous,
                sha,
                row["epoch"],
            ),
        )
        previous = sha


def complete_both(j, inputs):
    from scripts.tests.test_p15_pilot_wire_execution import fake_step, report

    b = fake_step(j, inputs)
    j.accept_report(report(j, b))
    c = fake_step(j, inputs)
    j.accept_report(report(j, c))


@pytest.mark.parametrize(
    "kind", ["reserved", "sent", "settled", "assistant_review", "slot_result"]
)
def test_rehashed_real_epoch_outside_window_is_not_success(journal_fixture, kind):
    from scripts import check_p15_pilot_execution as checker

    j, inputs = journal_fixture
    complete_both(j, inputs)
    rows = [dict(row) for row in j.db.execute("SELECT * FROM events ORDER BY seq")]
    next(row for row in rows if row["kind"] == kind)["epoch"] = 1000.0
    rechain_database(j, rows)
    with pytest.raises(BatchError):
        checker.verify(j.output, "a" * 64)


def test_next_arm_before_exact_assistant_accept_is_rejected(journal_fixture):
    from scripts import check_p15_pilot_execution as checker

    j, inputs = journal_fixture
    complete_both(j, inputs)
    rows = [dict(row) for row in j.db.execute("SELECT * FROM events ORDER BY seq")]
    index = next(
        i
        for i, row in enumerate(rows)
        if row["kind"] == "reserved" and json.loads(row["payload"])["arm"] == "C"
    )
    premature = rows.pop(index)
    accept_index = next(
        i for i, row in enumerate(rows) if row["kind"] == "assistant_review"
    )
    rows.insert(accept_index, premature)
    rechain_database(j, rows)
    with pytest.raises(BatchError, match="BATCH_RESERVE_STATE_OR_TIME"):
        checker.verify(j.output, "a" * 64)


def test_independent_stop_cannot_be_followed_by_valid_later_slots(journal_fixture):
    from scripts import check_p15_pilot_execution as checker

    j, inputs = journal_fixture
    complete_both(j, inputs)
    rows = [dict(row) for row in j.db.execute("SELECT * FROM events ORDER BY seq")]
    review = next(row for row in rows if row["kind"] == "assistant_review")
    payload = json.loads(review["payload"])
    payload["decision"] = "stop"
    review["payload"] = json.dumps(payload)
    (j.output / "assistant-00.json").write_text(json.dumps(payload))
    rechain_database(j, rows)
    with pytest.raises(BatchError, match="BATCH_RESERVE_STATE_OR_TIME"):
        checker.verify(j.output, "a" * 64)


def test_sender_cannot_bypass_batch_rule_by_recording_directly(journal_fixture):
    from scripts.tests.test_p15_pilot_wire_execution import fake_step

    j, inputs = journal_fixture
    fake_step(j, inputs)
    before = j.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    forged = dict(
        ticket="call-002",
        slot_id="slot",
        arm="C",
        stage="pilot_plan",
        request_sha256="c" * 64,
    )
    with pytest.raises(BatchError):
        j.record("reserved", forged)
    assert j.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before
    assert j.batch()["status"] == "awaiting_assistant"
    j.stop("explicit_stop")
    with pytest.raises(BatchError):
        j.record("reserved", forged)
    assert j.batch()["status"] == "stopped"


def test_late_candidate_is_evidence_not_checkpoint_or_success(
    journal_fixture, monkeypatch
):
    from scripts.tests.test_p15_pilot_wire_execution import fake_step
    from scripts import check_p15_pilot_execution as checker

    j, inputs = journal_fixture
    original = j.finish

    def late_finish(result):
        j.clock = lambda: 1001
        return original(result)

    monkeypatch.setattr(j, "finish", late_finish)
    fake_step(j, inputs)
    assert j.batch()["status"] == "stopped" and j.batch()["position"] == 0
    assert j.batch()["pending"] is None
    result = checker.verify(j.output, "a" * 64)
    assert result["late_slot_observations"] == 1
    assert result["first_e2e"]["numerators"] == {"B": 0, "C": 0}
    assert result["initial_structure"]["numerators"] == {"B": 0, "C": 0}


def test_reservation_clock_race_is_atomic(journal_fixture):
    j, _ = journal_fixture
    readings = iter([100, 100, 1001])
    j.clock = lambda: next(readings)
    with pytest.raises(BatchError, match="BATCH_RESERVE_STATE_OR_TIME"):
        j.reserve("slot", "B", "pilot_baseline", {})
    assert j.db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0
    assert (
        j.db.execute("SELECT COUNT(*) FROM events WHERE kind='reserved'").fetchone()[0]
        == 0
    )


def test_sender_rejects_database_state_not_derived_from_receipts(journal_fixture):
    from scripts.tests.test_p15_pilot_wire_execution import fake_step
    from scripts.isolated_diagnostics.p15_agent_pilot import PilotError

    j, inputs = journal_fixture
    fake_step(j, inputs)
    j.update(status="active", position=1, pending=None)
    with pytest.raises(PilotError, match="BATCH_PROJECTION_MISMATCH"):
        j.guard()
