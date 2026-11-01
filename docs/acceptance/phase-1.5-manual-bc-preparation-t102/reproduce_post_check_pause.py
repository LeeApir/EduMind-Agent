"""Reproduce a synthetic post-check delay; no Provider, key or file writes."""

import asyncio
import json
import socket
import sys
import time
from pathlib import Path

from scripts.isolated_diagnostics import p15_supervised_mock_v2 as mod


class ReachedLateMarker(Exception):
    pass


def forbid(*args, **kwargs):
    raise RuntimeError("network is disabled in the synthetic test")


socket.getaddrinfo = forbid
socket.socket.connect = forbid
socket.socket.connect_ex = forbid
observed = {}


def write_in_memory(path, value, *args, **kwargs):
    if path.name == "dispatched":
        observed["marker_time"] = time.monotonic()
        raise ReachedLateMarker
    if path.name == "worker-pid":
        return len(value)
    raise RuntimeError("filesystem writes disabled")


Path.write_text = write_in_memory
route = mod.wire.ROUTES["generation"]
body = mod.canonical(
    {
        "model": route["model"],
        "input": [
            {"role": "system", "content": "synthetic"},
            {"role": "user", "content": json.dumps({"spec_id": "synthetic"})},
        ],
    }
)
deadline = time.monotonic() + 1.0
job = {
    "role": "generation",
    "target": route["url"],
    "role_key": "synthetic-one-role-key",
    "scenario": "chain",
    "marker_dir": "/not-created",
    "monotonic_deadline": deadline,
    "batch_deadline": int(time.time()) + 30,
    "arm": "C",
    "stage": "C_plan",
    "ordinal": 0,
}


def trace(frame, event, arg):
    if (
        event == "line"
        and frame.f_code.co_name == "mock_handler"
        and frame.f_code.co_filename == mod.__file__
        and frame.f_lineno == 422
        and not observed.get("paused")
    ):
        observed["paused"] = True
        observed["after_successful_check"] = time.monotonic()
        time.sleep(1.2)
    return trace


sys.settrace(trace)
try:
    asyncio.run(mod._synthetic_response(job, body))
except ReachedLateMarker:
    pass
finally:
    sys.settrace(None)

assert observed.get("paused") is True
assert observed["after_successful_check"] < deadline < observed["marker_time"]
print("synthetic check passed before deadline:", observed["after_successful_check"] < deadline)
print("synthetic dispatch marker reached after deadline:", observed["marker_time"] > deadline)
print("late marker delta ms:", round((observed["marker_time"] - deadline) * 1000, 1))
print("watchdog not running; network and filesystem writes disabled")
