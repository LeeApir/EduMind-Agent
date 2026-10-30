"""Offline durability and local budget tests, no HTTP or credentials."""

import pytest
import json

from scripts.isolated_diagnostics.p15_reservation_v2 import Ledger, ReservationError


def test_reserve_send_settle_and_durable_budget(tmp_path):
    path = tmp_path / "ledger.sqlite"
    ledger = Ledger.create(
        path, input_budget=100, output_budget=20, calls=2, deadline=100, clock=lambda: 1
    )
    ticket = ledger.reserve(b"request", 60, 10)
    with pytest.raises(ReservationError):
        ledger.sent(ticket, b"other")
    ledger.sent(ticket, b"request")
    with pytest.raises(ReservationError):
        ledger.sent(ticket, b"request")
    ledger.settle(ticket, b"response", 50, 9)
    restored = Ledger(path, clock=lambda: 1)
    with pytest.raises(ReservationError, match="BUDGET"):
        restored.reserve(b"next", 41, 10)
    assert restored.summary()["input_reserved"] == 60


@pytest.mark.parametrize("state", ["reserved", "sent"])
def test_unknown_keeps_occupied_budget_and_cannot_restart(tmp_path, state):
    path = tmp_path / "ledger.sqlite"
    ledger = Ledger.create(
        path, input_budget=100, output_budget=20, calls=2, deadline=100, clock=lambda: 1
    )
    ticket = ledger.reserve(b"request", 60, 10)
    if state == "sent":
        ledger.sent(ticket, b"request")
    restored = Ledger(path, clock=lambda: 1)
    with pytest.raises(ReservationError, match="PENDING_OR_UNKNOWN"):
        restored.reserve(b"next", 1, 1)
    restored.stop()
    assert restored.summary()["attempts"][0]["state"] == (
        "unknown" if state == "sent" else "cancelled"
    )
    assert restored.summary()["input_reserved"] == 60
    with pytest.raises(ReservationError):
        restored.reserve(b"next", 1, 1)
    with pytest.raises(ReservationError):
        Ledger.create(
            path,
            input_budget=100,
            output_budget=20,
            calls=2,
            deadline=100,
            clock=lambda: 1,
        )


def test_overuse_retains_evidence_and_stops(tmp_path):
    now = [1.0]
    ledger = Ledger.create(
        tmp_path / "ledger.sqlite",
        input_budget=100,
        output_budget=20,
        calls=2,
        deadline=10,
        clock=lambda: now[0],
    )
    ticket = ledger.reserve(b"request", 60, 10)
    ledger.sent(ticket, b"request")
    ledger.settle(ticket, b"response", 61, 2)
    assert ledger.summary()["status"] == "stopped"
    assert ledger.summary()["attempts"][0]["state"] == "over_budget"
    assert ledger.response_bytes(ticket) == b"response"
    with pytest.raises(ReservationError):
        ledger.reserve(b"next", 1, 1)


@pytest.mark.parametrize("trigger", ["stop", "deadline"])
def test_late_evidence_is_saved_without_resuming(tmp_path, trigger):
    now = [1.0]
    ledger = Ledger.create(
        tmp_path / "ledger.sqlite",
        input_budget=100,
        output_budget=20,
        calls=2,
        deadline=10,
        clock=lambda: now[0],
    )
    ticket = ledger.reserve(b"request", 60, 10)
    ledger.sent(ticket, b"request")
    if trigger == "stop":
        ledger.stop()
    else:
        now[0] = 10
    ledger.settle(ticket, b"late-response", 61, 11)
    summary = ledger.summary()
    assert summary["status"] == "stopped"
    assert summary["attempts"][0]["state"] == "late_over_budget"
    assert ledger.response_bytes(ticket) == b"late-response"
    assert summary["attempts"][0]["input_used"] == 61
    with pytest.raises(ReservationError):
        ledger.reserve(b"next", 1, 1)
    with pytest.raises(ReservationError):
        ledger.settle(ticket, b"another", 1, 1)


def test_unsent_cancelled_cannot_supply_late_response(tmp_path):
    ledger = Ledger.create(
        tmp_path / "ledger.sqlite",
        input_budget=100,
        output_budget=20,
        calls=2,
        deadline=10,
        clock=lambda: 1,
    )
    ticket = ledger.reserve(b"request", 60, 10)
    ledger.stop()
    with pytest.raises(ReservationError, match="SETTLEMENT"):
        ledger.settle(ticket, b"not-sent", 1, 1)


def test_late_under_reservation_is_recorded_and_remains_stopped(tmp_path):
    path = tmp_path / "ledger.sqlite"
    ledger = Ledger.create(
        path, input_budget=100, output_budget=20, calls=2, deadline=10, clock=lambda: 1
    )
    ticket = ledger.reserve(b"request", 60, 10)
    ledger.sent(ticket, b"request")
    ledger.stop()
    ledger.settle(ticket, b"late", 30, 5)
    restored = Ledger(path, clock=lambda: 1)
    assert restored.summary()["status"] == "stopped"
    assert restored.summary()["attempts"][0]["state"] == "late_evidence"
    assert restored.response_bytes(ticket) == b"late"
    with pytest.raises(ReservationError):
        restored.sent(ticket, b"request")


def test_settled_request_cannot_be_reissued(tmp_path):
    ledger = Ledger.create(
        tmp_path / "ledger.sqlite",
        input_budget=100,
        output_budget=20,
        calls=2,
        deadline=10,
        clock=lambda: 1,
    )
    ticket = ledger.reserve(b"request", 20, 5)
    ledger.sent(ticket, b"request")
    ledger.settle(ticket, b"reply", 10, 2)
    with pytest.raises(ReservationError, match="DUPLICATE_REQUEST"):
        ledger.reserve(b"request", 20, 5)
    json.dumps(ledger.summary())


@pytest.mark.parametrize("bad_deadline", [float("nan"), float("inf"), True])
def test_invalid_window_does_not_create_ledger(tmp_path, bad_deadline):
    with pytest.raises(ReservationError, match="INIT"):
        Ledger.create(
            tmp_path / "ledger.sqlite",
            input_budget=100,
            output_budget=20,
            calls=2,
            deadline=bad_deadline,
            clock=lambda: 1,
        )
