"""Restricted render of freshly recompiled audited DSL; no candidate Python on the host."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import cast

from app.services.animation_dsl_compiler import CompiledDSL, compile_animation_dsl
from app.services.animation_dsl_runtime import IMAGE
from app.services.animation_renderer import (
    MAX_FILE_BYTES,
    OUTPUT_QUOTA_BYTES,
    ROOT,
    RenderController,
    RenderedCandidate,
    RenderError,
)

_RUNTIME = ROOT / "backend/app/dsl_runtime"
_SERVICES = Path(__file__).parent
_STAGED = {
    "font_check.py": _RUNTIME / "font_check.py",
    "container_runner.py": _RUNTIME / "container_runner.py",
    "verify_media.py": _RUNTIME / "verify_media.py",
    "animation_dsl_static.py": _SERVICES / "animation_dsl_static.py",
    "animation_dsl_compiler_policy.json": _SERVICES / "animation_dsl_compiler_policy.json",
}
_FROZEN = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in _STAGED.items()}
_RENDERER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_FAILURES = {
    "DSL_RENDER_UNAVAILABLE",
    "DSL_COMPILE_REJECTED",
    "DSL_RENDER_TIMEOUT",
    "DSL_RENDER_FAILED",
    "DSL_MEDIA_INVALID",
    "DSL_RENDER_RESOURCE_LIMIT",
}


def renderer_identity() -> str:
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != _RENDERER_SHA256:
        raise RenderError("DSL_RENDER_UNAVAILABLE")
    files = {**_FROZEN, "renderer": _RENDERER_SHA256}
    return hashlib.sha256(
        json.dumps(
            {
                "files": files,
                "image": IMAGE,
                "cpu": 2,
                "memory": 1073741824,
                "pids": 128,
                "wall_seconds": 120,
                "quota": OUTPUT_QUOTA_BYTES,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _docker(
    args: list[str], *, timeout: float, input_data: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["docker", *args],
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=max(0.01, timeout),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RenderError("DSL_RENDER_UNAVAILABLE") from None


def _copy_artifact(container: str, filename: str, target: Path, *, remaining: float) -> str:
    response = _docker(
        ["exec", container, "cat", f"/output/{filename}"], timeout=min(15, remaining)
    )
    if response.returncode or not 0 < len(response.stdout) <= MAX_FILE_BYTES:
        raise RenderError("DSL_MEDIA_INVALID")
    with target.open("xb") as f:
        f.write(response.stdout)
    return hashlib.sha256(response.stdout).hexdigest()


def render_compiled_dsl(
    compiled: CompiledDSL,
    *,
    work_root: Path | None = None,
    timeout_seconds: float = 120,
    container_name: str | None = None,
    controller: RenderController | None = None,
) -> RenderedCandidate:
    """Internal execution primitive. Worker resolves actual PG qualification before invoking it."""
    renderer_identity()  # Verify the loaded renderer matches the current frozen source.
    fresh = compile_animation_dsl(
        compiled.validated.canonical_json,
        knowledge_point_id=cast(str, compiled.validated.candidate["knowledge_point_id"]),
    )
    if fresh != compiled:
        raise RenderError("DSL_RENDER_UNAVAILABLE")
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120:
        raise RenderError("DSL_RENDER_UNAVAILABLE")
    for name, path in _STAGED.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != _FROZEN[name]:
            raise RenderError("DSL_RENDER_UNAVAILABLE")
    name = container_name or "edumind-render-" + uuid.uuid4().hex
    if not re.fullmatch(r"edumind-render-[0-9a-f]{32}", name):
        raise RenderError("DSL_RENDER_UNAVAILABLE")
    root = work_root or ROOT / "data/videos/cache/dsl-attempts"
    if root.is_symlink():
        raise RenderError("DSL_RENDER_UNAVAILABLE")
    root.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix="dsl-", dir=root))
    stage, output = attempt / "input", attempt / "candidate"
    stage.mkdir()
    output.mkdir()
    container = None
    completed = False
    deadline = time.monotonic() + timeout_seconds
    try:
        for filename, path in _STAGED.items():
            shutil.copyfile(path, stage / filename)
        (stage / "DSLScene.py").write_text(fresh.source, encoding="utf-8")
        (stage / "DSLScene.srt").write_text(fresh.subtitles, encoding="utf-8")
        manifest = {
            "source_sha256": fresh.source_sha256,
            "ast_sha256": fresh.ast_sha256,
            "ast_nodes": fresh.ast_nodes,
            "subtitles_sha256": fresh.subtitles_sha256,
            "static_sha256": _FROZEN["animation_dsl_static.py"],
            "static_policy_sha256": _FROZEN["animation_dsl_compiler_policy.json"],
            "duration_ms": fresh.validated.frames[-1].end_ms,
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        for path in stage.iterdir():
            path.chmod(0o444)
        stage.chmod(0o555)
        command = [
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--user",
            "10001:10001",
            "--cpus",
            "2",
            "--memory",
            "1g",
            "--pids-limit",
            "128",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
            "--tmpfs",
            f"/output:rw,nosuid,nodev,size={OUTPUT_QUOTA_BYTES},mode=1777",
            "--mount",
            f"type=bind,source={stage},destination=/input,readonly",
            "-e",
            "XDG_CACHE_HOME=/tmp",
            IMAGE,
            "python",
            "/input/container_runner.py",
        ]
        started = (
            controller.launch(command)
            if controller
            else _docker(command, timeout=15).stdout.decode("ascii").strip()
        )
        if not re.fullmatch(r"[0-9a-f]{64}", started):
            raise RenderError("DSL_RENDER_UNAVAILABLE")
        container = started
        ready = None
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            response = _docker(
                ["exec", container, "cat", "/output/.ready"], timeout=min(2, remaining)
            )
            if response.returncode == 0:
                if len(response.stdout) > 1024:
                    raise RenderError("DSL_MEDIA_INVALID")
                ready = json.loads(response.stdout)
                break
            failed = _docker(
                ["exec", container, "cat", "/output/.failed"], timeout=min(2, remaining)
            )
            if failed.returncode == 0:
                code = failed.stdout.decode().strip()
                raise RenderError(code if code in _FAILURES else "DSL_RENDER_FAILED")
            state = _docker(
                ["inspect", "--format", "{{json .State}}", container], timeout=min(2, remaining)
            )
            if state.returncode:
                raise RenderError("DSL_RENDER_FAILED")
            status = json.loads(state.stdout)
            if not status.get("Running"):
                raise RenderError(
                    "DSL_RENDER_RESOURCE_LIMIT" if status.get("OOMKilled") else "DSL_RENDER_FAILED"
                )
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        if ready is None:
            raise RenderError("DSL_RENDER_TIMEOUT")
        if type(ready) is not dict or ready.get("source_sha256") != fresh.source_sha256:
            raise RenderError("DSL_MEDIA_INVALID")
        mp4, srt = output / "DSLScene.mp4", output / "DSLScene.srt"
        mp4_hash = _copy_artifact(
            container, "DSLScene.mp4", mp4, remaining=deadline - time.monotonic()
        )
        srt_hash = _copy_artifact(
            container, "DSLScene.srt", srt, remaining=deadline - time.monotonic()
        )
        if (
            mp4_hash != ready.get("mp4_sha256")
            or srt_hash != fresh.subtitles_sha256
            or srt.read_text(encoding="utf-8") != fresh.subtitles
        ):
            raise RenderError("DSL_MEDIA_INVALID")
        # Re-decode actual bytes retrieved by the host. No dependency on a container-ready duration.
        checked = _docker(
            ["exec", "-i", container, "python", "/input/verify_media.py"],
            input_data=mp4.read_bytes(),
            timeout=min(20, deadline - time.monotonic()),
        )
        if checked.returncode or len(checked.stdout) > 1024:
            raise RenderError("DSL_MEDIA_INVALID")
        media = json.loads(checked.stdout)
        duration = media.get("duration_seconds")
        if (
            media.get("mp4_sha256") != mp4_hash
            or type(duration) not in (int, float)
            or not math.isfinite(duration)
            or not 30 <= duration <= 90
            or abs(duration - fresh.validated.duration_ms / 1000) > 1 / 15 + 1e-6
            or media.get("height") != 480
            or media.get("width") != 854
            or media.get("fps") != 15
        ):
            raise RenderError("DSL_MEDIA_INVALID")
        completed = True
        return RenderedCandidate(attempt, mp4, srt, float(duration), mp4_hash, srt_hash)
    except RenderError:
        raise
    except Exception:
        raise RenderError("DSL_RENDER_FAILED") from None
    finally:
        cleanup = True
        try:
            if controller is not None:
                cleanup = controller.stop()
            else:
                _docker(["rm", "-f", name], timeout=2)
                check = _docker(
                    ["ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"], timeout=2
                )
                cleanup = check.returncode == 0 and not check.stdout.strip()
        except Exception:
            cleanup = False
        if completed and cleanup:
            stage.chmod(0o755)
            shutil.rmtree(stage)
        else:
            stage.chmod(0o755)
            shutil.rmtree(attempt)
        if not cleanup:
            raise RenderError("DSL_RENDER_UNAVAILABLE")
