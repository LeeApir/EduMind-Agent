"""Local maintainer fixed-case supervisor. No models, database or host C fallback."""
from __future__ import annotations

import base64
import json
import os
import selectors
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from offline_c_docker import container_argv
from offline_c_fixtures import FIXTURES, ROOT, AdmissionError, check_manifest, safe_file, sha

LOCK_PATH = ROOT / "docs/acceptance/offline-c-toolchain-t067/lock.json"
LOCK_SHA256 = "3a627ac9040b85a92a62c777fe2be5d221a3968480facfc72057392ef98b0f5f"
HOST_ENV = {"PATH": os.environ["PATH"], "HOME": str(Path.home())}


def docker_json(argv):
    return json.loads(subprocess.check_output(["docker", *argv], env=HOST_ENV, timeout=10))


def verify_toolchain():
    raw = LOCK_PATH.read_bytes()
    if sha(raw) != LOCK_SHA256:
        raise AdmissionError("toolchain lock changed")
    lock = json.loads(raw)
    if sha((ROOT / lock["controller"]).read_bytes()) != lock["controller_sha256"]:
        raise AdmissionError("controller changed")
    approval = json.loads((ROOT / lock["approval"]).read_bytes())
    if approval.get("approved") is not True or approval["manifest_sha256"] != lock["approval_manifest_sha256"]:
        raise AdmissionError("snapshot approval required")
    info = docker_json(["image", "inspect", lock["image_id"]])[0]
    if info["Id"] != lock["image_id"] or (info["Os"], info["Architecture"]) != ("linux", "arm64"):
        raise AdmissionError("wrong toolchain image/platform")
    return lock


def checked_inspect(info, image):
    host = info["HostConfig"]
    required = {"NetworkMode": "none", "IpcMode": "none", "ReadonlyRootfs": True,
                "Memory": 536870912, "MemorySwap": 536870912, "NanoCpus": 1000000000, "PidsLimit": 64}
    if any(host.get(k) != v for k, v in required.items()):
        raise AdmissionError("effective container limits differ")
    if host.get("Privileged") or host.get("CapAdd") or host.get("PidMode") == "host":
        raise AdmissionError("privileged namespace/capability")
    if host.get("CapDrop") != ["ALL"] or "no-new-privileges:true" not in host.get("SecurityOpt", []):
        raise AdmissionError("capability/privilege guard missing")
    if info["Config"]["User"] != "10001:10001" or info["Config"]["Image"] != image:
        raise AdmissionError("container identity/image mismatch")
    binds = [m for m in info["Mounts"] if m["Type"] == "bind"]
    if len(binds) != 1 or binds[0]["Destination"] != "/bundle" or binds[0]["RW"]:
        raise AdmissionError("wrong writable/extra bind mount")
    if any(m["Destination"] not in {"/bundle", "/work", "/tmp"} for m in info["Mounts"]):
        raise AdmissionError("extra image mount")
    return {"effective": required, "user": info["Config"]["User"], "cap_drop": host["CapDrop"],
            "security_opt": host["SecurityOpt"], "tmpfs": host["Tmpfs"],
            "mounts": [{k: m[k] for k in ["Type", "Destination", "RW"] if k in m} for m in info["Mounts"]],
            "inspect_sha256": sha(json.dumps(info, sort_keys=True).encode()),
            "oom": info["State"]["OOMKilled"]}


