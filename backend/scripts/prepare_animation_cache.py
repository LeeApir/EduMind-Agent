"""Prepare the two reviewed public baseline animation assets; no user data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.animation_cache import AnimationCache  # noqa: E402

BASELINES = {
    "linked-list-insertion": {"values": [1, 3, 5], "index": 1, "value": 2},
    "linked-list-deletion": {"values": [1, 3, 5], "index": 1},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", choices=(*BASELINES, "both"), default="both")
    args = parser.parse_args()
    selected = BASELINES if args.template == "both" else {args.template: BASELINES[args.template]}
    cache = AnimationCache()
    results = []
    for template_id, parameters in selected.items():
        media = cache.resolve(template_id, parameters)
        results.append({
            "template_id": template_id,
            "cache_key": media.cache_key,
            "cache_hit": media.cache_hit,
            "mp4_sha256": media.mp4_sha256,
            "srt_sha256": media.srt_sha256,
            "duration_seconds": media.duration_seconds,
        })
    print(json.dumps(results, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
