"""Fail-closed static and command boundaries for the trusted renderer."""

import ast
import json
import os
import subprocess
from pathlib import Path

import pytest

from app.services import animation_renderer as renderer
from app.services.animation_templates import TemplateValidationError

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("source", [
    "import subprocess",
    "from os import system",
    "open('/etc/passwd')",
    "eval('1+1')",
    "exec('pass')",
    "os.system('id')",
    "x.__class__",
    "from pathlib import Path",
    "getattr(x, 'secret')",
    "os.unlink('/tmp/x')",
    "json.load(open('/tmp/x'))",
    "os.environ['SECRET']",
])
def test_static_audit_rejects_import_execution_and_path_escape(source: str) -> None:
    with pytest.raises(renderer.RenderError, match="RENDER_SOURCE_REJECTED"):
        renderer.audit_source(source)


@pytest.mark.parametrize("template_id,parameters,expected", [
    ("linked-list-insertion", {"values": [1, 3], "index": 1, "value": 2},
     {"VALUES": [1, 3], "INDEX": 1, "VALUE": 2}),
    ("linked-list-deletion", {"values": [1, 3], "index": 0},
     {"VALUES": [1, 3], "INDEX": 0}),
])
def test_compiler_replaces_only_literal_template_constants(
    template_id: str, parameters: dict[str, object], expected: dict[str, object]
) -> None:
    scene = renderer._TEMPLATES[template_id][1]
    source = (ROOT / "backend" / scene).read_text(encoding="utf-8")
    compiled = renderer._compiled_scene(source, parameters)
    tree = ast.parse(compiled)
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in expected
    }
    assert assignments == expected
    assert "__import__" not in compiled


def test_invalid_parameters_never_start_docker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def unexpected_docker(*args: object, **kwargs: object) -> None:
        raise AssertionError("docker must not start")

    monkeypatch.setattr(renderer, "_docker", unexpected_docker)
    with pytest.raises(TemplateValidationError):
        renderer.render_template(
            "linked-list-insertion", {"values": [1], "index": 2, "value": 4},
            work_root=tmp_path,
        )
    with pytest.raises(TemplateValidationError):
        renderer.render_template(
            "linked-list-deletion", {"values": [], "index": 0}, work_root=tmp_path,
        )
    assert list(tmp_path.iterdir()) == []


def test_docker_unavailable_fails_closed_and_cleans_only_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sentinel = tmp_path / "unrelated.txt"
    sentinel.write_text("keep", encoding="utf-8")
    command: list[str] = []

    def unavailable(args: list[str], **kwargs: object) -> None:
        command.extend(args)
        raise renderer.RenderError("RENDER_UNAVAILABLE")

    monkeypatch.setattr(renderer, "_docker", unavailable)
    with pytest.raises(renderer.RenderError, match="RENDER_UNAVAILABLE"):
        renderer.render_template(
            "linked-list-insertion", {"values": [1], "index": 0, "value": 2},
            work_root=tmp_path,
        )
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert list(tmp_path.iterdir()) == [sentinel]
    assert "--network" in command and command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "--cap-drop" in command
    assert "--user" in command and command[command.index("--user") + 1] == "10001:10001"
    assert "--tmpfs" in command and "size=268435456" in " ".join(command)
    assert sum(arg.startswith("type=bind,") for arg in command) == 1
    assert not any("docker.sock" in arg or "Provider" in arg for arg in command)


@pytest.mark.skipif(os.environ.get("EDUMIND_DOCKER_TESTS") != "1", reason="needs Docker")
def test_real_isolated_render_and_timeout(tmp_path: Path) -> None:
    for template_id, parameters, expected_hash, seconds in (
        ("linked-list-insertion", {"values": [1, 3, 5], "index": 1, "value": 2},
         "35b4ee0ac13ecff166320e4b1abde9dccc4226f8e177216c92d0b61abaa94f01", 36),
        ("linked-list-deletion", {"values": [1, 3, 5], "index": 1},
         "95d4ab163dc455156477cb5325733577b7ec089b3db6a4250ec645a73ee690ae", 42),
    ):
        result = renderer.render_template(template_id, parameters, work_root=tmp_path)
        assert result.mp4_sha256 == expected_hash and result.duration_seconds == seconds
        assert result.mp4_path.is_file() and result.srt_path.is_file()
        assert not (result.attempt_dir / "input").exists()
        result.cleanup()
    with pytest.raises(renderer.RenderError, match="RENDER_TIMEOUT"):
        renderer.render_template(
            "linked-list-insertion", {"values": [1], "index": 0, "value": 2},
            work_root=tmp_path, timeout_seconds=0.01,
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.environ.get("EDUMIND_DOCKER_TESTS") != "1", reason="needs Docker")
def test_real_container_denies_network_root_write_and_output_over_quota() -> None:
    probe = """
import json, socket
from pathlib import Path
result = {}
try:
    socket.create_connection(("1.1.1.1", 80), timeout=2)
    result["network"] = 0
except OSError as error:
    result["network"] = error.errno
try:
    Path("/etc/edumind-probe").write_text("x")
    result["rootfs"] = 0
except OSError as error:
    result["rootfs"] = error.errno
try:
    with Path("/output/quota").open("wb") as output:
        for _ in range(257):
            output.write(b"x" * 1048576)
    result["quota"] = 0
except OSError as error:
    result["quota"] = error.errno
print(json.dumps(result))
"""
    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--user", "10001:10001", "--cpus", "2", "--memory", "1g",
        "--pids-limit", "128", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
        "--tmpfs", "/output:rw,nosuid,nodev,size=268435456,mode=1777",
        renderer.IMAGE, "python", "-c", probe,
    ]
    result = subprocess.run(command, capture_output=True, check=True, timeout=30)
    violations = json.loads(result.stdout)
    assert violations["network"] != 0
    assert violations["rootfs"] in (1, 13, 30)
    assert violations["quota"] == 28
