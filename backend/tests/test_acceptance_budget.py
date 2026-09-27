"""Formal acceptance budget guards, with no external model calls."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs/acceptance"))

from acceptance_budget import GuardedBudget, install_status_guard
from serve_real_browser import CountingAdapter

from app.services import deepseek_responses
from app.services.provider_gateway import ProviderError, ProviderErrorCode


def budget(tmp_path, monkeypatch):
    import serve_real_browser

    class Settings:
        model = "mock-model"

    monkeypatch.setattr(serve_real_browser, "get_provider_settings", Settings)
    return GuardedBudget(tmp_path / "ledger.json", 240)


@pytest.mark.parametrize("status", [401, 402, 403, 429])
def test_http_anomaly_halts_before_another_adapter_attempt(tmp_path, monkeypatch, status):
    counter = budget(tmp_path, monkeypatch)
    monkeypatch.setattr(deepseek_responses, "_check_status", deepseek_responses._check_status)
    install_status_guard(deepseek_responses, counter)

    class Adapter:
        calls = 0

        async def generate_structured(self, request):
            self.calls += 1
            deepseek_responses._check_status(httpx.Response(status))

    original = Adapter()
    adapter = CountingAdapter(original, counter)
    with pytest.raises(ProviderError):
        asyncio.run(adapter.generate_structured(None))
    with pytest.raises(ProviderError) as error:
        asyncio.run(adapter.generate_structured(None))
    assert error.value.code == ProviderErrorCode.CONFIGURATION_MISSING
    assert original.calls == len(counter.calls) == 1
    assert counter.metadata["halted"] == "AUTH_BALANCE_QUOTA"


def test_all_240_attempts_including_failures_count(tmp_path, monkeypatch):
    counter = budget(tmp_path, monkeypatch)
    for _ in range(240):
        counter.reserve("structured").update(status="failed", error_code="TIMEOUT")
        counter.save()
    with pytest.raises(ProviderError):
        counter.reserve("stream")
    assert len(counter.calls) == 240
    assert not counter.metadata.get("halted")


def test_normalized_capability_error_halts(tmp_path, monkeypatch):
    counter = budget(tmp_path, monkeypatch)
    counter.reserve("stream").update(status="failed", error_code="CAPABILITY_UNAVAILABLE")
    counter.save()
    with pytest.raises(ProviderError):
        counter.reserve("structured")
    assert len(counter.calls) == 1


@pytest.mark.parametrize("halt", [True, False])
def test_runner_keeps_twenty_slots_and_original_evidence(tmp_path, monkeypatch, halt):
    import run_first_screen_v2 as runner

    counter = budget(tmp_path, monkeypatch)

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, path):
            return httpx.Response(
                200,
                json={"csrf_token": "mock"},
                headers={"set-cookie": "edumind_session=mock"},
                request=httpx.Request("POST", "http://localhost" + path),
            )

        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectError("offline recovery")

    class Stream:
        operation_id = "mock-operation"
        started_ns = 100

        def evidence(self, **_kwargs):
            return {
                "status": "published",
                "errors": [],
                "candidates": [],
                "started_ns": 100,
                "milestones_ns": {"published": 200},
            }

    calls = []

    async def raw(**kwargs):
        calls.append(kwargs)
        if halt:
            counter.metadata["halted"] = "AUTH_BALANCE_QUOTA"
            counter.save()
        return Stream()

    monkeypatch.setattr(runner.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(runner, "raw_learning_post", raw)
    output = tmp_path / "raw.json"
    asyncio.run(runner.run(SimpleNamespace(ledger=counter.output, output=output)))
    report = json.loads(output.read_text())
    assert len(report["samples"]) == 20
    assert len(calls) == (1 if halt else 20)
    assert all(call["timeout"] == 180 for call in calls)
    assert len({call["key"] for call in calls}) == len(calls)
    assert report["samples"][0]["status"] == "published"
    assert report["samples"][0]["recovery_error"] == "READ_FAILED"
    assert report["samples"][0]["milestones_ns"]["published"] == 200
    assert report["samples"][0]["recovery_extra_attempts"] == 0
    if halt:
        assert all(s["status"] == "unattempted" for s in report["samples"][1:])
