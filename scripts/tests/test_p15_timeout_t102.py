"""Caller wall-clock, late response and worker cleanup regressions; offline only."""

import asyncio
from copy import deepcopy
import subprocess
import sys
import threading
import time

import httpx
import pytest

from scripts.isolated_diagnostics import p15_controlled_mock_v1 as controller
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_visible_worker_v1 as worker
from scripts.tests.test_p15_controlled_mock_v1 import attest, grant, handler_for, package_grant
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC


def test_sync_blocking_handler_does_not_hold_asyncio_run_or_release_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "HTTP_WALL_SECONDS", 0.08)
    path = tmp_path / "ledger.db"
    started, release = threading.Event(), threading.Event()
    sent = []

    def blocked(request):
        sent.append(1)
        started.set()
        release.wait(2)
        raise RuntimeError("synthetic blocked transport")

    instance = controller.Controller(
        path, package_grant(path), httpx.MockTransport(blocked), selected=("slot", "B")
    )
    begin = time.monotonic()
    with pytest.raises(c.ContractError, match="MOCK_HTTP_TIMEOUT"):
        asyncio.run(instance.run(attest))
    assert time.monotonic() - begin < 0.9 and started.is_set()
    row = instance.db.execute("SELECT state,input_reserved,output_reserved FROM attempts").fetchone()
    assert row["state"] == "unknown" and row["input_reserved"] > 0 and row["output_reserved"] == 8000
    summary = instance.fixed_denominator_summary()
    assert summary["denominator"] == 2
    assert [item["outcome"] for item in summary["slots"]] == ["failed_or_unknown", "not_run"]
    assert sent == [1] and instance.batch_status() == "stopped"
    instance.close()
    release.set()


def test_cancellation_suppressing_transport_does_not_hold_caller(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "HTTP_WALL_SECONDS", 0.08)
    path = tmp_path / "ledger.db"

    async def ignores_cancellation(request):
        try:
            await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            await asyncio.sleep(1.5)
        return httpx.Response(500)

    instance = controller.Controller(path, grant("B", path), httpx.MockTransport(ignores_cancellation))
    begin = time.monotonic()
    with pytest.raises(c.ContractError, match="MOCK_HTTP_TIMEOUT"):
        asyncio.run(instance.run(attest))
    assert time.monotonic() - begin < 0.9
    assert instance.batch_status() == "stopped"
    assert instance.db.execute("SELECT state FROM attempts").fetchone()[0] == "unknown"
    instance.close()


def test_deadline_returns_when_feedback_thread_never_finishes(tmp_path, monkeypatch):
    path = tmp_path / "ledger.db"
    limits = grant("B", path)
    limits["deadline"] = 101
    monkeypatch.setattr(controller.time, "time", lambda: 100.0)
    release = threading.Event()
    entered = threading.Event()
    seen = []

    def feedback(*args):
        entered.set()
        release.wait(3)
        return attest(*args)

    instance = controller.Controller(path, limits, httpx.MockTransport(handler_for("B", seen)))
    begin = time.monotonic()
    with pytest.raises(c.ContractError, match="MOCK_DEADLINE_TIMEOUT"):
        asyncio.run(instance.run(feedback))
    assert time.monotonic() - begin < 1.8 and entered.is_set()
    assert instance.batch_status() == "stopped" and len(seen) == 2
    assert instance.fixed_denominator_summary()["slots"][0]["outcome"] == "failed_or_unknown"
    instance.close()
    release.set()


def test_deadline_returns_when_request_secret_preflight_hangs(tmp_path, monkeypatch):
    from scripts.isolated_diagnostics import p15_pinned_transport_v1 as pinned

    path = tmp_path / "ledger.db"
    limits = grant("B", path)
    limits["deadline"] = 101
    monkeypatch.setattr(controller.time, "time", lambda: 100.0)
    entered, release = threading.Event(), threading.Event()

    async def dns(host, port):
        pytest.fail("must not resolve")

    adapter = pinned.PinnedResponsesTransport(
        resolver=dns,
        credentials={
            "EDUMIND_DEEPSEEK_COMPAT_API_KEY": "synthetic-generation-key",
            "EDUMIND_AIAPI_REVIEW_API_KEY": "synthetic-review-key",
        },
        transport=httpx.MockTransport(lambda request: pytest.fail("must not send")),
    )

    def blocked(body):
        entered.set()
        release.wait(3)

    monkeypatch.setattr(adapter, "ensure_request_safe", blocked)
    instance = controller.Controller(path, limits, adapter)
    begin = time.monotonic()
    with pytest.raises(c.ContractError, match="MOCK_DEADLINE_TIMEOUT"):
        asyncio.run(instance.run(attest))
    assert time.monotonic() - begin < 1.8 and entered.is_set()
    assert instance.batch_status() == "stopped"
    assert instance.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    instance.close()
    release.set()


