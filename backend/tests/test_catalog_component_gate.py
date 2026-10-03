"""Offline gate must reject incomplete core or any extra network/Provider activity."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from verify_catalog_acceptance import verify_components  # noqa: E402


@pytest.mark.parametrize(
    "core",
    [
        {"provider_requests": 1, "external_attempts": []},
        {"provider_requests": 0, "external_attempts": ["blocked external attempt"]},
        {"provider_requests": 0, "external_attempts": [], "fatal_error": {"type": "TestFailure"}},
    ],
)
def test_core_failure_cannot_be_hidden_by_passing_metric_component(core):
    with pytest.raises(AssertionError):
        verify_components({}, {}, {}, core)
