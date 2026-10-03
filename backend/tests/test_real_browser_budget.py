"""Offline tests of the opt-in real browser acceptance budget."""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from app.services.provider_gateway import ProviderError, StructuredResult

SPEC = importlib.util.spec_from_file_location(
    "real_browser_server",
    Path(__file__).resolve().parents[2] / "scripts/acceptance_support/serve_real_browser.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_browser_budget_counts_actual_adapter_attempts_and_rejects_overflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EDUMIND_PROVIDER_MODEL", "offline-test")
    monkeypatch.setenv("EDUMIND_PROVIDER_BASE_URL", "https://invalid.example")
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "offline-secret-not-to-export")
    output = tmp_path / "ledger.json"
    budget = MODULE.Budget(output, 1)

    class Adapter:
        calls = 0

        async def generate_structured(self, request: object) -> StructuredResult:
            self.calls += 1
            return StructuredResult(value={}, model_id="offline-test")

    adapter = Adapter()
    counted = MODULE.CountingAdapter(adapter, budget)
    asyncio.run(counted.generate_structured(object()))
    with pytest.raises(ProviderError):
        asyncio.run(counted.generate_structured(object()))
    assert adapter.calls == 1
    stored = json.loads(output.read_text())
    assert len(stored["provider_calls"]) == 1
    assert stored["provider_calls"][0]["status"] == "completed"
    assert "offline-secret" not in output.read_text()
    with pytest.raises(FileExistsError):
        MODULE.Budget(output, 1)
