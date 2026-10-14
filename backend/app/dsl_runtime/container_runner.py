"""Pinned data-only DSL scene runner. All execution is confined to the quota-limited image."""

import hashlib
import json
import py_compile
import shutil
import subprocess
import sys
import time
from pathlib import Path

from font_check import check_font

INPUT = Path("/input")
OUTPUT = Path("/output")
MAX_FILE = 64 * 1024 * 1024


def main() -> None:
    started = time.monotonic()
    expected = json.loads((INPUT / "manifest.json").read_text())
    source = (INPUT / "DSLScene.py").read_bytes()
    subtitle = (INPUT / "DSLScene.srt").read_bytes()
    if (
        hashlib.sha256(source).hexdigest() != expected["source_sha256"]
        or hashlib.sha256(subtitle).hexdigest() != expected["subtitles_sha256"]
    ):
        raise ValueError("DSL_RENDER_UNAVAILABLE")
    checked = subprocess.run(
        [
            sys.executable,
            str(INPUT / "animation_dsl_static.py"),
            expected["static_sha256"],
            expected["static_policy_sha256"],
        ],
        input=source,
        capture_output=True,
        timeout=1,
        env={},
    )
    if checked.returncode or json.loads(checked.stdout).get("nodes") != expected["ast_nodes"]:
        raise ValueError("DSL_COMPILE_REJECTED")
    check_font(source)
    # Native syntax/import validation happens only here, never in the host process.
    py_compile.compile(str(INPUT / "DSLScene.py"), cfile="/tmp/DSLScene.pyc", doraise=True)
    try:
        rendered = subprocess.run(
            [
                "manim",
                "--resolution",
                "1280,720",
                "--fps",
                "15",
                "--disable_caching",
                "--media_dir",
                str(OUTPUT),
                str(INPUT / "DSLScene.py"),
                "DSLScene",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=max(0.01, 120 - (time.monotonic() - started)),
        )
    except subprocess.TimeoutExpired:
        raise ValueError("DSL_RENDER_TIMEOUT") from None
    if rendered.returncode:
        raise ValueError("DSL_RENDER_FAILED")
    original = OUTPUT / "videos/DSLScene/720p15/DSLScene.mp4"
    video = OUTPUT / "DSLScene.mp4"
    if original.is_symlink() or not original.is_file() or original.stat().st_nlink != 1:
        raise ValueError("DSL_MEDIA_INVALID")
    original.replace(video)
    (OUTPUT / "DSLScene.srt").write_bytes(subtitle)
    for name in ("videos", "texts", "images"):
        shutil.rmtree(OUTPUT / name, ignore_errors=True)
    allowed = {"DSLScene.mp4", "DSLScene.srt"}
    entries = list(OUTPUT.iterdir())
    if {p.name for p in entries} != allowed:
        raise ValueError("DSL_MEDIA_INVALID")
    if any(
        p.is_symlink()
        or not p.is_file()
        or p.stat().st_nlink != 1
        or not 0 < p.stat().st_size <= MAX_FILE
        for p in entries
    ):
        raise ValueError("DSL_MEDIA_INVALID")
    # Ready is only a completion hint. Host rechecks exact SRT/hash and re-decodes copied MP4.
    (OUTPUT / ".ready").write_text(
        json.dumps(
            {
                "source_sha256": expected["source_sha256"],
                "mp4_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                "srt_sha256": hashlib.sha256(subtitle).hexdigest(),
            },
            sort_keys=True,
        )
    )
    # Retire an orphan after 130 seconds; lease cleanup normally happens earlier.
    while time.monotonic() < started + 130:
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        code = str(error)
        allowed = {
            "DSL_RENDER_UNAVAILABLE",
            "DSL_COMPILE_REJECTED",
            "DSL_RENDER_TIMEOUT",
            "DSL_RENDER_FAILED",
            "DSL_MEDIA_INVALID",
        }
        try:
            (OUTPUT / ".failed").write_text(code if code in allowed else "DSL_RENDER_FAILED")
        except OSError:
            pass
        sys.exit(1)
