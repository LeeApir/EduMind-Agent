"""Browser E2E for the focus/interactive classroom panel with route-mocked API.

Exercises the real ``ClassroomPanel.vue`` component and ``classroom.ts`` API client
in headless Chromium against the exact classroom SSE wire format: default focus
view, on-demand companion roles, streaming speech with a current-speaker marker,
XSS escaping, keyboard submit, and idempotent error retry. It reuses the
``learning_flow.py`` route-mock convention, so no backend or provider is required;
the durable server path is covered by the backend classroom suite against a mock
provider (``tests/test_classroom_speech_api.py``).
"""

import json
import os
from urllib.parse import urlparse

from playwright.sync_api import Route, expect, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

BASE_URL = os.getenv("EDUMIND_E2E_BASE_URL", "http://127.0.0.1:4173")

UNIT_ID = "unit-classroom-001"
SPEECH_POSTS: list[dict[str, str]] = []
MODE_POSTS: list[dict[str, object]] = []
FAIL_NEXT_SPEECH = False

SNAPSHOT: dict[str, object] = {
    "learning_unit_id": UNIT_ID,
    "revision": 1,
    "message_cursor": 0,
    "scene_key": "intro",
    "scene_version": 1,
    "scene_progress": 0,
    "mode": "focus",
    "enabled_roles": [],
    "paused": False,
}

COMMITTED: list[dict[str, object]] = []
_next_cursor = 0
_next_message_id = 0


def sse(*events: tuple[str, dict[str, object]]) -> str:
    return "".join(
        f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for event, data in events
    )


def commit_messages(text: str, tutor_text: str) -> None:
    global _next_cursor, _next_message_id
    for role, body in (("student", text), ("tutor", tutor_text)):
        _next_cursor += 1
        _next_message_id += 1
        COMMITTED.append(
            {
                "id": f"cm-{_next_message_id}",
                "cursor": _next_cursor,
                "role": role,
                "scene_key": "intro",
                "scene_version": 1,
                "text": body,
            }
        )
    SNAPSHOT["message_cursor"] = _next_cursor


def messages_payload(after: int) -> dict[str, object]:
    rows = [message for message in COMMITTED if int(message["cursor"]) > after]
    return {"messages": rows, "last_message_cursor": int(SNAPSHOT["message_cursor"])}