def supervised(argv, name, *, timeout=40, stdout_limit=1048576):
    started = time.monotonic()
    proc = subprocess.Popen(argv, env=HOST_ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    outputs = {"stdout": bytearray(), "stderr": bytearray()}
    reason = None
    try:
        with selectors.DefaultSelector() as sel:
            for key, pipe in (("stdout", proc.stdout), ("stderr", proc.stderr)):
                os.set_blocking(pipe.fileno(), False)
                sel.register(pipe, selectors.EVENT_READ, key)
            while sel.get_map():
                if time.monotonic()-started > timeout:
                    reason = "timeout"
                    break
                for key, _ in sel.select(.05):
                    raw = os.read(key.fd, 8192)
                    if not raw:
                        sel.unregister(key.fileobj)
                        continue
                    output = outputs[key.data]
                    cap = stdout_limit if key.data == "stdout" else 65536
                    room = cap-len(output)
                    output.extend(raw[:room])
                    if len(raw) > room:
                        reason = "output_limit"
                        break
                if reason:
                    break
        if reason:
            subprocess.run(["docker", "kill", name], env=HOST_ENV, capture_output=True, timeout=10)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        code = proc.wait(timeout=10)
        return {"exit_code": code, "reason": reason, "stdout": bytes(outputs["stdout"]),
                "stderr": bytes(outputs["stderr"]), "duration_ms": int((time.monotonic()-started)*1000)}
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        proc.stdout.close()
        proc.stderr.close()


def execute_container(lock, bundle, args, *, timeout=40):
    name = "edumind-fixed-c-" + uuid.uuid4().hex
    argv = container_argv(lock["image_id"], name, bundle, args)
    try:
        result = supervised(argv, name, timeout=timeout)
        info = docker_json(["inspect", name])[0]
        result["isolation"] = checked_inspect(info, lock["image_id"])
        result["argv"] = argv
        return result
    finally:
        cleanup = subprocess.run(["docker", "rm", "-f", name], env=HOST_ENV, capture_output=True, timeout=10)
        if cleanup.returncode:
            raise AdmissionError(f"container cleanup failed: {name}")


def prepare_bundle(destination):
    check_manifest()
    manifest = json.loads((ROOT / FIXTURES / "manifest.json").read_bytes())
    destination.mkdir(mode=0o755)
    for relative, evidence in manifest["artifacts"].items():
        raw = safe_file(ROOT, str(FIXTURES / relative)).read_bytes()
        if sha(raw) != evidence["sha256"]:
            raise AdmissionError("bundle source changed")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(0o444)
    return manifest


def verify_bundle(bundle, manifest):
    for relative, evidence in manifest["artifacts"].items():
        if sha((bundle / relative).read_bytes()) != evidence["sha256"]:
            raise AdmissionError("bundle changed during execution")


def preflight(lock, bundle):
    result = execute_container(lock, bundle, ["probe"])
    if result["exit_code"] != 0 or result["reason"]:
        raise AdmissionError("isolation probe failed")
    probe = json.loads(result["stdout"])
    assert probe["controller_sha256"] == lock["controller_sha256"]
    assert (probe["uid"], probe["gid"]) == (10001, 10001)
    assert probe["status"] == {"CapEff": "0000000000000000", "NoNewPrivs": "1", "Seccomp": "2"}
    assert all(probe["write_denied"].values())
    assert probe["cgroup"]["memory.max"] == "536870912"
    assert probe["cgroup"]["memory.swap.max"] == "0"
    assert probe["cgroup"]["pids.max"] == "64"
    quota, period = map(int, probe["cgroup"]["cpu.max"].split())
    assert 0 < quota <= period
    assert len(probe["routes"].strip().splitlines()) == 1
    assert probe["tmpfs_bytes"] == {"/work": 134217728, "/tmp": 16777216}
    assert probe["rlimits"] == {"nofile": [128, 128], "core": [0, 0], "fsize": [16777216, 16777216]}
    for mount, required in [("/work", {"nosuid", "nodev"}), ("/tmp", {"nosuid", "nodev", "noexec"})]:
        options = next(line.split()[3] for line in probe["mounts"].splitlines() if line.split()[1] == mount)
        assert required <= set(options.split(','))
    loop = execute_container(lock, bundle, ["probe-loop"], timeout=2)
    flood = execute_container(lock, bundle, ["probe-output"])
    child = execute_container(lock, bundle, ["probe-child-output"])
    assert loop["reason"] == "timeout"
    assert flood["reason"] == "output_limit" and len(flood["stdout"]) == 1048576
    child_result = json.loads(child["stdout"])
    assert child_result["output_limit"] and child_result["stdout"]["bytes"] == 65536
    return {"probe": probe, "isolation": result["isolation"],
            "host_timeout": {"reason": loop["reason"], "argv": loop["argv"]},
            "host_output": {"reason": flood["reason"], "bytes": len(flood["stdout"]), "argv": flood["argv"]},
            "child_output": child_result, "cleanup": "all containers removed"}


def validate_commands(commands):
    for c in commands:
        for stream in ["stdout", "stderr"]:
            b = c[stream]
            raw = base64.b64decode(b["base64"], validate=True)
            if len(raw) != b["bytes"] or sha(raw) != b["sha256"] or len(raw) > 65536:
                raise AdmissionError("invalid bounded command evidence")
        if c["cwd"] != "/work" or c["env"] != dict(v.split("=", 1) for v in __import__("offline_c_docker").ENV):
            raise AdmissionError("unexpected command environment")


def case_result(lock, bundle, source, case, manifest, preflight_digest, *, timeout=40):
    result = execute_container(lock, bundle, [source, case], timeout=timeout)
    aborted = result["reason"] or result["exit_code"] != 0 or result["isolation"]["oom"]
    if aborted:
        value = {"commands": [], "status": "fail", "reason": "oom" if result["isolation"]["oom"] else result["reason"] or "protocol_error"}
        result["isolation"]["controller_failure"] = {
            "exit_code": result["exit_code"], "reason": result["reason"],
            "stdout_sha256": sha(result["stdout"]), "stderr_sha256": sha(result["stderr"]),
            "stage_execution": "unknown; container started, no synthetic child exit code"}
    else:
        try:
            value = json.loads(result["stdout"])
            if set(value) != {"commands", "status", "reason"}:
                raise AdmissionError("invalid controller result")
            validate_commands(value["commands"])
        except (ValueError, KeyError, TypeError) as error:
            value = {"commands": [], "status": "fail", "reason": "protocol_error"}
            result["isolation"]["controller_failure"] = {
                "error": type(error).__name__, "stdout_sha256": sha(result["stdout"]),
                "stderr_sha256": sha(result["stderr"]),
                "stage_execution": "unknown; started container returned invalid evidence"}
    commands = value["commands"]
    stderr = base64.b64decode(commands[0]["stderr"]["base64"]).decode("utf-8", "replace") if commands else ""
    observations = {k: None for k in ["numeric_sequence", "format_exact", "attempts", "allocated", "released", "live", "per_insert_states", "free_call_sequence", "caller_head_reset"]}
    observations.update({"asan": "not_run", "ubsan": "not_run", "lsan": "not_run"})
    expected = False
    if source == "om-original":
        expected = (value["reason"] in {"compile_failed", "compile_error"} and "Node" in stderr)
    elif case == "strict":
        expected = value["reason"] == "compile_error" and "no newline at end of file" in stderr
    elif case == "ordinary":
        expected = value["status"] == "pass" and len(commands) == 1
    elif len(commands) == 2:
        actual = base64.b64decode(commands[1]["stdout"]["base64"])
        independent = json.loads((bundle / "spec/independent.json").read_bytes())["independent_expectations"]["edumind"]["original_main"]
        numeric = [int(n) for n in actual.decode().split()]
        observations["numeric_sequence"] = numeric
        observations["format_exact"] = {"independent": actual == base64.b64decode(independent["stdout_base64"]),
                                         "model_claim": actual == b"3 2 1"}
        if case == "sanitized-normal":
            observations["asan"] = observations["ubsan"] = "ran; see exact exit/stderr, no report on this path" if commands[1]["exit_code"] == 0 else "ran; diagnostic/abnormal exit"
        expected = value["status"] == "pass" and numeric == independent["numeric_sequence"] and observations["format_exact"]["independent"]
        if not expected and value["status"] == "pass":
            value["status"], value["reason"] = "fail", "numeric_mismatch" if numeric != independent["numeric_sequence"] else "format_mismatch"
    source_relative = manifest["sources"][source]["program"]
    bindings = {"package": sha((ROOT / FIXTURES / "manifest.json").read_bytes()),
                "source": manifest["artifacts"][source_relative]["sha256"],
                "extraction": manifest["artifacts"]["spec/extraction.json"]["sha256"],
                "driver": None, "spec": manifest["artifacts"]["spec/independent.json"]["sha256"],
                "review_registry": manifest["review_registry_sha256"], "toolchain": LOCK_SHA256,
                "controller": lock["controller_sha256"],
                "baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    return {"version": "fixed-c-offline-v1", "run_id": None, "case_id": case, "source_id": source,
            "bindings": bindings, "toolchain": lock,
            "isolation": {**result["isolation"], "preflight_sha256": preflight_digest, "cleanup": "removed", "container_argv": result["argv"]},
            "kind": "strict_compile" if case == "strict" else "ordinary_compile" if case == "ordinary" else "original_main",
            "fault_at": None, **value, "observations": observations,
            "expected_observation_matched": expected,
            "scope_limitations": ["fixed original 1/2/3 main only", "ordinary and strict results separate", "LSan not run", "model output not oracle", "not a model review/pass or human signoff"]}


def run_compile_suite(manifest_path, output):
    # The output must be fresh so past failure evidence is never overwritten.
    if output.exists() and any(output.iterdir()):
        raise AdmissionError("output evidence directory must be fresh")
    output.mkdir(parents=True, exist_ok=True)
    check_manifest(manifest_path)
    schedule = [(s, c) for s in ["edumind-r02-original", "om-original"] for c in ["strict", "ordinary", "normal", "sanitized-normal"]]
    report = {"version": "fixed-c-report-v1", "run_id": uuid.uuid4().hex, "suite": "compile-output",
              "provider_calls": 0, "cases": [], "preflight": None, "stopped": None}
    started = time.monotonic()
    try:
        lock = verify_toolchain()
        with tempfile.TemporaryDirectory(prefix="edumind-fixed-c-") as private:
            bundle = Path(private) / "bundle"
            manifest = prepare_bundle(bundle)
            report["preflight"] = preflight(lock, bundle)
            preflight_digest = sha(json.dumps(report["preflight"], sort_keys=True).encode())
            for source, case in schedule:
                if time.monotonic()-started > 1200:
                    raise AdmissionError("run wall budget exhausted")
                result = case_result(lock, bundle, source, case, manifest, preflight_digest, timeout=min(40, 1200-(time.monotonic()-started)))
                result["run_id"] = report["run_id"]
                report["cases"].append(result)
                verify_bundle(bundle, manifest)
                if not result["expected_observation_matched"]:
                    raise AdmissionError("unexpected observation; stop without retry")
    except (OSError, ValueError, KeyError, AssertionError, subprocess.SubprocessError) as error:
        report["stopped"] = {"type": type(error).__name__, "message": str(error)[:300]}
    completed = {(c["source_id"], c["case_id"]) for c in report["cases"]}
    for source, case in schedule:
        if (source, case) not in completed:
            report["cases"].append({"version": "fixed-c-offline-v1", "run_id": report["run_id"],
                "source_id": source, "case_id": case, "status": "not_run", "reason": "stopped",
                "bindings": {key: None for key in ["package", "source", "extraction", "driver", "spec", "review_registry", "toolchain", "controller", "baseline_commit"]},
                "toolchain": None, "isolation": {"cleanup": "not_started"},
                "kind": "strict_compile" if case == "strict" else "ordinary_compile" if case == "ordinary" else "original_main",
                "fault_at": None, "commands": [], "observations": {},
                "expected_observation_matched": None,
                "scope_limitations": ["not run; no result inferred from environment failure"]})
    report["execution_counts_are_confirmed_minimum"] = any(c.get("isolation", {}).get("controller_failure") for c in report["cases"])
    report["compilations"] = sum(len([c for c in case.get("commands", []) if c["argv"][0] == "/usr/bin/clang-19"]) for case in report["cases"])
    report["sample_processes"] = sum(len([c for c in case.get("commands", []) if c["argv"][0] == "/work/program"]) for case in report["cases"])
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    return report
