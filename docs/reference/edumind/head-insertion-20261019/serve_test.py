"""One-course observational instance; production source and environment stay unchanged."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DB_NAME = "edumind_head_insertion_20261019"
sys.path.insert(0, str(ROOT / "backend"))
os.umask(0o077)


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def configure():
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url

    values = dotenv_values(ROOT / ".env")
    for name, value in values.items():
        if name.startswith("EDUMIND_") and value is not None:
            os.environ[name] = value
    url = make_url(os.environ["EDUMIND_DATABASE_URL"])
    # The existing Compose database is container-addressed in some environments.
    # Only a local loopback DB is used, with an entirely new database name.
    url = url.set(host="127.0.0.1", port=15432, database=DB_NAME)
    os.environ["EDUMIND_DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["EDUMIND_PRODUCT_MODE"] = "dynamic"
    assert os.environ["EDUMIND_PROVIDER_MODEL"] == "deepseek-flash"
    assert os.environ["EDUMIND_PROVIDER_BASE_URL"] == "https://api.deepseek.com"
    assert os.environ["EDUMIND_PROVIDER_STRUCTURED_TRANSPORT"] == "responses_json_schema"
    return url


async def prepare(url):
    import asyncpg

    connection = await asyncpg.connect(
        host=url.host, port=url.port, user=url.username, password=url.password,
        database="postgres", timeout=10,
    )
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", DB_NAME)
        if exists:
            raise RuntimeError("Test database already exists; never reset or reuse automatically")
        await connection.execute(f'CREATE DATABASE "{DB_NAME}"')
    finally:
        await connection.close()


def main():
    url = configure()
    asyncio.run(prepare(url))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend", check=True,
    )

    import httpx
    import uvicorn
    from app.core import provider_factory
    from app.services.provider_gateway import ProviderError, ProviderErrorCode

    calls = []
    save("provider-calls.json", calls)

    class CaptureTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.inner = httpx.AsyncHTTPTransport(retries=0)

        async def handle_async_request(self, request):
            if len(calls) >= 22:
                raise ProviderError(ProviderErrorCode.CONFIGURATION_MISSING)
            body = json.loads(request.content)
            assert body.get("model") == "deepseek-flash"
            number = len(calls) + 1
            entry = {
                "number": number, "started_at": now(), "method": request.method,
                "route": "https://api.deepseek.com/responses",
                "actual_url": str(request.url),
                "host": request.headers.get("host"),
                "model": body.get("model"), "reasoning": body.get("reasoning"),
                "max_output_tokens": body.get("max_output_tokens"),
                "request_sha256": hashlib.sha256(request.content).hexdigest(),
                "status": "sent", "stream": body.get("stream"),
            }
            calls.append(entry)
            (OUT / f"{number:03}-request.json").write_bytes(request.content)
            save("provider-calls.json", calls)
            start = time.monotonic()
            try:
                response = await self.inner.handle_async_request(request)
                raw = await response.aread()
                (OUT / f"{number:03}-response.bin").write_bytes(raw)
                entry.update(http_status=response.status_code, status="received")
                try:
                    payload = json.loads(raw)
                    entry.update(returned_model=payload.get("model"), usage=payload.get("usage"))
                except ValueError:
                    pass
                return response
            except BaseException as error:
                entry.update(status="interrupted", error_class=type(error).__name__)
                raise
            finally:
                entry.update(ended_at=now(), duration_seconds=time.monotonic() - start)
                save("provider-calls.json", calls)

        async def aclose(self):
            await self.inner.aclose()

    original = provider_factory.configured_provider_adapter

    def observed_adapter(settings, guard, **kwargs):
        adapter = original(settings, guard, **kwargs)
        adapter._transport = CaptureTransport()
        return adapter

    provider_factory.configured_provider_adapter = observed_adapter
    from app.main import app

    class CaptureLearning:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http" or scope.get("path") != "/api/learning-sessions":
                return await self.wrapped(scope, receive, send)
            request_parts = []
            response_parts = []
            metadata = {"started_at": now(), "method": scope["method"]}

            async def capture_receive():
                message = await receive()
                if message["type"] == "http.request":
                    request_parts.append(message.get("body", b""))
                return message

            async def capture_send(message):
                if message["type"] == "http.response.start":
                    metadata["http_status"] = message["status"]
                elif message["type"] == "http.response.body":
                    response_parts.append(message.get("body", b""))
                await send(message)

            try:
                await self.wrapped(scope, capture_receive, capture_send)
            finally:
                (OUT / "learning-request.json").write_bytes(b"".join(request_parts))
                (OUT / "learning-response.sse").write_bytes(b"".join(response_parts))
                metadata["ended_at"] = now()
                save("learning-http.json", metadata)

    save("instance.json", {
        "started_at": now(), "database": DB_NAME, "api_port": 8029,
        "web_port": 5199, "mode": "dynamic", "scope": "one isolated test course",
        "model": "deepseek-flash", "transport": "responses_json_schema",
        "reasoning": "none (actual default factory)", "production_env_modified": False,
        "cost_cap_cny": None, "request_cap": 22,
        "approval": "User replied 无上限 to this isolated test proposal",
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    })
    uvicorn.run(CaptureLearning(app), host="127.0.0.1", port=8029, access_log=False)


if __name__ == "__main__":
    main()
