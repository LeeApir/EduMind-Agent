"""Synthetic authorization only: durable bounded accounting, never live requests."""

import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, Refused, digest  # noqa: E402

PACKAGE = "a" * 64
LIMITS = Limits(2, 200, 200, 20, 600)


@pytest.fixture
def setup(tmp_path):
    clock = [10000.0, 100.0]
    path = tmp_path / "offline.sqlite"
    db = Ledger(path, clock=lambda: tuple(clock))
    approval = {
        "package_sha256": PACKAGE,
        "batch_id": "TEST_ONLY",
        "limits": dict(
            requests=2,
            input_tokens=200,
            output_tokens=200,
            fee_micros=20,
            wall_seconds=600,
        ),
        "scope": "PHASE-1.5-T038",
        "evidence_ref": "synthetic:NOT_REAL_HUMAN_AUTHORIZATION",
    }
    yield db, path, clock, approval
    db.close()


def start(db, a):
    db.start("TEST_ONLY", PACKAGE, LIMITS, a, pinned_approval_sha256=digest(a))


def reserve(db, key="a", **kw):
    db.reserve(
        "TEST_ONLY",
        PACKAGE,
        key,
        input_max=kw.get("input_max", 100),
        output_max=kw.get("output_max", 100),
        fee_max=kw.get("fee_max", 10),
    )


def test_no_approval_or_changed_binding_cannot_start(setup):
    db, _, _, a = setup
    for approval, pin in [
        (None, ""),
        (a, "0" * 64),
        ({**a, "batch_id": "other"}, digest({**a, "batch_id": "other"})),
        ({**a, "package_sha256": "b" * 64}, digest({**a, "package_sha256": "b" * 64})),
    ]:
        with pytest.raises(Refused):
            db.start("TEST_ONLY", PACKAGE, LIMITS, approval, pinned_approval_sha256=pin)
    assert db.db.execute("SELECT count(*) FROM batches").fetchone()[0] == 0


def test_start_reopen_duplicate_send_and_receipt_append_only(setup):
    db, path, clock, a = setup
    start(db, a)
    reserve(db)
    db.mark_sent("TEST_ONLY", PACKAGE, "a")
    other = Ledger(path, clock=lambda: tuple(clock))
    try:
        with pytest.raises(Refused, match="ALREADY_STARTED"):
            start(other, a)
        with pytest.raises(Refused, match="ALREADY_RESERVED"):
            reserve(other)
        with pytest.raises(Refused, match="NOT_NEW_RESERVED"):
            other.mark_sent("TEST_ONLY", PACKAGE, "a")
        assert other.usage("TEST_ONLY") == dict(
            requests=1, input_tokens=100, output_tokens=100, fee_micros=10
        )
        with pytest.raises(sqlite3.IntegrityError):
            other.db.execute("DELETE FROM receipts")
        with pytest.raises(sqlite3.IntegrityError):
            other.db.execute("UPDATE batches SET limits_json='{}'")
    finally:
        other.close()


@pytest.mark.parametrize(
    "field,value", [("input_max", 201), ("output_max", 201), ("fee_max", 21)]
)
def test_reservation_upper_bounds_stop_before_send(setup, field, value):
    db, _, _, a = setup
    start(db, a)
    with pytest.raises(Refused, match="BUDGET_EXHAUSTED"):
        reserve(db, **{field: value})
    assert db.usage("TEST_ONLY")["requests"] == 0
    assert db.db.execute("SELECT state FROM batches").fetchone()[0] == "stopped"
    with pytest.raises(Refused, match="STOPPED"):
        reserve(db)


def test_request_count_not_refunded_by_zero_cost_not_executed(setup):
    db, _, _, a = setup
    start(db, a)
    for key in ["a", "b"]:
        reserve(db, key)
        db.settle(
            "TEST_ONLY",
            key,
            outcome="not_executed",
            proof_sha256="c" * 64,
            input_used=0,
            output_used=0,
            fee_used=0,
        )
    with pytest.raises(Refused, match="BUDGET_EXHAUSTED"):
        reserve(db, "c")
    assert db.usage("TEST_ONLY") == dict(
        requests=2, input_tokens=0, output_tokens=0, fee_micros=0
    )


