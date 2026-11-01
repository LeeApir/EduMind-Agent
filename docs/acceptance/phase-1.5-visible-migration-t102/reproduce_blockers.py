"""Reproduce two known security gaps with synthetic credentials and Mock HTTP.

Exit 2 means the gaps are present; this is not a passing acceptance test.
No real DNS, TCP connection, or Provider key is used.
"""

import asyncio
import inspect
import json
import socket
import tempfile
import threading
import time
from pathlib import Path

import httpx

from scripts.isolated_diagnostics import p15_controlled_mock_v1 as controller
from scripts.isolated_diagnostics import p15_pinned_transport_v1 as transport
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.tests.test_p15_controlled_mock_v1 import grant


def deny_network(*args, **kwargs):
    raise AssertionError("real network forbidden")


async def synthetic_dns(host, port):
    return ("1.1.1.1",)


def credentials():
    return {
        wire.ROUTES["generation"]["credential_env"]: "synthetic-generation-key",
        wire.ROUTES["review"]["credential_env"]: "synthetic-review-key",
    }


def race(path):
    seen = []
    checked, resume = threading.Event(), threading.Event()
    original = transport.DispatchFence.is_set
    previous_timeout = controller.HTTP_WALL_SECONDS

    def stale_read(self):
        value = original(self)
        frame = inspect.currentframe()
        if frame and frame.f_back and frame.f_back.f_code.co_name == "guarded":
            checked.set()
            resume.wait(2)
        return value

    def handler(request):
        seen.append(request.headers["host"])
        return httpx.Response(500, stream=httpx.ByteStream(b"{}"))

    controller.HTTP_WALL_SECONDS = 0.08
    transport.DispatchFence.is_set = stale_read
    instance = None
    try:
        adapter = transport.PinnedResponsesTransport(
            resolver=synthetic_dns, credentials=credentials(), transport=httpx.MockTransport(handler)
        )
        instance = controller.Controller(path, grant("B", path), adapter)
        try:
            asyncio.run(instance.run())
        except Exception as exc:
            assert str(exc) == "MOCK_HTTP_TIMEOUT"
        assert checked.is_set() and instance.batch_status() == "stopped" and not seen
        instance.close()
        instance = None
        resume.set()
        deadline = time.monotonic() + 2
        while not seen and time.monotonic() < deadline:
            time.sleep(0.01)
        assert seen == ["api.deepseek.com"]
        print("STOP_RACE: stopped with 0 sends; later Mock dispatches=1")
    finally:
        resume.set()
        transport.DispatchFence.is_set = original
        controller.HTTP_WALL_SECONDS = previous_timeout
        if instance is not None:
            instance.abandon_pending()


def escaped_secret(path):
    secret = credentials()[wire.ROUTES["generation"]["credential_env"]]
    escaped = "".join("\\\\u%04x" % ord(char) for char in secret)
    raw = json.dumps({"output": [{"content": [{"text": "echo " + escaped}]}]}).encode()
    assert not transport._secret_visible(raw, secret)
    adapter = transport.PinnedResponsesTransport(
        resolver=synthetic_dns,
        credentials=credentials(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=httpx.ByteStream(raw))),
    )
    instance = controller.Controller(path, grant("B", path), adapter)
    try:
        try:
            asyncio.run(instance.run())
        except Exception as exc:
            assert str(exc) == "MOCK_USAGE_UNKNOWN"
        row = instance.db.execute("SELECT state,response FROM attempts").fetchone()
        assert instance.batch_status() == "stopped" and bytes(row["response"]) == raw
        print("ESCAPED_SECRET: detector missed synthetic encoded key; raw response persisted")
    finally:
        instance.close()


if __name__ == "__main__":
    socket.getaddrinfo = deny_network
    socket.socket.connect = deny_network
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        race(root / "race.db")
        escaped_secret(root / "secret.db")
    print("Known gaps reproduced; real transport remains disabled.")
    raise SystemExit(2)
