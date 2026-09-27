"""Offline acceptance instrumentation regressions; no real Provider calls."""

import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

DIRECTORY = Path(__file__).resolve().parents[2] / "docs/acceptance"
sys.path.insert(0, str(DIRECTORY))


def load(name):
    spec = importlib.util.spec_from_file_location(name, DIRECTORY / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load("run_first_screen")
SERVER = load("serve_first_screen")
AUDIT = load("audit_first_screen")


def test_paragraph_requires_real_boundary_and_excludes_headings_and_fences():
    assert RUNNER.paragraph_candidate("指针保存地址。") is None
    assert RUNNER.paragraph_candidate("指针保存地址。\n") is None
    assert RUNNER.paragraph_candidate("指针保存地址。\n\n") == "指针保存地址。"
    assert RUNNER.paragraph_candidate("指针保存地址。", ended=True) == "指针保存地址。"
    assert RUNNER.paragraph_candidate("# 指针。\n\n```c\nint *p;\n```\n\n") is None
    assert (
        RUNNER.paragraph_candidate("# 标题\n\n```c\ncode.\n```\n\n指针保存地址。\n\n")
        == "指针保存地址。"
    )
    assert RUNNER.paragraph_candidate("不完整陈述\n\n", ended=True) is None
    assert RUNNER.paragraph_candidate("\n\n", ended=True) is None
    assert (
        RUNNER.paragraph_candidate("Pointers store addresses.\n\n") == "Pointers store addresses."
    )


def test_planned_p95_retains_missing_and_does_not_use_conditional_p95():
    samples = [{"validated_ms": {"token": n}} for n in range(18)]
    samples.extend([{"validated_ms": {}}, {"validated_ms": {}}])
    result = RUNNER.summarize(samples, "token")
    assert result["missing"] == 2
    assert result["planned_p95_missing"] is True
    assert result["planned_p95_ms"] is None
    assert result["conditional_observed_p95_ms"] == 17
    assert (
        RUNNER.summarize([{"validated_ms": {"token": n}} for n in range(20)], "token")[
            "planned_p95_ms"
        ]
        == 18
    )


def test_manual_audit_does_not_promote_candidates_or_mutate_raw():
    samples = [
        {
            "number": n,
            "validated_ms": {m: 1000 for m in RUNNER.METRICS},
            "client_ms": {m: 1100 for m in RUNNER.METRICS},
        }
        for n in range(1, 21)
    ]
    raw = {
        "samples": samples,
        "samples_planned": 20,
        "published_failures": 0,
        "metrics": {"paragraph": {"planned_p95_ms": 1000}},
    }
    result = AUDIT.audit(raw, [2, 11, 12])
    assert result["first_token_gate_passed"] is True
    assert result["first_teachable_paragraph_gate_passed"] is False
    assert result["validated_metrics"]["paragraph"]["missing"] == 3
    assert result["validated_metrics"]["paragraph"]["planned_p95_ms"] is None
    assert result["stage_gate_passed"] is False
    assert raw["samples"][1]["validated_ms"]["paragraph"] == 1000


def test_validated_clock_wrap_runs_only_after_real_dependencies_and_schema():
    app = FastAPI()
    calls = []

    class Payload(BaseModel):
        value: int

    async def auth():
        calls.append("auth")
        return "owner"

    @app.post("/api/learning-sessions")
    async def endpoint(payload: Payload, owner=Depends(auth)):
        calls.append("endpoint")
        return JSONResponse({"value": payload.value})

    SERVER.instrument_route(app)
    with TestClient(app) as client:
        invalid = client.post("/api/learning-sessions", json={"value": "invalid"})
        assert invalid.status_code == 422
        assert SERVER.HEADER not in invalid.headers
        assert "endpoint" not in calls
        calls.clear()
        good = client.post("/api/learning-sessions", json={"value": 1})
        assert calls == ["auth", "endpoint"]
        assert int(good.headers[SERVER.HEADER]) > 0

        async def denied():
            raise HTTPException(401)

        app.dependency_overrides[auth] = denied
        calls.clear()
        forbidden = client.post("/api/learning-sessions", json={"value": 1})
        assert forbidden.status_code == 401
        assert SERVER.HEADER not in forbidden.headers
        assert calls == []


def test_timeout_retained_without_retry(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            raise TimeoutError()

    monkeypatch.setattr(RUNNER.httpx, "AsyncClient", lambda **kwargs: Client())
    result = asyncio.run(RUNNER.sample("http://offline", 1))
    assert result["status"] == "failed"
    assert result["error_codes"] == ["TOTAL_TIMEOUT"]
    assert result["validated_ms"] == {}


def test_real_client_parser_fragmented_sse_and_fresh_identity_offline(monkeypatch):
    keys = []

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            events = [
                ("agent_start", {"stage": "preparing"}),
                ("token", {"temporary": True, "delta": "指针保存"}),
                ("token", {"temporary": True, "delta": "地址。\n\n"}),
                ("stage_changed", {"stage": "reviewing"}),
                ("scene_ready", {"learning_unit_id": "offline"}),
                ("done", {"status": "published"}),
            ]
            for event, payload in events:
                frame = f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()
                yield frame[:7]
                await asyncio.sleep(0.001)
                yield frame[7:]

    def handle(request):
        if request.url.path == "/api/auth/guest":
            return httpx.Response(
                201,
                json={"csrf_token": "offline"},
                headers={"Set-Cookie": "edumind_session=offline; Secure; HttpOnly; Path=/"},
            )
        assert request.url.path == "/api/learning-sessions"
        assert request.headers["X-CSRF-Token"] == "offline"
        assert request.headers["Cookie"] == "edumind_session=offline"
        keys.append(request.headers["Idempotency-Key"])
        return httpx.Response(
            200,
            headers={SERVER.HEADER: str(time.monotonic_ns())},
            stream=Chunks(),
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        RUNNER.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    for number in (1, 2):
        record = asyncio.run(RUNNER.sample("http://offline", number))
        assert record["status"] == "published"
        assert record["error_codes"] == []
        metrics = record["validated_ms"]
        assert set(metrics) == set(RUNNER.METRICS)
        assert metrics["headers"] < metrics["status"] < metrics["token"]
        assert metrics["token"] < metrics["paragraph"] < metrics["published"]
        assert record["manual_review_required"] is True
    assert len(keys) == 2
    assert keys[0] != keys[1]
