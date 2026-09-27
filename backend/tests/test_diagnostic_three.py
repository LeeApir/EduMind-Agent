"""Diagnostic guards without any external Provider."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs/acceptance"))

from first_screen_diagnostics import CURRENT
from serve_diagnostic_three import DiagnosticAdapter, DiagnosticBudget, TraceMiddleware

from app.services.provider_gateway import ProviderError, ProviderErrorCode, TextDelta


def budget(tmp_path, monkeypatch):
    import serve_real_browser

    class Settings:
        model = "mock-model"

    monkeypatch.setattr(serve_real_browser, "get_provider_settings", Settings)
    return DiagnosticBudget(tmp_path / "ledger.json", 36)


def test_cap_includes_failed_attempts(tmp_path, monkeypatch):
    counter = budget(tmp_path, monkeypatch)
    for _ in range(36):
        counter.reserve("structured").update(status="failed", error_code="TIMEOUT")
        counter.save()
    with pytest.raises(ProviderError) as error:
        counter.reserve("stream")
    assert error.value.code == ProviderErrorCode.CONFIGURATION_MISSING
    assert len(counter.calls) == 36


def test_quota_stops_before_retry(tmp_path, monkeypatch):
    counter = budget(tmp_path, monkeypatch)

    class Adapter:
        async def generate_structured(self, request):
            raise ProviderError(ProviderErrorCode.RATE_LIMITED)

    adapter = DiagnosticAdapter(Adapter(), counter)
    with pytest.raises(ProviderError):
        asyncio.run(adapter.generate_structured(None))
    with pytest.raises(ProviderError) as error:
        asyncio.run(adapter.generate_structured(None))
    assert error.value.code == ProviderErrorCode.CONFIGURATION_MISSING
    assert len(counter.calls) == 1


def test_stream_time_and_context_reset(tmp_path, monkeypatch):
    counter = budget(tmp_path, monkeypatch)

    class Adapter:
        async def stream_text(self, request):
            await asyncio.sleep(0.02)
            yield TextDelta("指针保存地址。")

    async def app(scope, receive, send):
        async for _ in DiagnosticAdapter(Adapter(), counter).stream_text(None):
            pass
        await send({"type": "http.response.start", "status": 200})

    middleware = TraceMiddleware(app, tmp_path / "trace.json")

    async def exercise():
        async def send(message):
            pass

        await middleware({"type": "http", "path": "/api/learning-sessions"}, None, send)
        assert CURRENT.get() is None

    asyncio.run(exercise())
    entry = middleware.records[0]["spans"][0]
    assert entry["first_delta_ns"] - entry["start_ns"] >= 15_000_000
    assert entry["end_ns"] >= entry["first_delta_ns"]
    assert counter.calls[0]["request"] == "learning"


def test_independent_semantics_preserves_unknown_and_selects_later():
    from first_screen_v2 import ParagraphClock, qualify

    clock = ParagraphClock()
    clock.feed("先看代码。\n\n", 10)
    clock.feed("指针保存地址。\n\n", 20)
    decisions = {
        "1": {"sha256": clock.candidates[0]["sha256"], "verdict": "intro", "reason": "导语"},
        "2": {"sha256": clock.candidates[1]["sha256"], "verdict": "teaching", "reason": "知识"},
    }
    result = qualify(clock.candidates, decisions)
    assert result["first_teaching_candidate"]["completed_ns"] == 20
    decisions["1"]["verdict"] = "unconfirmed"
    assert qualify(clock.candidates, decisions)["milestone_confirmed"] is False


def test_diagnostic_audit_keeps_all_three_and_never_computes_p95():
    import json

    from audit_diagnostic_three import audit

    directory = Path(__file__).resolve().parents[2] / "docs/acceptance"
    raw, decisions, trace = (
        json.loads((directory / f"mvp-0.2-t035-{name}.json").read_text())
        for name in ("raw", "decisions", "trace")
    )
    result = audit(raw, decisions, trace)
    assert result["formal_acceptance"] is False
    assert len(result["samples"]) == 3
    assert result["samples"][0]["milestone_confirmed"] is False
    assert "teaching_paragraph" not in result["samples"][0]["client_ms"]
    assert result["samples"][1]["milestone_confirmed"] is True
    assert "p95" not in json.dumps(result).lower()
    for item in result["samples"]:
        assert item["recovery_extra_attempts"] == 0
        assert item["physical_connections"] == 0
