"""Offline durability and local budget tests, no HTTP or credentials."""

import pytest

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
    assert restored.summary()["attempts"][0]["state"] == "unknown"
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


def test_overuse_and_late_result_remain_unsettled(tmp_path):
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
    with pytest.raises(ReservationError, match="SETTLEMENT"):
        ledger.settle(ticket, b"response", 61, 2)
    now[0] = 10
    with pytest.raises(ReservationError, match="STOPPED_OR_EXPIRED"):
        ledger.settle(ticket, b"response", 59, 2)
    ledger.stop()
    assert ledger.summary()["attempts"][0]["state"] == "unknown"
