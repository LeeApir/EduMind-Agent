"""Decode only host-supplied MP4 bytes inside the existing restricted render container."""

import hashlib
import io
import json
import sys
from pathlib import Path

import av  # type: ignore[import-not-found]


def main() -> None:
    # stdin is the artifact independently copied/hash-checked by the host, not a .ready claim.
    data = sys.stdin.buffer.read(64 * 1024 * 1024 + 1)
    if not 0 < len(data) <= 64 * 1024 * 1024:
        raise ValueError("DSL_MEDIA_INVALID")
    expected = json.loads(Path("/input/manifest.json").read_text())
    expected_ms = expected["duration_ms"]
    with av.open(io.BytesIO(data)) as media:
        if len(media.streams) != 1 or len(media.streams.video) != 1 or media.duration is None:
            raise ValueError("DSL_MEDIA_INVALID")
        stream = media.streams.video[0]
        if stream.height != 720 or stream.width != 1280 or stream.average_rate != 15:
            raise ValueError("DSL_MEDIA_INVALID")
        count = 0
        for frame in media.decode(stream):
            if frame.height != 720 or frame.width != 1280:
                raise ValueError("DSL_MEDIA_INVALID")
            count += 1
            if count > 1351:
                raise ValueError("DSL_MEDIA_INVALID")
        duration = media.duration / 1_000_000
        if (
            not 30 <= duration <= 90
            or abs(duration - expected_ms / 1000) > 1 / 15 + 1e-6
            or abs(count - expected_ms * 15 / 1000) > 1
        ):
            raise ValueError("DSL_MEDIA_INVALID")
    print(
        json.dumps(
            {
                "mp4_sha256": hashlib.sha256(data).hexdigest(),
                "duration_seconds": duration,
                "frames": count,
                "height": 720,
                "width": 1280,
                "fps": 15,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
