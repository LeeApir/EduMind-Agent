"""Single-repeat transport fail-closed tests; no real Provider."""

# ruff: noqa: E402
import asyncio
from pathlib import Path
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_plan_p01_retest as run
from acceptance_support.qwen_review_budget import sha
from acceptance_support.plan_admission_run import Ledger


def test_transport_only_same_review_wire_once_even_after_failed_send(monkeypatch):
    raw = b"exact frozen wire"
    monkeypatch.setattr(run, "WIRE_SHA", sha(raw))
    calls = []

    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout("test only")

    wire = run.SingleWire("review", httpx.MockTransport(fail))
    request = httpx.Request("POST", "https://example.com", content=raw)

    async def exercise():
        with pytest.raises(httpx.ReadTimeout):
            await wire.handle_async_request(request)
        with pytest.raises(ValueError):
            await wire.handle_async_request(request)

    asyncio.run(exercise())
    assert len(calls) == 1


@pytest.mark.parametrize(
    "role,body", [("generation", b"exact frozen wire"), ("review", b"changed wire")]
)
def test_wrong_role_or_wire_never_sent(monkeypatch, role, body):
    monkeypatch.setattr(run, "WIRE_SHA", sha(b"exact frozen wire"))
    calls = []
    wire = run.SingleWire(
        role, httpx.MockTransport(lambda request: calls.append(request))
    )
    with pytest.raises(ValueError):
        asyncio.run(
            wire.handle_async_request(
                httpx.Request("POST", "https://example.com", content=body)
            )
        )
    assert not calls


def test_one_slot_caps_one_and_stop_preserves_old_run(tmp_path):
    ledger = Ledger(
        tmp_path / "run.sqlite", "a" * 64, [run.spec()], activate=True, now=lambda: 1000
    )
    slot = run.spec()["slot_id"]
    ledger.start(slot)
    n, _ = ledger.reserve(slot, "plan_check", "b" * 64)
    ledger.complete(n, "c" * 64)
    with pytest.raises(ValueError, match="CAP"):
        ledger.reserve(slot, "plan_check", "b" * 64)
    ledger.finish(slot, "d" * 64)
    ledger.stop("SINGLE_REPEAT_FINISHED_STOP_NO_CONTINUATION")
    with pytest.raises(ValueError, match="STOPPED"):
        ledger.start(slot)
    assert len(ledger.snapshot()["calls"]) == 1
