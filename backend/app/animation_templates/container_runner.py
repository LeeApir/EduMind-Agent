"""Fixed renderer entrypoint inside the isolated, quota-limited container."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import av  # type: ignore[import-not-found]

OUTPUT = Path("/output")
SCENES = {
    "linked-list-insertion": "LinkedListInsertionScene",
    "linked-list-deletion": "LinkedListDeletionScene",
}


def main() -> None:
    started_at = time.monotonic()
    if len(sys.argv) != 2 or sys.argv[1] not in SCENES:
        raise ValueError("unsupported template")
    scene, module = SCENES[sys.argv[1]], "compiled_scene"
    if sys.argv[1] == "linked-list-insertion":
        from app.animation_templates.insertion_plan import srt_for_insertion

        subtitle_fn = srt_for_insertion
    else:
        from app.animation_templates.deletion_plan import srt_for_deletion

        subtitle_fn = srt_for_deletion
    subprocess.run(
        ["manim", "-ql", "--media_dir", str(OUTPUT), "/input/compiled_scene.py", scene],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    video = OUTPUT / "videos" / module / "480p15" / f"{scene}.mp4"
    subtitle = OUTPUT / f"{scene}.srt"
    subtitle.write_text(subtitle_fn(), encoding="utf-8")
    if video.is_symlink() or subtitle.is_symlink() or not video.is_file():
        raise ValueError("invalid media output")
    if video.stat().st_size > 64 * 1024 * 1024 or subtitle.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("media output too large")
    with av.open(str(video)) as media:
        streams = media.streams.video
        if len(streams) != 1 or media.duration is None:
            raise ValueError("invalid MP4")
        duration = media.duration / 1_000_000
        if not 30 <= duration <= 90 or streams[0].width <= 0 or streams[0].height <= 0:
            raise ValueError("invalid MP4 duration or dimensions")
        if sum(1 for _ in media.decode(streams[0])) == 0:
            raise ValueError("undecodable MP4")
    cues = subtitle.read_text(encoding="utf-8").strip().split("\n\n")
    if len(cues) not in (6, 7):
        raise ValueError("invalid SRT")
    for number, cue in enumerate(cues, start=1):
        lines = cue.splitlines()
        expected_time = (
            f"00:00:{(number - 1) * 6:02},000 --> 00:00:{number * 6:02},000"
        )
        if len(lines) != 3 or lines[0] != str(number) or lines[1] != expected_time:
            raise ValueError("invalid SRT timing")
        if not lines[2].strip():
            raise ValueError("empty SRT cue")
    if duration != len(cues) * 6:
        raise ValueError("SRT and MP4 are not synchronized")
    shutil.rmtree(OUTPUT / "texts", ignore_errors=True)
    shutil.rmtree(video.parent / "partial_movie_files", ignore_errors=True)
    expected = {video.relative_to(OUTPUT), subtitle.relative_to(OUTPUT)}
    actual = {path.relative_to(OUTPUT) for path in OUTPUT.rglob("*") if path.is_file()}
    if actual != expected or any(path.is_symlink() for path in OUTPUT.rglob("*")):
        raise ValueError("unexpected output file")
    manifest = {
        "mp4": str(video.relative_to(OUTPUT)),
        "srt": str(subtitle.relative_to(OUTPUT)),
        "duration_seconds": duration,
        "mp4_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        "srt_sha256": hashlib.sha256(subtitle.read_bytes()).hexdigest(),
    }
    (OUTPUT / ".ready").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    # A killed host worker cannot run its finally block. Exit and auto-remove
    # the container even if the host never retrieves the ready media.
    stop_at = started_at + 130
    while time.monotonic() < stop_at:
        time.sleep(1)


if __name__ == "__main__":
    main()
