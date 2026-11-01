"""Resource-isolated offline view expansion, not a production execution policy."""

import json
import ctypes
import errno
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import threading
import time
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_bounded_json_v1 as bounded
from scripts.isolated_diagnostics.p15_spawn_isolation_v2 import SpawnOnlyPopen
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

ROOT = Path(__file__).resolve().parents[2]
MAX_JOB_BYTES = 64 * 1024 * 1024
MAX_RESULT_BYTES = 32 * 1024 * 1024
MEMORY_BYTES = 1024 * 1024 * 1024
CPU_SECONDS = 25
WALL_SECONDS = 35
REAP_SECONDS = 0.5
MONITOR_JOIN_SECONDS = 0.5


def _resident_bytes(pid: int) -> int:
    if sys.platform == "darwin":
        lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        buf = ctypes.create_string_buffer(128)
        # PROC_PIDTASKINFO: first two uint64 fields are virtual and resident size.
        ctypes.set_errno(0)
        length = lib.proc_pidinfo(pid, 4, 0, buf, len(buf))
        if length < 16:
            raise OSError(ctypes.get_errno() or errno.EIO, "rss_unavailable")
        return int.from_bytes(buf.raw[8:16], sys.byteorder)
    if sys.platform.startswith("linux"):
        status = Path(f"/proc/{pid}/status").read_text()
        line = next(line for line in status.splitlines() if line.startswith("VmRSS:"))
        return int(line.split()[1]) * 1024
    raise OSError("rss_platform_unknown")


def _reaped_after_missing(process: subprocess.Popen[bytes]) -> bool:
    if process.poll() is not None:
        return True
    try:
        # ESRCH can race with the runtime's asynchronous child reaper. Reap
        # promptly; a child still alive after this bounded wait is unknown.
        process.wait(timeout=0.2)
        return True
    except subprocess.TimeoutExpired:
        return False


