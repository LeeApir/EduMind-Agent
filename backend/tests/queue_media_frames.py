"""Seek actual generated template MP4s for supplementary visual inspection."""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    output = Path(sys.argv[1]).resolve()
    report = json.loads((output / "matrix-result.json").read_text())
    inspected = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 960, "height": 540})
        for index in (4, 14):
            slot = report["template_slots"][index]
            media = output / "media-cache/objects" / (slot["mp4_sha256"] + ".mp4")
            page.goto(media.as_uri())
            page.wait_for_function("document.querySelector('video')?.readyState >= 2")
            for seconds in (15, 21, 33):
                page.evaluate(
                    """async t => {
                    const video = document.querySelector('video'); video.pause();
                    await new Promise(resolve => {
                        video.addEventListener('seeked', resolve, {once:true});
                        video.currentTime = t;
                    });
                }""",
                    seconds,
                )
                filename = slot["id"] + f"-frame-{seconds}.png"
                page.screenshot(path=str(output / filename))
                inspected.append(
                    {
                        "slot_id": slot["id"],
                        "seconds": seconds,
                        "mp4_sha256": slot["mp4_sha256"],
                        "frame": filename,
                    }
                )
        browser.close()
    (output / "visual-frames.json").write_text(
        json.dumps(
            {
                "qualification": "supplementary generated-media frames; not human signoff",
                "frames": inspected,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
