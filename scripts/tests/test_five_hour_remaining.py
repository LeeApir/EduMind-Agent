"""Offline scope/limit checks for the explicitly authorized six-case continuation."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_five_hour_remaining as continuation  # noqa: E402
import acceptance_support.five_hour_runtime as kernel  # noqa: E402


@pytest.fixture
def selected(monkeypatch):
    monkeypatch.setattr(kernel, "ORDER", list(continuation.ORDER))
    return continuation.ORDER


def finish(ledger, name, count):
    ledger.start_case(name)
    for _ in range(count):
        n = ledger.reserve(name, "a" * 64)
        ledger.complete_call(n, "b" * 64)
    ledger.finish_case(name, "c" * 64)
    ledger.assess(name, "d" * 64)


def test_new_ledger_has_only_six_pending_cases(tmp_path, selected):
    ledger = kernel.RunLedger(
        tmp_path / "new.sqlite", "e" * 64, t0=1000, now=lambda: 1000
    )
    assert [(c[0], c[1]) for c in ledger.snapshot()["cases"]] == [
        (n, "pending") for n in selected
    ]
    assert not ledger.snapshot()["calls"]
    with pytest.raises(ValueError, match="UNKNOWN_CASE"):
        ledger.start_case("R02")
    with pytest.raises(ValueError, match="PREVIOUS_GPT"):
        ledger.start_case("A01")


def test_fifty_is_implied_by_frozen_baselines_and_sixteen_extras(tmp_path, selected):
    ledger = kernel.RunLedger(
        tmp_path / "new.sqlite", "e" * 64, t0=1000, now=lambda: 1000
    )
    for name, count in zip(selected, [1, 1, 20, 12, 8, 8], strict=True):
        finish(ledger, name, count)
    assert len(ledger.snapshot()["calls"]) == 50
    # Every case is used; neither replay nor a hidden seventh case can reserve more.
    with pytest.raises(ValueError, match="REPLAY"):
        ledger.start_case("A04")


def test_old_clock_not_reset_and_failed_case_not_replayed(tmp_path, selected):
    now = [1000]
    ledger = kernel.RunLedger(
        tmp_path / "new.sqlite", "e" * 64, t0=0, now=lambda: now[0]
    )
    ledger.start_case("R03")
    ledger.reserve("R03", "a" * 64)
    recovered = kernel.RunLedger(ledger.path, ledger.digest, now=lambda: now[0])
    with pytest.raises(ValueError, match="REPLAY"):
        recovered.start_case("R03")
    now[0] = 16200
    with pytest.raises(ValueError, match="DEADLINE"):
        recovered.start_case("R03")
