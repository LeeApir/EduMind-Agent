"""Reproduce the reviewed deletion scene with data-only parameters in pinned Manim."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.animation_templates.deletion_plan import srt_for_deletion  # noqa: E402
from app.services.animation_templates import (  # noqa: E402
    load_template,
    normalize_parameters,
)

IMAGE = (
    "manimcommunity/manim@"
    "sha256:89ab433ce59134a4dcf351deb2511e067ab354393c0bb7d1859f3e8f0b2406a3"
)
SCENE = "LinkedListDeletionScene"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("single", "head", "middle", "tail"), required=True)
    parser.add_argument("--parameters", required=True, help="JSON object with values and index")
    args = parser.parse_args()
    parameters = normalize_parameters(
        load_template("linked-list-deletion"), json.loads(args.parameters)
    )
    output = ROOT / "data" / "videos" / "cache" / "t007" / args.case
    output.mkdir(parents=True, exist_ok=True)
    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m", "--cpus", "2",
        "--memory", "1g", "--pids-limit", "128", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "-e", "PYTHONPATH=/project/backend", "-e", "XDG_CACHE_HOME=/tmp",
        "-e", "EDUMIND_ANIMATION_PARAMETERS=" + json.dumps(parameters, separators=(",", ":")),
        "-v", f"{BACKEND}:/project/backend:ro",
        "-v", f"{ROOT / 'data' / 'animation_templates'}:/project/data/animation_templates:ro",
        "-v", f"{output}:/output", "-w", "/project/backend", IMAGE,
        "manim", "-ql", "--media_dir", "/output",
        "app/animation_templates/linked_list_deletion.py", SCENE,
    ]
    subprocess.run(command, check=True)
    video = output / "videos" / "linked_list_deletion" / "480p15" / f"{SCENE}.mp4"
    if not video.is_file() or video.stat().st_size == 0:
        raise RuntimeError("Manim did not produce a video")
    subtitle = output / f"{SCENE}.srt"
    subtitle.write_text(srt_for_deletion(), encoding="utf-8")
    print(f"MP4: {video}\nSRT: {subtitle}")


if __name__ == "__main__":
    main()