def mock_api(route: Route) -> None:
    global FAIL_NEXT_SPEECH
    request = route.request
    path = urlparse(request.url).path

    if path == "/api/auth/session":
        route.fulfill(status=401, json={"code": "UNAUTHORIZED"})
        return
    if path == "/api/auth/guest":
        route.fulfill(status=201, json={"csrf_token": "c" * 64, "user": {"id": "user-classroom"}})
        return
    if path == "/api/profile/me":
        route.fulfill(status=404, json={"code": "NOT_FOUND"})
        return
    if path == "/api/quiz-submissions/latest":
        route.fulfill(status=404, json={"code": "NOT_FOUND"})
        return
    if path == "/api/learning-sessions":
        route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=sse(
                ("agent_start", {"operation_id": "op-classroom", "stage": "preparing"}),
                ("token", {"operation_id": "op-classroom", "temporary": True, "delta": "先理解 next 指针。"}),
                ("stage_changed", {"operation_id": "op-classroom", "stage": "reviewing"}),
                ("review_pass", {"operation_id": "op-classroom", "attempt": 1}),
                (
                    "scene_ready",
                    {
                        "operation_id": "op-classroom",
                        "learning_unit_id": UNIT_ID,
                        "scene_id": "scene-classroom",
                        "version": 1,
                        "resource_ids": ["resource-explanation", "resource-code", "resource-exercise"],
                    },
                ),
                ("done", {"operation_id": "op-classroom", "status": "published"}),
            ),
        )
        return
    if path == f"/api/learning-units/{UNIT_ID}":
        route.fulfill(
            status=200,
            json={
                "id": UNIT_ID,
                "status": "ready",
                "scenes": [
                    {
                        "resources": [
                            {
                                "id": "resource-explanation",
                                "type": "explanation",
                                "version": 1,
                                "review_status": "passed",
                                "content": {"markdown": "链表节点通过 next 指针连接。"},
                            },
                            {
                                "id": "resource-code",
                                "type": "code",
                                "version": 1,
                                "review_status": "passed",
                                "content": {"source": "node->next = head;"},
                            },
                            {
                                "id": "resource-exercise",
                                "type": "exercise",
                                "version": 1,
                                "review_status": "passed",
                                "content": {"items": [{"id": "q1", "question": "插入前先保存什么？"}]},
                            },
                        ]
                    }
                ],
            },
        )
        return
    if path == f"/api/learning-units/{UNIT_ID}/classroom/mode":
        assert request.method == "PATCH"
        assert request.headers.get("if-match-classroom-revision") == str(SNAPSHOT["revision"])
        assert request.headers.get("x-csrf-token")
        assert request.headers.get("idempotency-key")
        payload = json.loads(request.post_data or "{}")
        MODE_POSTS.append(payload)
        SNAPSHOT["revision"] = int(SNAPSHOT["revision"]) + 1
        SNAPSHOT["mode"] = payload["mode"]
        SNAPSHOT["enabled_roles"] = payload["enabled_roles"]
        route.fulfill(status=200, json=SNAPSHOT)
        return
    if path == f"/api/learning-units/{UNIT_ID}/classroom/messages":
        if request.method == "POST":
            text = json.loads(request.post_data or "{}").get("text", "")
            SPEECH_POSTS.append(
                {
                    "text": text,
                    "key": request.headers.get("idempotency-key", ""),
                    "revision": request.headers.get("if-match-classroom-revision", ""),
                }
            )
            if FAIL_NEXT_SPEECH:
                FAIL_NEXT_SPEECH = False
                route.fulfill(
                    status=200,
                    content_type="text/event-stream",
                    body=sse(
                        ("agent_start", {"operation_id": "op-speech-err", "revision": 1, "scene_version": 1}),
                        (
                            "error",
                            {
                                "operation_id": "op-speech-err",
                                "code": "PROVIDER_UNAVAILABLE",
                                "message": "模型服务暂不可用，请稍后重试。",
                                "retryable": True,
                            },
                        ),
                        ("done", {"operation_id": "op-speech-err", "status": "failed"}),
                    ),
                )
                return
            if "XSS" in text:
                hostile = "<img src=x onerror=alert(1)>"
                tutor_text = hostile
                tokens = [("tutor", hostile)]
            else:
                tutor_text = "先保存后继，再改前驱。"
                tokens = [("tutor", "先保存后继，"), ("tutor", "再改前驱。")]
            commit_messages(text, tutor_text)
            body = sse(
                ("agent_start", {"operation_id": "op-speech-ok", "revision": 1, "scene_version": 1}),
                *[("token", {"role": role, "delta": delta, "temporary": True}) for role, delta in tokens],
                ("review_pass", {"operation_id": "op-speech-ok", "kind": "speech"}),
                (
                    "message_ready",
                    {
                        "revision": 1,
                        "message_cursor": int(SNAPSHOT["message_cursor"]),
                        "message_id": COMMITTED[-1]["id"],
                    },
                ),
                ("done", {"status": "published"}),
            )
            route.fulfill(status=200, content_type="text/event-stream", body=body)
            return
        query = urlparse(request.url).query
        after = int(query.split("=", 1)[1]) if query.startswith("after=") else 0
        route.fulfill(status=200, json=messages_payload(after))
        return
    if path == f"/api/learning-units/{UNIT_ID}/classroom":
        route.fulfill(status=200, json=SNAPSHOT)
        return
    if path.startswith("/api/classroom-operations/"):
        route.fulfill(
            status=200,
            json={
                "id": path.rsplit("/", 1)[-1],
                "status": "published",
                "learning_unit_id": UNIT_ID,
                "kind": "speech",
                "base_revision": 1,
            },
        )
        return
    route.fulfill(status=404, json={"code": "NOT_FOUND"})


def open_page(page) -> None:
    global FAIL_NEXT_SPEECH
    SPEECH_POSTS.clear()
    MODE_POSTS.clear()
    FAIL_NEXT_SPEECH = False
    page.on(
        "console",
        lambda message: print(f"browser console [{message.type}]: {message.text}", flush=True),
    )
    page.on("pageerror", lambda error: print(f"browser pageerror: {error}", flush=True))
    page.route(f"{BASE_URL}/api/**", mock_api)
    page.goto(BASE_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=1_000)
    except PlaywrightTimeoutError:
        page.wait_for_load_state("domcontentloaded")


