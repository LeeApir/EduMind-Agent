"""One-shot synthetic subprocess supervisor; never reads keys or sends HTTP.

The child is started via absolute path and Python -I -S. Time checks are
pre-dispatch checks, not an absolute network-send deadline guarantee.
"""

import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import threading
import time
from typing import Any

from scripts.isolated_diagnostics.p15_spawn_isolation_v2 import SpawnOnlyPopen
from scripts.isolated_diagnostics.p15_pilot_wire import ROUTES

CHILD = Path(__file__).resolve().with_name("p15_manual_child_v1.py")
INTERPRETER = Path(sys.executable).resolve(strict=True)


def child_digest() -> str:
    return hashlib.sha256(CHILD.read_bytes()).hexdigest()


def interpreter_digest() -> str:
    return hashlib.sha256(INTERPRETER.read_bytes()).hexdigest()


def _trusted_path(path: Path, expected: str) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("UNTRUSTED_CHILD")
    info = path.stat()
    if (
        not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid())
        or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise ValueError("UNTRUSTED_CHILD")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("CHILD_DIGEST")
    for parent in path.parents:
        details = parent.stat()
        if details.st_uid not in (0, os.getuid()) or details.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError("UNTRUSTED_PARENT")


class ManualSupervisor:
    """Allow a single synthetic request, then require the child to be reaped."""

    def __init__(self, role: str, key: str, expected_child_digest: str, expected_python_digest: str) -> None:
        if role not in ("generation", "review") or not key.startswith("synthetic-"):
            raise ValueError("SYNTHETIC_ONLY")
        other = "review" if role == "generation" else "generation"
        if ROUTES[other]["credential_env"] in set(os.environ.keys()):
            raise ValueError("OTHER_ROLE_ENV_PRESENT")
        self.role = role
        self._key = key
        self._expected = expected_child_digest
        self._expected_python = expected_python_digest
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._process: subprocess.Popen[bytes] | None = None
        self._started = False
        self._stopped = False

    def dispatch(self, body: str, *, batch_deadline: float, request_deadline: float, delay: float = 0) -> dict[str, Any]:
        _trusted_path(CHILD, self._expected)
        _trusted_path(INTERPRETER, self._expected_python)
        job = json.dumps({"role": self.role, "key": self._key, "body": body, "delay": delay}).encode() + b"\n"
        with self._lock:
            if self._started or self._stopped or self._stop_requested.is_set():
                raise RuntimeError("STOPPED_OR_ALREADY_SENT")
            if time.monotonic() >= min(batch_deadline, request_deadline):
                raise RuntimeError("PRE_SEND_DEADLINE")
            self._started = True
            self._process = SpawnOnlyPopen(
                [str(INTERPRETER), "-I", "-S", str(CHILD)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={"PATH": os.defpath, "LANG": "C.UTF-8"},
                close_fds=True,
                start_new_session=True,
            )
            process = self._process
            stop_before_permit = self._stop_requested.is_set()
        if stop_before_permit or self._stop_requested.is_set():
            self.stop(1.0)
            raise RuntimeError("STOPPED_BEFORE_PERMIT")
        try:
            out, _ = process.communicate(job, timeout=max(0.0, min(batch_deadline, request_deadline) - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise TimeoutError(self.stop(1.0)) from None
        if process.returncode != 0:
            raise RuntimeError("CHILD_FAILED")
        if self._stop_requested.is_set():
            raise RuntimeError("STOPPED_RESULT_IGNORED")
        return dict(json.loads(out))

    def stop(self, timeout: float) -> str:
        """Confirm only the child has exited; escaped descendants are unconfirmed."""
        deadline = time.monotonic() + timeout
        self._stop_requested.set()
        if not self._lock.acquire(timeout=max(0.0, timeout)):
            return "stop_unconfirmed"
        try:
            self._stopped = True
            process = self._process
            if process is None:
                return "local_stopped_confirmed"
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    return "stop_unconfirmed"
            try:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                return "stop_unconfirmed"
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                # The synthetic child is a fixed no-network, no-fork script;
                # this is not yet a guarantee for a real sender or descendants.
                return "local_stopped_confirmed"
            except OSError:
                pass
            return "stop_unconfirmed"
        finally:
            self._lock.release()
