"""Fixed supervisor regressions; real isolation/C evidence is recorded separately."""
import base64
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from offline_c_docker import container_argv  # noqa: E402
from offline_c_fixtures import AdmissionError  # noqa: E402
from offline_c_runner import checked_inspect, validate_commands  # noqa: E402

spec = importlib.util.spec_from_file_location("trusted_c_controller", ROOT / "scripts/offline_c_runtime/controller.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)
IMAGE = "sha256:" + "a" * 64
NAME = "edumind-fixed-c-" + "b" * 32


def inspect_fixture():
    return {"Config": {"User": "10001:10001", "Image": IMAGE},
            "HostConfig": {"NetworkMode": "none", "IpcMode": "none", "ReadonlyRootfs": True,
                           "Memory": 536870912, "MemorySwap": 536870912, "NanoCpus": 1000000000,
                           "PidsLimit": 64, "Privileged": False, "CapAdd": None, "CapDrop": ["ALL"],
                           "SecurityOpt": ["no-new-privileges:true"], "Tmpfs": {}},
            "Mounts": [{"Type": "bind", "Destination": "/bundle", "RW": False}], "State": {"OOMKilled": False}}


def test_exact_image_and_registered_case_only():
    argv = container_argv(IMAGE, NAME, Path("/private/bundle"), ["edumind-r02-original", "strict"])
    assert "--network=none" in argv and "--read-only" in argv and "--privileged" not in argv
    assert "-i" in argv and "HOME=/tmp" in argv
    for image, args in [("latest", ["metadata"]), (IMAGE, ["arbitrary.c", "normal"]), (IMAGE, ["/bin/sh", "-c"]), (IMAGE, ["edumind-r02-original", "custom-flags"])]:
        with pytest.raises(ValueError):
            container_argv(image, NAME, None, args)


@pytest.mark.parametrize("key,value", [("NetworkMode", "host"), ("IpcMode", "host"), ("ReadonlyRootfs", False),
    ("Memory", 0), ("MemorySwap", -1), ("NanoCpus", 0), ("PidsLimit", 0),
    ("Privileged", True), ("CapAdd", ["SYS_ADMIN"]), ("SecurityOpt", ["seccomp=unconfined"])])
def test_effective_guards_cannot_be_dropped(key, value):
    data = inspect_fixture()
    data["HostConfig"][key] = value
    with pytest.raises(AdmissionError):
        checked_inspect(data, IMAGE)


def test_extra_or_writable_mount_is_rejected():
    for mount in [{"Type": "bind", "Destination": "/project", "RW": False},
                  {"Type": "volume", "Destination": "/extra", "RW": True}]:
        data = inspect_fixture()
        data["Mounts"].append(mount)
        with pytest.raises(AdmissionError):
            checked_inspect(data, IMAGE)
    data = inspect_fixture()
    data["Mounts"][0]["RW"] = True
    with pytest.raises(AdmissionError):
        checked_inspect(data, IMAGE)


def test_good_inspect_and_bounded_output_binding():
    assert checked_inspect(inspect_fixture(), IMAGE)["effective"]["PidsLimit"] == 64
    command = {"stdout": controller.encoded(b"3 2 1 \n"), "stderr": controller.encoded(b""), "cwd": "/work", "env": controller.ENV}
    command.update(argv=["synthetic"], started_at="2026-10-19T00:00:00+00:00", ended_at="2026-10-19T00:00:00+00:00", duration_ms=0, exit_code=0, signal=None, timeout=False, output_limit=False, oom=False)
    validate_commands([command])
    bad = copy.deepcopy(command)
    bad["stdout"]["base64"] = base64.b64encode(b"other").decode()
    with pytest.raises(AdmissionError):
        validate_commands([bad])
    bad = copy.deepcopy(command)
    bad["env"] = {**bad["env"], "API_KEY": "synthetic"}
    with pytest.raises(AdmissionError):
        validate_commands([bad])


@pytest.mark.parametrize("case,status,reason", [("normal", "not_run", "compile_failed"), ("strict", "fail", "compile_error")])
def test_compile_failure_never_runs_a_program(monkeypatch, capsys, case, status, reason):
    calls = []
    def fake(argv, timeout):
        calls.append(argv)
        return {"exit_code": 1, "timeout": False, "output_limit": False}
    monkeypatch.setattr(controller, "capture", fake)
    monkeypatch.setattr(sys, "argv", ["controller", "om-original", case])
    controller.main()
    value = json.loads(capsys.readouterr().out)
    assert (value["status"], value["reason"]) == (status, reason)
    assert len(calls) == 1 and calls[0][0] == "/usr/bin/clang-19"


@pytest.mark.parametrize("run_result,reason", [
    ({"exit_code": 7, "timeout": False, "output_limit": False}, "runtime_error"),
    ({"exit_code": None, "timeout": True, "output_limit": False}, "timeout"),
    ({"exit_code": None, "timeout": False, "output_limit": True}, "output_limit")])
def test_run_failure_never_becomes_pass(monkeypatch, capsys, run_result, reason):
    results = iter([{"exit_code": 0, "timeout": False, "output_limit": False}, run_result])
    monkeypatch.setattr(controller, "capture", lambda argv, timeout: next(results))
    monkeypatch.setattr(sys, "argv", ["controller", "edumind-r02-original", "normal"])
    controller.main()
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "fail" and value["reason"] == reason


def test_environment_unavailable_records_all_not_run_without_host_fallback(monkeypatch, tmp_path):
    import offline_c_runner as runner
    def unavailable():
        raise FileNotFoundError("Docker unavailable; synthetic regression")
    monkeypatch.setattr(runner, "verify_toolchain", unavailable)
    report = runner.run_compile_suite(ROOT / "docs/acceptance/offline-c-fixtures/manifest.json", tmp_path / "evidence")
    assert report["stopped"] is not None
    assert len(report["cases"]) == 8 and report["compilations"] == report["sample_processes"] == 0
    assert all(c["status"] == "not_run" and c["commands"] == [] for c in report["cases"])
    assert all(c["expected_observation_matched"] is None for c in report["cases"])


def test_started_container_with_invalid_evidence_is_failure_not_fictional_not_run(monkeypatch):
    import offline_c_runner as runner
    monkeypatch.setattr(runner, "execute_container", lambda *args, **kwargs: {
        "reason": None, "exit_code": 0, "stdout": b"invalid JSON", "stderr": b"",
        "isolation": {"oom": False}, "argv": ["docker", "synthetic"]})
    manifest = json.loads((ROOT / "docs/acceptance/offline-c-fixtures/manifest.json").read_bytes())
    result = runner.case_result({"controller_sha256": "a"*64}, ROOT, "edumind-r02-original", "normal", manifest, "b"*64)
    assert result["status"] == "fail" and result["reason"] == "protocol_error"
    assert result["commands"] == [] and not result["expected_observation_matched"]
    assert "unknown" in result["isolation"]["controller_failure"]["stage_execution"]
