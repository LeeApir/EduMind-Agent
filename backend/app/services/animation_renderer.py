"""Fail-closed renderer for approved, literal-parameter Manim templates."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.services.animation_templates import load_template, normalize_parameters

ROOT = Path(__file__).resolve().parents[3]
IMAGE = (
    "manimcommunity/manim@"
    "sha256:89ab433ce59134a4dcf351deb2511e067ab354393c0bb7d1859f3e8f0b2406a3"
)
MAX_FILE_BYTES = 64 * 1024 * 1024
OUTPUT_QUOTA_BYTES = 256 * 1024 * 1024
_TEMPLATES = {
    "linked-list-insertion": (
        "app/animation_templates/insertion_plan.py",
        "app/animation_templates/linked_list_insertion.py",
        "LinkedListInsertionScene", "compiled_scene",
    ),
    "linked-list-deletion": (
        "app/animation_templates/deletion_plan.py",
        "app/animation_templates/linked_list_deletion.py",
        "LinkedListDeletionScene", "compiled_scene",
    ),
}
_ALLOWED_FROM = {
    "__future__": {"annotations"},
    "dataclasses": {"dataclass"},
    "typing": {"cast"},
    "manim": {
        "DOWN", "LEFT", "RIGHT", "UP", "Arrow", "FadeIn", "FadeOut",
        "RoundedRectangle", "Scene", "Text", "VGroup",
    },
    "app.animation_templates.insertion_plan": {"InsertionFrame", "plan_insertion"},
    "app.animation_templates.deletion_plan": {"DeletionFrame", "plan_deletion"},
    "app.services.animation_templates": {"load_template", "normalize_parameters"},
}
_BANNED_CALLS = {
    "eval", "exec", "compile", "open", "__import__", "getattr", "setattr",
    "delattr", "globals", "locals", "vars", "input", "breakpoint", "system",
    "popen", "fork", "spawn", "socket", "connect", "read_text", "write_text",
    "read_bytes", "write_bytes",
}


class RenderError(RuntimeError):
    """Stable error code; never contains paths, source or container logs."""


@dataclass(frozen=True)
class RenderedCandidate:
    attempt_dir: Path
    mp4_path: Path
    srt_path: Path
    duration_seconds: float
    mp4_sha256: str
    srt_sha256: str

    def cleanup(self) -> None:
        shutil.rmtree(self.attempt_dir)


def audit_source(source: str) -> ast.Module:
    """Check fixed business source and the literal-compiled scene before execution."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise RenderError("RENDER_SOURCE_REJECTED") from error
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name not in {"json", "os"} or alias.asname for alias in node.names):
                raise RenderError("RENDER_SOURCE_REJECTED")
        elif isinstance(node, ast.ImportFrom):
            allowed = _ALLOWED_FROM.get(node.module or "", set())
            if node.level or not allowed or any(
                alias.name not in allowed or alias.asname for alias in node.names
            ):
                raise RenderError("RENDER_SOURCE_REJECTED")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            raise RenderError("RENDER_SOURCE_REJECTED")
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            raise RenderError("RENDER_SOURCE_REJECTED")
        elif isinstance(node, ast.Attribute) and (
            node.attr.startswith("__") or node.attr in _BANNED_CALLS
        ):
            raise RenderError("RENDER_SOURCE_REJECTED")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "os" and node.attr != "environ":
                raise RenderError("RENDER_SOURCE_REJECTED")
            if node.value.id == "json" and node.attr != "loads":
                raise RenderError("RENDER_SOURCE_REJECTED")
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            if isinstance(node.value.value, ast.Name) and node.value.value.id == "os":
                raise RenderError("RENDER_SOURCE_REJECTED")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _BANNED_CALLS:
                raise RenderError("RENDER_SOURCE_REJECTED")
    return tree


def _compiled_scene(scene_source: str, parameters: Mapping[str, object]) -> str:
    tree = audit_source(scene_source)
    literals = {
        "VALUES": parameters["values"],
        "INDEX": parameters["index"],
    }
    if "value" in parameters:
        literals["VALUE"] = parameters["value"]
    values = parameters["values"]
    if not isinstance(values, list):
        raise RenderError("RENDER_SOURCE_REJECTED")
    seen: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in literals:
                if target.id in seen:
                    raise RenderError("RENDER_SOURCE_REJECTED")
                node.value = ast.Constant(literals[target.id]) if target.id != "VALUES" else (
                    ast.List(elts=[ast.Constant(value) for value in values],
                             ctx=ast.Load())
                )
                seen.add(target.id)
    if seen != set(literals):
        raise RenderError("RENDER_SOURCE_REJECTED")
    compiled = ast.unparse(ast.fix_missing_locations(tree))
    audit_source(compiled)
    return compiled + "\n"


def _docker(
    args: list[str], *, timeout: float = 15, check: bool = False
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            ["docker", *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise RenderError("RENDER_UNAVAILABLE") from error
    if check and result.returncode != 0:
        raise RenderError("RENDER_UNAVAILABLE")
    return result


def _stage_input(template_id: str, parameters: Mapping[str, object], input_dir: Path) -> None:
    plan, scene, _, _ = _TEMPLATES[template_id]
    files = (
        "app/__init__.py", "app/animation_templates/__init__.py",
        "app/animation_templates/container_runner.py",
        "app/services/__init__.py", "app/services/animation_templates.py", plan, scene,
    )
    for relative in files:
        source = ROOT / "backend" / relative
        target = input_dir / "backend" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o644)
        if relative in (plan, scene):
            audit_source(target.read_text(encoding="utf-8"))
    manifest = f"data/animation_templates/{template_id}.json"
    target = input_dir / manifest
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / manifest, target)
    (input_dir / "compiled_scene.py").write_text(
        _compiled_scene((input_dir / "backend" / scene).read_text(encoding="utf-8"),
                        parameters),
        encoding="utf-8",
    )
    for directory in input_dir.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)
    input_dir.chmod(0o755)


