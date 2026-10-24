"""Regression: optional description:null must not be confused with core Schema drift."""

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_p15_direct_relay_once_results as p  # noqa: E402


def test_actual_direct_observation():
    assert p.check()["count_equivalence_tested"] is False


@pytest.mark.parametrize(
    "change", ["description_null", "type", "name", "strict", "schema"]
)
def test_benign_description_and_actual_core_changes(change):
    expected = p.read(p.BASE / "request.json")["text"]["format"]
    actual = copy.deepcopy(expected)
    if change == "description_null":
        actual["description"] = None
    elif change == "strict":
        actual["strict"] = False
    elif change == "schema":
        actual["schema"] = {"type": "string"}
    else:
        actual[change] = "changed"
    assert p.core_schema_matches(expected, actual) is (change == "description_null")