def _kill_worker_group(process: subprocess.Popen[bytes]) -> None:
    """Best-effort termination of the dedicated worker session and descendants."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        # Even if the group cannot be killed, stop waiting and report unknown.
        try:
            process.kill()
        except OSError:
            pass


def expand(
    value: dict[str, Any], identity: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, Any]:
    """Gate raw role payload before launching a bounded child for Markdown/view work."""
    bounded.encode(value, c.MAX_PAYLOAD, "PAYLOAD_SIZE")
    arm = identity.get("arm")
    c.require(arm in ("B", "C"), "IDENTITY")
    # This does not parse Markdown or build the expanded document tree.
    c.validate(
        "C_content" if arm == "C" else "B_generate",
        value,
        catalog=catalog if arm == "C" else None,
    )
    output = _execute(
        {"mode": "expand", "value": value, "identity": identity, "catalog": catalog}
    )
    c.require(set(output) == {"artifact", "view", "binding"}, "EXPANSION_RESULT")
    return output


def validate_review(
    value: dict[str, Any],
    sent_view: bytes,
    artifact: dict[str, Any],
    catalog: dict[str, Any],
    binding: dict[str, Any],
) -> None:
    """Repeat candidate and exact-view checks inside the same monitored isolation."""
    c.require(
        type(sent_view) is bytes and len(sent_view) <= MAX_RESULT_BYTES,
        "VISIBLE_REQUEST",
    )
    output = _execute(
        {
            "mode": "review",
            "value": value,
            "sent_view": sent_view.decode("utf-8"),
            "artifact": artifact,
            "catalog": catalog,
            "binding": binding,
        }
    )
    c.require(output == {"ok": True}, "EXPANSION_RESULT")


def _execute(data: dict[str, Any]) -> dict[str, Any]:
    job = bounded.encode(data, MAX_JOB_BYTES, "WORKER_INPUT_LIMIT")
    c.require(len(job) <= MAX_JOB_BYTES, "WORKER_INPUT_LIMIT")
    env = {
        "PATH": os.defpath,
        "PYTHONPATH": os.pathsep.join((str(ROOT / "backend"), str(ROOT))),
        "LANG": "C.UTF-8",
    }
    try:
        process = SpawnOnlyPopen(
            [
                sys.executable,
                "-m",
                "scripts.isolated_diagnostics.p15_visible_worker_v2",
                "--worker",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        reason: list[str] = []

        def monitor() -> None:
            # On macOS RLIMIT_AS may be unavailable. Polling RSS is a stop
            # signal, not a hard memory ceiling; allocations can overshoot.
            while process.poll() is None:
                try:
                    resident = _resident_bytes(process.pid)
                    if process.poll() is not None:
                        return
                    if resident > MEMORY_BYTES:
                        reason.append("memory")
                        _kill_worker_group(process)
                        return
                except OSError as exc:
                    if process.poll() is not None:
                        return
                    if exc.errno == errno.ESRCH and _reaped_after_missing(process):
                        # The kernel says the child no longer exists; wait for
                        # reaping before classifying this as monitoring failure.
                        return
                    reason.append("monitor_unknown")
                    _kill_worker_group(process)
                    return
                except (ValueError, StopIteration):
                    if process.poll() is not None:
                        return
                    reason.append("monitor_unknown")
                    _kill_worker_group(process)
                    return
                time.sleep(0.1)

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        try:
            stdout, _ = process.communicate(input=job, timeout=WALL_SECONDS)
        except subprocess.TimeoutExpired:
            # Killing a child does not guarantee that inherited pipes close or
            # that the OS can promptly reap it. Never turn the timeout into an
            # unbounded second communicate().
            _kill_worker_group(process)
            try:
                process.communicate(timeout=REAP_SECONDS)
            except (subprocess.TimeoutExpired, OSError):
                pass
            raise
        finally:
            thread.join(timeout=MONITOR_JOIN_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise c.ContractError("EXPANSION_RESOURCE_UNKNOWN") from exc
    if reason:
        raise c.ContractError("EXPANSION_RESOURCE_" + reason[0].upper())
    if process.returncode != 0:
        code = {
            21: "EXPANSION_VALIDATION",
            22: "EXPANSION_OUTPUT_LIMIT",
            23: "EXPANSION_MEMORY",
        }.get(process.returncode, "EXPANSION_RESOURCE_UNKNOWN")
        raise c.ContractError(code)
    c.require(len(stdout) <= MAX_RESULT_BYTES, "EXPANSION_OUTPUT_LIMIT")
    try:
        output = json.loads(stdout)
    except (ValueError, UnicodeError) as exc:
        raise c.ContractError("EXPANSION_RESULT") from exc
    c.require(type(output) is dict, "EXPANSION_RESULT")
    return dict(output)


def _worker() -> None:
    # A resource limit that cannot be installed is a stop, not an unbounded retry.
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    except (ValueError, OSError):
        # The parent watchdog still enforces a sampled RSS stop, not a hard cap.
        pass
    raw = sys.stdin.buffer.read(MAX_JOB_BYTES + 1)
    c.require(len(raw) <= MAX_JOB_BYTES, "WORKER_INPUT_LIMIT")
    job = json.loads(raw)
    c.require(type(job) is dict, "WORKER_INPUT")
    from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact
    from scripts.isolated_diagnostics import p15_visible_review_view_v1 as visible

    if job.get("mode") == "expand":
        c.require(set(job) == {"mode", "value", "identity", "catalog"}, "WORKER_INPUT")
        arm = job["identity"]["arm"]
        course = artifact.assemble(
            job["value"], job["identity"], job["catalog"] if arm == "C" else None
        )
        view, binding = visible.build(course, job["catalog"])
        result = bounded.encode(
            {"artifact": course, "view": view, "binding": binding},
            MAX_RESULT_BYTES,
            "WORKER_OUTPUT_LIMIT",
        )
    elif job.get("mode") == "review":
        c.require(
            set(job)
            == {"mode", "value", "sent_view", "artifact", "catalog", "binding"},
            "WORKER_INPUT",
        )
        visible.validate_review(
            job["value"],
            job["sent_view"].encode("utf-8"),
            job["artifact"],
            job["catalog"],
            job["binding"],
        )
        result = canonical({"ok": True})
    else:
        raise c.ContractError("WORKER_INPUT")
    c.require(len(result) <= MAX_RESULT_BYTES, "WORKER_OUTPUT_LIMIT")
    sys.stdout.buffer.write(result)


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit(2)
    try:
        _worker()
    except c.ContractError as exc:
        raise SystemExit(22 if str(exc) == "WORKER_OUTPUT_LIMIT" else 21) from None
    except MemoryError:
        raise SystemExit(23) from None
