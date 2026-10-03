"""Fixed denominator and failure accounting; strictly offline."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from catalog_acceptance_protocol import p95  # noqa: E402


def test_missing_and_failed_slots_remain_in_denominator():
    rows = [{"ok": True, "s": 1} for _ in range(18)]
    assert p95(rows, "s", 20) == "+inf"
    assert p95(rows + [{"ok": True, "s": 1}], "s", 20) == 1
    assert p95(rows + [{"ok": False, "s": 0}, {"ok": False, "s": 0}], "s", 20) == "+inf"
    assert p95([], "s", 20) == "+inf"


def test_nearest_rank_and_boundaries():
    assert p95([{"ok": True, "s": i} for i in range(1, 21)], "s", 20) == 19
    assert p95([{"ok": True, "s": 2} for _ in range(100)], "s", 100) == 2
    with pytest.raises(ValueError):
        p95([{"ok": True, "s": 1}], "s", 0)
    with pytest.raises(ValueError):
        p95([{"ok": True, "s": 1}] * 21, "s", 20)


def test_nonfinite_measurement_cannot_be_success():
    assert p95([{"ok": True, "s": float("inf")}], "s", 1) == "+inf"
    assert p95([{"ok": True, "s": float("nan")}], "s", 1) == "+inf"
