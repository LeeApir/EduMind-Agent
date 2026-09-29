"""Route-mocked Chromium flow for reviewed debate entry, refresh, exit, and failure."""

import json
from urllib.parse import urlparse

from learning_flow import BASE_URL, open_page, sse, submit
from playwright.sync_api import Route, expect, sync_playwright

UNIT_ID = "unit-reviewed-001"
ORIGINAL = {
    "learning_unit_id": UNIT_ID, "revision": 1, "message_cursor": 5,
    "scene_key": "intro", "scene_version": 1, "scene_progress": 3,
    "mode": "interactive", "enabled_roles": ["beginner"], "paused": False,
}
RESULT = {
    "id": "result-debate-1", "scene_key": "array-vs-linked-list",
    "scene_version": 1, "status": "published",
    "question": "频繁随机访问时怎么选？",
    "question_conditions": {"stated": ["频繁随机访问"], "unknown": ["插入频率"]},
    "perspectives": {
        "performance": '<img src=x onerror="alert(1)"> 数组下标访问更合适',
        "engineering": "考虑维护成本", "academic": "先说明操作模型",
    },
    "moderator": {
        "objective_conclusion": "给定随机访问条件下优先数组",
        "tradeoffs": "插入时可能搬移元素", "learner_advice": "列出操作频率再判断",
    },
    "moderator_summary": "给定条件下优先数组。",
    "candidate_schema_version": "v1", "candidate_prompt_version": "v1",
    "generation_model_id": "fake-generation", "review_version": "v1",
    "review_model_id": "fake-review", "correction_attempts": 0,
}


def run() -> None:
    snapshot = dict(ORIGINAL)
    posts = 0

    def debate_api(route: Route) -> None:
        nonlocal snapshot, posts
        request = route.request
        path = urlparse(request.url).path
        base = f"/api/learning-units/{UNIT_ID}/classroom"
        if path == base:
            route.fulfill(status=200, json=snapshot)
            return
        if path == f"{base}/messages":
            route.fulfill(status=200, json={"messages": [], "last_message_cursor": 5})
            return
        if path == f"{base}/debate" and request.method == "POST":
            posts += 1
            assert request.headers.get("if-match-classroom-revision") == str(snapshot["revision"])
            assert request.headers.get("idempotency-key")
            assert request.headers.get("x-csrf-token")
            assert json.loads(request.post_data or "{}")["preset"] == "array-vs-linked-list"
            if posts == 3:
                route.fulfill(status=200, content_type="text/event-stream", body=sse(
                    ("agent_start", {"operation_id": "op-rejected"}),
                    ("error", {"code": "REVIEW_REJECTED", "retryable": False}),
                    ("done", {"status": "failed"}),
                ))
                return
            next_revision = int(snapshot["revision"]) + 1
            snapshot = {
                **ORIGINAL, "revision": next_revision, "scene_key": "array-vs-linked-list",
                "scene_progress": 0, "mode": "focus", "enabled_roles": [], "paused": True,
                "detour": {"kind": "debate", "result_id": "result-debate-1",
                           "scene_key": "intro", "scene_version": 1,
                           "scene_progress": 3, "mode": "interactive",
                           "enabled_roles": ["beginner"], "paused": False},
            }
            route.fulfill(status=200, content_type="text/event-stream", body=sse(
                ("agent_start", {"operation_id": "op-debate-1"}),
                ("stage_changed", {"stage": "reviewing"}),
                ("review_pass", {"kind": "debate"}),
                ("debate_ready", {"result_id": "result-debate-1"}),
                ("done", {"status": "published"}),
            ))
            return
        if path == f"{base}/debate/result-debate-1":
            route.fulfill(status=200, json=RESULT)
            return
        if path == f"{base}/debate/result-debate-1/exit":
            assert request.headers.get("if-match-classroom-revision") == str(snapshot["revision"])
            assert request.headers.get("idempotency-key")
            snapshot = {**ORIGINAL, "revision": int(snapshot["revision"]) + 1}
            route.fulfill(status=200, json=snapshot)
            return
        route.fallback()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            open_page(page)
            page.route(f"{BASE_URL}/api/**", debate_api)
            submit(page, "学习单链表")
            expect(page.get_by_test_id("debate-panel")).to_be_visible()
            page.get_by_role("button", name="练习", exact=True).click()
            page.get_by_label("头节点变量？").fill("head")
            page.get_by_test_id("debate-question").fill("频繁随机访问时怎么选？")
            page.get_by_test_id("start-debate").click()
            expect(page.get_by_test_id("debate-perspectives")).to_contain_text("数组下标访问")
            assert page.locator("[data-testid=debate-perspectives] img").count() == 0
            expect(page.get_by_test_id("debate-moderator")).to_contain_text("给定随机访问条件")
            expect(page.get_by_test_id("classroom-panel")).to_be_hidden()
            page.get_by_test_id("exit-debate").click()
            expect(page.get_by_test_id("classroom-panel")).to_be_visible()
            expect(page.get_by_label("头节点变量？")).to_have_value("head")
            page.get_by_test_id("start-debate").click()
            expect(page.get_by_test_id("debate-perspectives")).to_be_visible()
            page.reload()
            expect(page.get_by_test_id("debate-perspectives")).to_contain_text("数组下标访问")
            page.get_by_test_id("exit-debate").click()
            expect(page.get_by_test_id("classroom-panel")).to_be_visible()
            assert snapshot["scene_progress"] == 3 and snapshot["message_cursor"] == 5
            page.get_by_test_id("debate-question").fill("另一种对比问题")
            page.get_by_test_id("start-debate").click()
            expect(page.get_by_test_id("debate-error")).to_contain_text("未通过审核")
            expect(page.get_by_test_id("classroom-panel")).to_be_visible()
            assert snapshot["revision"] == 5
        finally:
            browser.close()


if __name__ == "__main__":
    run()