def _stream_artifact(container_id: str, relative: str, target: Path) -> str:
    digest = hashlib.sha256()
    process = subprocess.Popen(
        ["docker", "exec", container_id, "cat", f"/output/{relative}"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    size = 0
    try:
        assert process.stdout is not None
        with target.open("xb") as output:
            while chunk := process.stdout.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise RenderError("RENDER_OUTPUT_INVALID")
                output.write(chunk)
                digest.update(chunk)
        if process.wait(timeout=15) != 0 or size == 0:
            raise RenderError("RENDER_OUTPUT_INVALID")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    return digest.hexdigest()


def render_template(
    template_id: str,
    parameters: dict[str, object],
    *,
    work_root: Path | None = None,
    timeout_seconds: float = 120,
    container_name: str | None = None,
) -> RenderedCandidate:
    """Return only validated local candidate bytes; publication is a later task."""
    spec = load_template(template_id, require_executable=True)
    normalized = normalize_parameters(spec, parameters)
    if template_id not in _TEMPLATES:
        raise RenderError("RENDER_SOURCE_REJECTED")
    root = work_root or ROOT / "data" / "videos" / "cache" / "attempts"
    root.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix="render-", dir=root))
    input_dir, output_dir = attempt / "input", attempt / "candidate"
    input_dir.mkdir()
    output_dir.mkdir()
    container_id: str | None = None
    completed = False
    deadline = time.monotonic() + min(timeout_seconds, 120)
    try:
        _stage_input(template_id, normalized, input_dir)
        _, _, scene, module = _TEMPLATES[template_id]
        name = container_name or "edumind-render-" + uuid.uuid4().hex
        if not re.fullmatch(r"edumind-render-[0-9a-f]{32}", name):
            raise RenderError("RENDER_SOURCE_REJECTED")
        command = [
            "run", "-d", "--rm", "--name", name, "--network", "none", "--read-only",
            "--user", "10001:10001", "--cpus", "2", "--memory", "1g",
            "--pids-limit", "128", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
            "--tmpfs", f"/output:rw,nosuid,nodev,size={OUTPUT_QUOTA_BYTES},mode=1777",
            "--mount", f"type=bind,source={input_dir},destination=/input,readonly",
            "-e", "PYTHONPATH=/input/backend", "-e", "XDG_CACHE_HOME=/tmp",
            IMAGE, "python", "/input/backend/app/animation_templates/container_runner.py",
            template_id,
        ]
        started = _docker(command, timeout=15, check=True).stdout.decode("ascii").strip()
        if len(started) != 64 or any(char not in "0123456789abcdef" for char in started):
            raise RenderError("RENDER_UNAVAILABLE")
        container_id = started
        manifest: dict[str, object] | None = None
        while time.monotonic() < deadline:
            response = _docker(["exec", container_id, "cat", "/output/.ready"], timeout=10)
            if response.returncode == 0:
                manifest = json.loads(response.stdout)
                break
            state = _docker(["inspect", "--format", "{{.State.Running}}", container_id])
            if state.returncode != 0 or state.stdout.strip() != b"true":
                raise RenderError("RENDER_FAILED")
            time.sleep(1)
        if manifest is None:
            raise RenderError("RENDER_TIMEOUT")
        mp4_relative = f"videos/{module}/480p15/{scene}.mp4"
        srt_relative = f"{scene}.srt"
        if manifest.get("mp4") != mp4_relative or manifest.get("srt") != srt_relative:
            raise RenderError("RENDER_OUTPUT_INVALID")
        mp4_path, srt_path = output_dir / f"{scene}.mp4", output_dir / f"{scene}.srt"
        mp4_hash = _stream_artifact(container_id, mp4_relative, mp4_path)
        srt_hash = _stream_artifact(container_id, srt_relative, srt_path)
        if mp4_hash != manifest.get("mp4_sha256") or srt_hash != manifest.get("srt_sha256"):
            raise RenderError("RENDER_OUTPUT_INVALID")
        duration = manifest.get("duration_seconds")
        if not isinstance(duration, (int, float)) or not 30 <= duration <= 90:
            raise RenderError("RENDER_OUTPUT_INVALID")
        completed = True
        return RenderedCandidate(attempt, mp4_path, srt_path, float(duration), mp4_hash,
                                 srt_hash)
    except RenderError:
        raise
    except Exception as error:
        raise RenderError("RENDER_FAILED") from error
    finally:
        cleanup_failed = False
        if container_id is not None:
            try:
                removed = _docker(["rm", "-f", container_id], timeout=10)
                cleanup_failed = removed.returncode != 0
            except RenderError:
                cleanup_failed = True
        if completed and not cleanup_failed:
            shutil.rmtree(input_dir)
        else:
            shutil.rmtree(attempt)
        if cleanup_failed:
            raise RenderError("RENDER_UNAVAILABLE")