def test_http_timeout_retains_late_bytes_and_usage_without_advancing(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "HTTP_WALL_SECONDS", 0.08)

    async def exercise():
        path = tmp_path / "ledger.db"
        release = threading.Event()
        seen = []
        reply = handler_for("B", seen)

        def delayed(request):
            assert release.wait(2)
            return reply(request)

        instance = controller.Controller(path, grant("B", path), httpx.MockTransport(delayed))
        with pytest.raises(c.ContractError, match="MOCK_HTTP_TIMEOUT"):
            await instance.run(attest)
        row = instance.db.execute("SELECT * FROM attempts").fetchone()
        assert row["state"] == "unknown" and row["response"] is None
        release.set()
        assert await instance.drain_late(2)
        row = instance.db.execute("SELECT * FROM attempts").fetchone()
        assert row["state"] == "late" and row["input_used"] == 10 and row["response"]
        assert len(seen) == 1 and instance.batch_status() == "stopped"
        instance.close()

    asyncio.run(exercise())


def test_stopped_unresponsive_transport_can_be_abandoned_without_resending(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "HTTP_WALL_SECONDS", 0.08)

    async def exercise():
        path = tmp_path / "ledger.db"
        release = threading.Event()
        seen = []
        reply = handler_for("B", seen)

        def delayed(request):
            release.wait(2)
            return reply(request)

        instance = controller.Controller(path, grant("B", path), httpx.MockTransport(delayed))
        with pytest.raises(c.ContractError, match="MOCK_HTTP_TIMEOUT"):
            await instance.run(attest)
        assert not await instance.drain_late(0.01)
        instance.abandon_pending()
        reopened = controller.Controller(path, grant("B", path), httpx.MockTransport(reply))
        assert reopened.batch_status() == "stopped"
        assert reopened.db.execute("SELECT state FROM attempts").fetchone()[0] == "unknown"
        with pytest.raises(c.ContractError):
            await reopened.run(attest)
        reopened.close()
        release.set()
        await asyncio.sleep(0.1)
        assert len(seen) <= 1

    asyncio.run(exercise())


def test_worker_timeout_with_inherited_stdout_returns_and_kills_group(monkeypatch):
    real_popen = subprocess.Popen
    monkeypatch.setattr(worker, "WALL_SECONDS", 0.1)
    monkeypatch.setattr(worker, "REAP_SECONDS", 0.1)
    monkeypatch.setattr(worker, "MONITOR_JOIN_SECONDS", 0.1)

    def spawn_inheriting_child(*args, **kwargs):
        script = "import os,time; os.fork(); time.sleep(3)"
        return real_popen([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr(worker.subprocess, "Popen", spawn_inheriting_child)
    begin = time.monotonic()
    with pytest.raises(c.ContractError, match="EXPANSION_RESOURCE_UNKNOWN"):
        worker._execute({})
    assert time.monotonic() - begin < 1.2


def test_crash_after_slot_start_before_reservation_keeps_denominator(tmp_path):
    path = tmp_path / "ledger.db"
    package = package_grant(path)
    transport = httpx.MockTransport(lambda request: pytest.fail("no send"))
    first = controller.Controller(path, package, transport, selected=("slot", "B"))
    first.db.execute("UPDATE slots SET status='started' WHERE slot='slot' AND arm='B'")
    first._seal()
    first.close()
    recovered = controller.Controller(path, package, transport, selected=("slot", "B"))
    assert recovered.batch_status() == "stopped"
    summary = recovered.fixed_denominator_summary()
    assert summary["denominator"] == 2
    assert [row["outcome"] for row in summary["slots"]] == ["failed_or_unknown", "not_run"]
    assert recovered.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    recovered.close()


def test_failure_and_unrun_remain_in_original_28_arm_denominator(tmp_path):
    path = tmp_path / "ledger.db"
    rows = []
    for index in range(14):
        spec = deepcopy(SPEC)
        kind = "supported" if index < 10 else "refusal"
        if kind == "refusal":
            spec["variant"] = "unsupported"
        for arm in ("B", "C"):
            rows.append(dict(slot=f"dev-{index:02}", arm=arm, spec=spec, kind=kind, question=None))
    package = dict(
        batch="fixed-denominator-dev",
        ledger_path=str(path.absolute()),
        slots=rows,
        calls=90,
        input=1_080_737_280,
        output=720_000,
        request_bytes=12_000_000,
        deadline=4_000_000_000,
    )
    sent = []

    def fail(request):
        sent.append(1)
        return httpx.Response(500, stream=httpx.ByteStream(b"{}"))

    instance = controller.Controller(path, package, httpx.MockTransport(fail), selected=("dev-00", "B"))
    with pytest.raises(c.ContractError):
        asyncio.run(instance.run(attest))
    summary = instance.fixed_denominator_summary()
    assert summary["denominator"] == 28 and len(summary["slots"]) == 28
    assert sum(row["kind"] == "supported" for row in summary["slots"]) == 20
    assert sum(row["kind"] == "refusal" for row in summary["slots"]) == 8
    assert sum(row["outcome"] == "failed_or_unknown" for row in summary["slots"]) == 1
    assert sum(row["outcome"] == "not_run" for row in summary["slots"]) == 27
    assert sent == [1] and not summary["semantic_quality_evaluated"]
    instance.close()
