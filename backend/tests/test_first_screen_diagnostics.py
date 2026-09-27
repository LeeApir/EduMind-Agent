"""Real application/isolated PostgreSQL, controlled Provider delay, no billable calls."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs/acceptance"))

from first_screen_diagnostics import CURRENT, Timeline, install
from test_learning_sessions import FakeAdapter

from app.api.learning_sessions import provider_gateway
from app.main import app
from app.services.provider_gateway import ProviderGateway

pytestmark = pytest.mark.skipif(
    not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="isolated PG required"
)


def test_real_route_serial_preparation_with_controlled_provider_latency(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    timeline = Timeline()
    install(monkeypatch, timeline)

    class Delayed(FakeAdapter):
        async def generate_structured(self, request):
            stage = (
                "provider_profile"
                if "profile_version" in request.json_schema["properties"]
                else "provider_formal"
            )

            async def call():
                await asyncio.sleep(0.08 if stage == "provider_profile" else 0.005)
                return await super(Delayed, self).generate_structured(request)

            return await timeline.wrap(stage, call)()

        async def stream_text(self, request):
            started = time.monotonic_ns()
            await asyncio.sleep(0.025)
            timeline.spans.append(
                {
                    "stage": "provider_stream_first_delta",
                    "start_ns": started,
                    "end_ns": time.monotonic_ns(),
                    "duration_ms": (time.monotonic_ns() - started) / 1e6,
                }
            )
            async for delta in super().stream_text(request):
                yield delta

    adapter = Delayed()
    app.dependency_overrides[provider_gateway] = lambda: ProviderGateway(adapter)

    async def run():
        token = CURRENT.set(timeline)

        async def observed(scope, receive, send):
            async def timed_send(message):
                if message["type"] == "http.response.start":
                    timeline.sent["headers_sent_ns"] = time.monotonic_ns()
                elif message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    for name in ("agent_start", "token", "stage_changed", "scene_ready"):
                        if f"event: {name}".encode() in body:
                            timeline.sent.setdefault(name, time.monotonic_ns())
                await send(message)

            await app(scope, receive, timed_send)

        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=observed),
                base_url="https://offline",
                headers={"Origin": "https://offline"},
            ) as client:
                auth_start = time.monotonic_ns()
                guest = await client.post("/api/auth/guest")
                assert guest.status_code == 201
                timeline.spans.append(
                    {
                        "stage": "anonymous_session_total_db",
                        "start_ns": auth_start,
                        "end_ns": time.monotonic_ns(),
                        "duration_ms": (time.monotonic_ns() - auth_start) / 1e6,
                    }
                )
                timeline.sent.clear()
                timeline.phase = "learning"
                result = await client.post(
                    "/api/learning-sessions",
                    json={"goal": "讲解单链表"},
                    headers={
                        "X-CSRF-Token": guest.json()["csrf_token"],
                        "Idempotency-Key": str(uuid4()),
                    },
                )
                assert result.status_code == 200
                before_replay = len(adapter.calls)
                assert '"status": "published"' in result.text
                first_send = dict(timeline.sent)
                timeline.phase = "same_key_replay"
                # T030's duplicate POST is replay-only, not a second Provider generation.
                request = result.request
                replay = await client.send(request)
                assert replay.status_code == 200
                assert len(adapter.calls) == before_replay
                timeline.sent = first_send
        finally:
            CURRENT.reset(token)

    try:
        asyncio.run(run())
    finally:
        app.dependency_overrides.clear()
    spans = {s["stage"]: s for s in timeline.spans}
    assert spans["provider_profile"]["duration_ms"] >= 80
    assert spans["provider_stream_first_delta"]["duration_ms"] >= 25
    assert (
        spans["profile_extraction_merge_db"]["end_ns"]
        <= spans["path_locked_snapshot_db"]["start_ns"]
    )
    assert spans["path_locked_snapshot_db"]["end_ns"] < timeline.sent["agent_start"]
    assert spans["provider_profile"]["end_ns"] < timeline.sent["token"]
    output = os.getenv("EDUMIND_DIAGNOSTIC_OUTPUT")
    if output:
        with Path(output).open("x") as handle:
            json.dump(
                {
                    "kind": "offline_controlled_delay_real_routes",
                    "billable_calls": 0,
                    "injected_profile_ms": 80,
                    "injected_first_delta_ms": 25,
                    "spans": timeline.spans,
                    "server_send_ns_not_client_arrival": timeline.sent,
                },
                handle,
                indent=2,
            )
