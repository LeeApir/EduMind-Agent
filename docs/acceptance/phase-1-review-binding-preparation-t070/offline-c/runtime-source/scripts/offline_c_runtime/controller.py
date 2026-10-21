"""Trusted fixed-case controller, copied into the locked image; no arbitrary argv API."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import selectors
import resource
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ENV = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "TMPDIR": "/tmp", "LANG": "C", "LC_ALL": "C",
       "ASAN_OPTIONS": "detect_leaks=0:abort_on_error=1:symbolize=0",
       "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=0"}
SOURCES = {"edumind-r02-original": "edumind/candidate.c", "om-original": "om/original-program.c"}
FLAGS = ["-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Wnewline-eof"]
SANITIZERS = ["-O0", "-g", "-fno-omit-frame-pointer", "-fsanitize=address,undefined", "-fno-sanitize-recover=all"]


def utc():
    return datetime.now(timezone.utc).isoformat()


def encoded(raw):
    return {"base64": base64.b64encode(raw).decode(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def capture(argv, timeout, limit=65536):
    started = utc()
    before = time.monotonic()
    proc = subprocess.Popen(argv, cwd="/work", env=ENV, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    outputs = {"stdout": bytearray(), "stderr": bytearray()}
    timed_out = overflow = False
    with selectors.DefaultSelector() as sel:
        for name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            os.set_blocking(stream.fileno(), False)
            sel.register(stream, selectors.EVENT_READ, name)
        while sel.get_map():
            if time.monotonic() - before > timeout:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                break
            for key, _ in sel.select(.05):
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    sel.unregister(key.fileobj)
                    continue
                output = outputs[key.data]
                remaining = limit - len(output)
                output.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow = True
                    os.killpg(proc.pid, signal.SIGKILL)
                    break
            if overflow:
                break
    code = proc.wait(timeout=2)
    proc.stdout.close()
    proc.stderr.close()
    return {"argv": argv, "cwd": "/work", "env": ENV, "started_at": started, "ended_at": utc(),
            "duration_ms": int((time.monotonic()-before)*1000), "exit_code": code if code >= 0 else None,
            "signal": -code if code < 0 else None, "timeout": timed_out, "output_limit": overflow,
            "oom": False, **{k: encoded(bytes(v)) for k, v in outputs.items()}}


def metadata():
    commands = [capture(["/usr/bin/clang-19", "--version"], 5),
                capture(["/usr/bin/ld", "--version"], 5),
                capture(["/usr/bin/dpkg-query", "-W", "-f=${Package}=${Version}\\n"], 5)]
    return {"controller_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "python": sys.version, "python_executable": sys.executable,
            "platform": sys.platform, "machine": os.uname().machine, "commands": commands}


def probe():
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
    denied = {}
    for name in ["/root-write-probe", "/bundle/write-probe"]:
        try:
            Path(name).write_text("forbidden")
            denied[name] = False
        except PermissionError:
            denied[name] = True
        except OSError as exc:
            denied[name] = exc.errno == 30
    cgroup = {name: Path("/sys/fs/cgroup", name).read_text().strip()
              for name in ["memory.max", "memory.swap.max", "pids.max", "cpu.max"]}
    return {"uid": os.getuid(), "gid": os.getgid(),
            "status": {k: status[k].strip() for k in ["CapEff", "NoNewPrivs", "Seccomp"]},
            "write_denied": denied, "cgroup": cgroup,
            "routes": Path("/proc/net/route").read_text(),
            "mounts": Path("/proc/mounts").read_text(),
            "tmpfs_bytes": {name: os.statvfs(name).f_blocks * os.statvfs(name).f_frsize for name in ["/work", "/tmp"]},
            "rlimits": {name: resource.getrlimit(value) for name, value in [
                ("nofile", resource.RLIMIT_NOFILE), ("core", resource.RLIMIT_CORE), ("fsize", resource.RLIMIT_FSIZE)]},
            "controller_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def main():
    if sys.argv[1:] == ["probe"]:
        print(json.dumps(probe()))
        return
    if sys.argv[1:] == ["probe-loop"]:
        while True:
            pass
    if sys.argv[1:] == ["probe-output"]:
        while True:
            os.write(1, b"x" * 8192)
    if sys.argv[1:] == ["probe-child-output"]:
        print(json.dumps(capture([sys.executable, "-I", "-c", "import os; os.write(1, b'x'*131072)"], 5)))
        return
    if sys.argv[1:] == ["metadata"]:
        print(json.dumps(metadata()))
        return
    if len(sys.argv) != 3 or sys.argv[1] not in SOURCES:
        raise ValueError("unregistered source or command")
    source_id, case = sys.argv[1:]
    ownership = case in {f"{mode}-{n}" for mode in ["program", "contract"] for n in range(4)}
    negative = case in {"negative-drop-link", "negative-double-free", "negative-ignored-return"}
    if case not in {"strict", "ordinary", "normal", "sanitized-normal"} and not ownership and not negative:
        raise ValueError("unregistered case")
    source = "/bundle/" + SOURCES[source_id]
    if ownership and (source_id == "edumind-r02-original" or case.startswith("contract-")):
        source = "/bundle/" + ("edumind" if source_id == "edumind-r02-original" else "om") + "/ownership-driver.c"
    if negative:
        if source_id != "edumind-r02-original":
            raise ValueError("unregistered controlled negative")
        source = "/bundle/edumind/ownership-driver.c"
    flags = FLAGS + (["-Werror"] if case == "strict" else [])
    if case == "sanitized-normal" or ownership or negative:
        flags += SANITIZERS
    if negative:
        flags += [f'-DSOURCE_C="{case}.c"']
    command = capture(["/usr/bin/clang-19", *flags, source, "-o", "/work/program"], 30)
    commands = [command]
    reason = "success"
    status = "pass"
    if command["timeout"]:
        status, reason = "fail", "timeout"
    elif command["output_limit"]:
        status, reason = "fail", "output_limit"
    elif command["exit_code"] != 0:
        status, reason = "fail", "compile_error"
    elif case in {"normal", "sanitized-normal"} or ownership or negative:
        args = ["/work/program"]
        if ownership:
            args += ["program" if case.startswith("program-") else "contract", case.rsplit("-", 1)[1]]
        if negative:
            args += ["program", "0"]
        run = capture(args, 5)
        commands.append(run)
        if run["timeout"]:
            status, reason = "fail", "timeout"
        elif run["output_limit"]:
            status, reason = "fail", "output_limit"
        elif run["exit_code"] != 0:
            status, reason = "fail", "runtime_error"
    if len(commands) == 1 and reason == "compile_error" and (case in {"normal", "sanitized-normal"} or ownership):
        status, reason = "not_run", "compile_failed"
    print(json.dumps({"commands": commands, "status": status, "reason": reason}))


if __name__ == "__main__":
    main()