def run() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(8_000)

            print("E2E classroom: setup + default focus view", flush=True)
            open_page(page)
            page.get_by_label("学习目标").fill("我想理解链表插入")
            page.get_by_role("button", name="开始学习").click()
            page.get_by_test_id("classroom-panel").wait_for(timeout=15000)
            expect(page.get_by_test_id("mode-tag")).to_contain_text("专注模式")
            expect(page.get_by_test_id("role-toggles")).to_have_count(0)

            print("E2E classroom: switch interactive, enable companions", flush=True)
            page.get_by_test_id("toggle-mode").click()
            expect(page.get_by_test_id("mode-tag")).to_contain_text("互动模式")
            expect(page.get_by_test_id("role-toggles")).to_have_count(1)
            expect(page.get_by_test_id("role-beginner")).to_have_attribute("aria-pressed", "true")
            expect(page.get_by_test_id("role-advanced")).to_have_attribute("aria-pressed", "true")
            assert MODE_POSTS == [
                {"mode": "interactive", "enabled_roles": ["beginner", "advanced"]}
            ], MODE_POSTS

            print("E2E classroom: keyboard submit commits the streamed turn", flush=True)
            page.get_by_test_id("speech-input").fill("为什么先保存后继？")
            page.get_by_test_id("speech-input").press("Enter")
            transcript = page.get_by_test_id("transcript")
            expect(transcript).to_contain_text("为什么先保存后继？")
            expect(transcript).to_contain_text("先保存后继，再改前驱。")
            expect(transcript.locator(".message-student")).to_have_count(1)
            expect(transcript.locator(".message-tutor")).to_have_count(1)
            assert SPEECH_POSTS[-1]["text"] == "为什么先保存后继？"

            print("E2E classroom: button submit", flush=True)
            page.get_by_test_id("speech-input").fill("再来一个例子")
            page.get_by_test_id("send-speech").click()
            expect(transcript.locator(".message-student")).to_have_count(2)
            expect(transcript.locator(".message-tutor")).to_have_count(2)

            print("E2E classroom: XSS escaping in committed model content", flush=True)
            page.get_by_test_id("speech-input").fill("XSS 测试 <img src=x onerror=alert(1)>")
            page.get_by_test_id("speech-input").press("Enter")
            expect(transcript).to_contain_text("<img src=x onerror=alert(1)>")
            expect(transcript.locator("img")).to_have_count(0)
            expect(transcript.locator("script")).to_have_count(0)

            print("E2E classroom: definitive server error -> fresh-key retry", flush=True)
            global FAIL_NEXT_SPEECH
            FAIL_NEXT_SPEECH = True
            page.get_by_test_id("speech-input").fill("触发 Provider 故障")
            page.get_by_test_id("speech-input").press("Enter")
            expect(page.get_by_test_id("stream-error")).to_contain_text("未能完成")
            before = len(SPEECH_POSTS)
            page.get_by_test_id("retry-speech").click()
            expect(page.get_by_test_id("stream-error")).to_have_count(0)
            expect(page.get_by_test_id("transcript")).to_contain_text("先保存后继，再改前驱。")
            assert len(SPEECH_POSTS) == before + 1
            assert SPEECH_POSTS[-2]["key"] != SPEECH_POSTS[-1]["key"], SPEECH_POSTS

            print("E2E classroom: close interactive back to focus", flush=True)
            page.get_by_test_id("toggle-mode").click()
            expect(page.get_by_test_id("mode-tag")).to_contain_text("专注模式")
            expect(page.get_by_test_id("role-toggles")).to_have_count(0)

            print("E2E classroom: mobile viewport has no horizontal overflow", flush=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.close()

            print(
                json.dumps(
                    {
                        "speech_posts": len(SPEECH_POSTS),
                        "mode_posts": MODE_POSTS,
                        "committed_messages": len(COMMITTED),
                        "xss_escaped": True,
                        "keyboard_submit": True,
                        "mobile_ok": True,
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            browser.close()
    print("MVP 0.3 classroom browser route-mock E2E passed")


if __name__ == "__main__":
    run()
