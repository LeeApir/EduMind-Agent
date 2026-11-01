"""Bounded synthetic-secret checks in a separate offline Python process.

The checks cover declared literal and JSON/Unicode escape forms, not arbitrary
encodings or deliberate splitting. Unknown inputs fail closed. This module
does not load environment credentials, resolve DNS, or make HTTP requests.
"""

import base64
from collections.abc import Iterator
import errno
import itertools
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import threading
import time
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_visible_worker_v1 as isolated
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

ROOT = Path(__file__).resolve().parents[2]
VERSION = "synthetic-secret-guard-v1"
MAX_RAW = 12_000_000
MAX_JOB = 17_000_000
MAX_DEPTH = 64
MAX_KEYS = 2
WALL_SECONDS = 20.0
REAP_SECONDS = 0.5
CPU_SECONDS = 15
MEMORY_BYTES = 512 * 1024 * 1024
_ESCAPED_UNICODE = re.compile(r"\\{1,32}u([0-9a-fA-F]{4})")


def _normalized(text: str) -> tuple[str, bool]:
    for _ in range(4):
        value = _ESCAPED_UNICODE.sub(lambda match: chr(int(match.group(1), 16)), text)
        value = re.sub(r"\\{1,32}/", "/", value)
        if value == text:
            return text, False
        text = value
    return text, bool(_ESCAPED_UNICODE.search(text) or re.search(r"\\{1,32}/", text))


def classify(raw: bytes, keys: list[str]) -> str:
    """Return only safe, unsafe, or unknown; never include inputs in results."""
    if (
        type(raw) is not bytes
        or len(raw) > MAX_RAW
        or type(keys) is not list
        or not 1 <= len(keys) <= MAX_KEYS
        or any(type(key) is not str or not 8 <= len(key) <= 1024 for key in keys)
    ):
        return "unknown"
    try:
        text = raw.decode("utf-8")
        root = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return "unknown"
    normalized, truncated = _normalized(text)
    if any(key in text or key in normalized for key in keys):
        return "unsafe"
    if truncated:
        return "unknown"
    # Iterators keep the traversal stack proportional to depth, not item count.
    stack: list[tuple[Iterator[Any], int]] = [(iter((root,)), 0)]
    while stack:
        iterator, depth = stack[-1]
        try:
            value = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        if depth > MAX_DEPTH:
            return "unknown"
        if isinstance(value, str):
            normalized, truncated = _normalized(value)
            if any(key in value or key in normalized for key in keys):
                return "unsafe"
            if truncated:
                return "unknown"
            if re.search(r"\\{33,}u", value):
                return "unknown"
            try:
                nested = json.loads(value)
            except RecursionError:
                return "unknown"
            except (ValueError, UnicodeError):
                continue
            if isinstance(nested, (dict, list, str)) and nested != value:
                stack.append((iter((nested,)), depth + 1))
        elif isinstance(value, dict):
            stack.append((iter(itertools.chain(value.keys(), value.values())), depth + 1))
        elif isinstance(value, list):
            stack.append((iter(value), depth + 1))
    return "safe"


def check(raw: bytes, keys: list[str]) -> None:
    """Invoke the restricted checker; anything except an exact safe result stops."""
    c.require(type(raw) is bytes and len(raw) <= MAX_RAW, "GUARD_INPUT")
    job = canonical({"raw_b64": base64.b64encode(raw).decode("ascii"), "keys": keys})
    c.require(len(job) <= MAX_JOB, "GUARD_INPUT")
    env = {
        "PATH": os.defpath,
        "PYTHONPATH": os.pathsep.join((str(ROOT / "backend"), str(ROOT))),
        "LANG": "C.UTF-8",
    }
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "scripts.isolated_diagnostics.p15_synthetic_guard_v1", "--worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=ROOT,
            env=env,
            close_fds=True,
            start_new_session=True,
        )
        reason: list[str] = []

        def monitor() -> None:
            while process.poll() is None:
                try:
                    if isolated._resident_bytes(process.pid) > MEMORY_BYTES:
                        reason.append("memory")
                        isolated._kill_worker_group(process)
                        return
                except OSError as exc:
                    if process.poll() is not None:
                        return
                    if exc.errno == errno.ESRCH and isolated._reaped_after_missing(process):
                        return
                    reason.append("monitor")
                    isolated._kill_worker_group(process)
                    return
                except (ValueError, StopIteration):
                    if process.poll() is None:
                        reason.append("monitor")
                        isolated._kill_worker_group(process)
                    return
                time.sleep(0.1)

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        try:
            output, _ = process.communicate(input=job, timeout=WALL_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                process.communicate(timeout=REAP_SECONDS)
            except (OSError, subprocess.TimeoutExpired):
                pass
            raise c.ContractError("GUARD_UNKNOWN") from None
        finally:
            thread.join(timeout=0.5)
    except OSError:
        raise c.ContractError("GUARD_UNKNOWN") from None
    c.require(not reason and process.returncode == 0 and output in (b"safe\n", b"unsafe\n", b"unknown\n"), "GUARD_UNKNOWN")
    c.require(output == b"safe\n", "GUARD_UNSAFE" if output == b"unsafe\n" else "GUARD_UNKNOWN")


def _worker() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    except (ValueError, OSError):
        pass
    raw = sys.stdin.buffer.read(MAX_JOB + 1)
    if len(raw) > MAX_JOB:
        raise SystemExit(2)
    try:
        value = json.loads(raw)
        if type(value) is not dict or set(value) != {"raw_b64", "keys"}:
            raise ValueError
        payload = base64.b64decode(value["raw_b64"], validate=True)
        result = classify(payload, value["keys"])
    except (ValueError, TypeError, KeyError, RecursionError):
        raise SystemExit(2) from None
    sys.stdout.write(result + "\n")


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit(2)
    _worker()