def test_unknown_keeps_full_reservation_stops_and_late_settlement_never_reopens(setup):
    db, _, _, a = setup
    start(db, a)
    reserve(db)
    db.mark_sent("TEST_ONLY", PACKAGE, "a")
    db.settle("TEST_ONLY", "a", outcome="unknown")
    assert db.usage("TEST_ONLY")["fee_micros"] == 10
    with pytest.raises(Refused, match="STOPPED"):
        reserve(db, "b")
    db.settle(
        "TEST_ONLY",
        "a",
        outcome="complete",
        proof_sha256="c" * 64,
        input_used=20,
        output_used=30,
        fee_used=2,
    )
    assert db.usage("TEST_ONLY")["fee_micros"] == 2
    with pytest.raises(Refused, match="STOPPED"):
        reserve(db, "b")


@pytest.mark.parametrize(
    "delta", [(601, 601), (-1, 1), (1, -1), (20, 1), (float("nan"), 1)]
)
def test_deadline_and_clock_anomaly_persist_across_reopen(setup, delta):
    db, path, clock, a = setup
    start(db, a)
    clock[0] += delta[0]
    clock[1] += delta[1]
    with pytest.raises(Refused):
        reserve(db)
    other = Ledger(path, clock=lambda: (10001, 101))
    try:
        assert other.db.execute("SELECT state FROM batches").fetchone()[0] == "stopped"
        with pytest.raises(Refused, match="STOPPED"):
            reserve(other)
    finally:
        other.close()


def test_config_change_and_late_response_stop(setup):
    db, _, clock, a = setup
    start(db, a)
    reserve(db)
    db.mark_sent("TEST_ONLY", PACKAGE, "a")
    clock[0] += 121
    clock[1] += 121
    db.settle(
        "TEST_ONLY",
        "a",
        outcome="complete",
        proof_sha256="c" * 64,
        input_used=10,
        output_used=10,
        fee_used=1,
    )
    assert db.db.execute("SELECT reason FROM batches").fetchone()[0] == "CALL_DEADLINE"
    with pytest.raises(Refused):
        reserve(db, "b")


def test_changed_package_stops_even_without_reservation(setup):
    db, _, _, a = setup
    start(db, a)
    with pytest.raises(Refused, match="CONFIG_CHANGED"):
        db.reserve("TEST_ONLY", "b" * 64, "a", input_max=1, output_max=1, fee_max=0)
    assert db.usage("TEST_ONLY")["requests"] == 0


def test_proof_missing_or_oversized_usage_never_refunds(setup):
    db, _, _, a = setup
    start(db, a)
    reserve(db)
    db.mark_sent("TEST_ONLY", PACKAGE, "a")
    with pytest.raises(Refused, match="PROOF"):
        db.settle(
            "TEST_ONLY",
            "a",
            outcome="complete",
            input_used=1,
            output_used=1,
            fee_used=0,
        )
    with pytest.raises(Refused, match="OVERFLOW"):
        db.settle(
            "TEST_ONLY",
            "a",
            outcome="complete",
            proof_sha256="c" * 64,
            input_used=101,
            output_used=1,
            fee_used=0,
        )
    assert db.usage("TEST_ONLY")["input_tokens"] == 100
    assert db.db.execute("SELECT reason FROM batches").fetchone()[0] == "USAGE_OVERFLOW"


@pytest.mark.parametrize(
    "reason",
    [
        "natural_severe_error",
        "security_incident",
        "independence_contaminated",
        "threshold_unreachable",
        "human_pause",
    ],
)
def test_explicit_stop_is_durable_and_cannot_restart(setup, reason):
    db, _, _, a = setup
    start(db, a)
    db.halt("TEST_ONLY", reason)
    with pytest.raises(Refused, match="ALREADY_STARTED"):
        start(db, a)
    with pytest.raises(Refused, match="STOPPED"):
        reserve(db)


def test_concurrent_reservations_cannot_overrun_shared_budget(setup):
    db, path, clock, a = setup
    start(db, a)

    def once(i):
        conn = Ledger(path, clock=lambda: tuple(clock))
        try:
            reserve(conn, str(i))
            return True
        except Refused:
            return False
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(once, range(4)))
    assert sum(results) == 2
    assert db.usage("TEST_ONLY")["requests"] == 2
