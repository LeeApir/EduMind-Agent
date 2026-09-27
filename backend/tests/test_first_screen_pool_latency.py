"""Real loopback Uvicorn/PG with injected connection delay and a fake Provider only."""

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import httpx
import pytest
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs/acceptance"))

from first_screen_v2 import assessed_metrics, raw_learning_post
from test_learning_sessions import FakeAdapter

from app.api.learning_sessions import provider_gateway
from app.core import database
from app.main import app
from app.services.provider_gateway import ProviderGateway

pytestmark = pytest.mark.skipif(
    not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="isolated PG required"
)


def test_pool_reuse_makes_teaching_paragraph_earlier_without_changing_recovery(monkeypatch):
    url = os.environ["EDUMIND_TEST_DATABASE_URL"]
    monkeypatch.setenv("EDUMIND_DATABASE_URL", url)
    original = database.create_async_engine
    connections = []
    engines = []

    def delayed_engine(database_url, **kwargs):
        async def connect():
            connections.append(1)
            await asyncio.sleep(0.1)
            return await asyncpg.connect(
                database_url.replace("postgresql+asyncpg://", "postgresql://")
            )

        engine = original(database_url, async_creator=connect, **kwargs)
        engines.append(engine)
        return engine

    monkeypatch.setattr(database, "create_async_engine", delayed_engine)
    adapter = FakeAdapter()
    app.dependency_overrides[provider_gateway] = lambda: ProviderGateway(adapter)

    async def once(legacy):
        # Same actual app/protocol, only ownership of pool differs.
        import socket

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(10)
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            await asyncio.sleep(0.005)
        if legacy:

            async def legacy_factory():
                engine = database.create_database_engine()
                try:
                    yield database.async_sessionmaker(engine, expire_on_commit=False)
                finally:
                    await engine.dispose()

            app.dependency_overrides[database.database_session_factory] = legacy_factory
        start_connections = len(connections)
        start_calls = len(adapter.calls)
        try:
            base = f"http://127.0.0.1:{port}"
            async with httpx.AsyncClient(
                base_url=base, headers={"Origin": base}, trust_env=False
            ) as client:
                guest = await client.post("/api/auth/guest")
                assert guest.status_code == 201
                csrf = guest.json()["csrf_token"]
                cookie = guest.cookies["edumind_session"]
                key = str(uuid4())
                before_learning = len(connections)
                stream = await raw_learning_post(
                    port=port, cookie=cookie, csrf=csrf, key=key, goal="讲解单链表"
                )
                assert stream.status == "published" and stream.errors == []
                learning_connections = len(connections) - before_learning
                candidate = stream.paragraphs.candidates[0]
                assert candidate["text"] == "链表由节点组成。先理解 next 指针。"
                decision = {
                    "1": {
                        "sha256": candidate["sha256"],
                        "verdict": "teaching",
                        "reason": "公开fixture说明节点连接关系",
                    }
                }
                assessed = assessed_metrics(stream.evidence(), decision)
                calls = len(adapter.calls)
                replay = await raw_learning_post(
                    port=port, cookie=cookie, csrf=csrf, key=key, goal="讲解单链表"
                )
                assert replay.status == "published" and len(adapter.calls) == calls
                client.cookies.clear()
                client.cookies.set("edumind_session", cookie)
                owned = await client.get(f"/api/learning-operations/{stream.operation_id}")
                assert owned.status_code == 200 and owned.json()["status"] == "published"
                # Different anonymous owner cannot reuse published identity.
                other = await client.post("/api/auth/guest")
                client.cookies.clear()
                client.cookies.set("edumind_session", other.cookies["edumind_session"])
                assert stream.operation_id is not None
                unauthorized = await client.get(f"/api/learning-operations/{stream.operation_id}")
                assert unauthorized.status_code == 404
                assert len(adapter.calls) == calls
                return {
                    "legacy": legacy,
                    "learning_cold_connections": learning_connections,
                    "total_connections": len(connections) - start_connections,
                    "client_ms": assessed["client_ms"],
                    "fake_provider_calls": calls - start_calls,
                    "same_key_replay_additional_provider_calls": len(adapter.calls) - calls,
                }
        finally:
            app.dependency_overrides.pop(database.database_session_factory, None)
            server.should_exit = True
            await serving
            listener.close()

    async def run():
        try:
            before = await once(True)
            after = await once(False)
            assert before["learning_cold_connections"] >= 2
            assert after["learning_cold_connections"] == 0
            assert (
                before["client_ms"]["teaching_paragraph"] - after["client_ms"]["teaching_paragraph"]
                >= 150
            )
            output = os.getenv("EDUMIND_POOL_DIAGNOSTIC_OUTPUT")
            if output:
                with Path(output).open("x") as handle:
                    json.dump(
                        {
                            "kind": "offline_wire_real_routes_pg_mock",
                            "billable_calls": 0,
                            "injected_cold_connect_ms": 100,
                            "before": before,
                            "after": after,
                        },
                        handle,
                        indent=2,
                    )
        finally:
            for engine in engines:
                await engine.dispose()

    try:
        asyncio.run(run())
    finally:
        app.dependency_overrides.clear()
