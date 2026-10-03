"""Browser download behavior with route fixtures; real backend validation is separate."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("EDUMIND_E2E_BASE_URL", "http://127.0.0.1:4173")
UNIT = "unit-export-0001"
MP4 = b"\x00\x00\x00\x18ftypisom reviewed MP4 bytes"
SRT = "1\n00:00:00,000 --> 00:00:01,000\n链表插入\n".encode()
NOTES = "# 学习笔记\n\n当前已审核讲解 v2\n".encode()


def run() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 375, "height": 812}, accept_downloads=True
            )
            page = context.new_page()
            page.add_init_script(
                """{
                  const unit = """ + json.dumps(UNIT) + """;
                  sessionStorage.setItem('edumind:last-learning-unit', unit);
                  sessionStorage.setItem(`edumind:animation:${unit}:scene-current`, JSON.stringify({
                    sceneId:'scene-current', requestKey:'saved', jobId:'job-current',
                    request:{template_id:'linked-list-insertion', template_version:'1.0.0',
                      scene_version:2, parameters:{values:[1,3,5], index:1, value:4}}
                  }));
                }""",
            )
            requests = []

            def route_api(route):
                request = route.request
                request_path = urlsplit(request.url).path
                if not request_path.startswith("/api/"):
                    return route.continue_()
                path = request_path.removeprefix("/api/")
                requests.append((request.method, path))
                if path == "auth/session":
                    return route.fulfill(json={"csrf_token": "csrf"})
                if path == f"learning-units/{UNIT}":
                    return route.fulfill(json={
                        "knowledge_node_id": "linked-list-insertion",
                        "scenes": [
                            {"id": "scene-old", "scene_key": "intro", "version": 1,
                             "is_current": False, "resources": [{
                                 "id": "resource-old", "type": "explanation", "version": 1,
                                 "review_status": "passed", "content": {"markdown": "旧版讲解"}}]},
                            {"id": "scene-current", "scene_key": "intro", "version": 2,
                             "is_current": True, "resources": [{
                                 "id": "resource-current", "type": "explanation", "version": 2,
                                 "review_status": "passed",
                                 "content": {"markdown": "当前已审核讲解 v2"}}]},
                        ],
                    })
                if path == "animation-jobs/job-current":
                    return route.fulfill(json={
                        "id": "job-current", "learning_unit_id": UNIT,
                        "template_id": "linked-list-insertion", "status": "succeeded",
                        "attempt": 1, "progress": 1, "last_event_id": 2,
                        "media_id": "media-current",
                    })
                if path == f"learning-units/{UNIT}/notes.md":
                    return route.fulfill(body=NOTES, headers={
                        "Content-Type": "text/markdown; charset=utf-8",
                        "Content-Disposition": f'attachment; filename="learning-notes-{UNIT}.md"',
                    })
                if path.startswith("animation-media/media-current/"):
                    extension = "mp4" if "/mp4" in path else "srt"
                    body = MP4 if extension == "mp4" else SRT
                    return route.fulfill(body=body, headers={
                        "Content-Type": (
                            "video/mp4" if extension == "mp4" else "application/x-subrip"
                        ),
                        "Content-Disposition": (
                            f'attachment; filename="animation-media-current.{extension}"'
                        ),
                    })
                return route.fulfill(status=404, json={"code": "NOT_FOUND"})

            page.route("**/api/**", route_api)
            page.goto(BASE)
            expect(page.get_by_test_id("download-notes")).to_be_enabled()
            expect(page.get_by_test_id("download-mp4")).to_be_visible()
            for test_id, expected_name, expected_bytes in (
                ("download-notes", f"learning-notes-{UNIT}.md", NOTES),
                ("download-mp4", "animation-media-current.mp4", MP4),
                ("download-srt", "animation-media-current.srt", SRT),
            ):
                page.get_by_test_id(test_id).focus()
                with page.expect_download() as result:
                    page.keyboard.press("Enter")
                download = result.value
                assert download.suggested_filename == expected_name
                assert Path(download.path()).read_bytes() == expected_bytes
            page.evaluate(
                "unit => sessionStorage.setItem('edumind:scene-selection:' + unit, 'scene-old')",
                UNIT,
            )
            page.reload()
            expect(page.get_by_test_id("download-notes")).to_be_disabled()
            expect(page.get_by_test_id("download-mp4")).to_have_count(0)
            assert not any(
                method == "POST" and ("animations" in path or "learning-sessions" in path)
                for method, path in requests
            ), requests
            print("Mobile keyboard export browser route check passed", flush=True)
        finally:
            browser.close()
