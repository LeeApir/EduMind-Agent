"""Browser E2E scenarios with deterministic, route-mocked API responses."""

import json
import os
from urllib.parse import urlparse

from playwright.sync_api import Page, Route, expect, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

BASE_URL = os.getenv("EDUMIND_E2E_BASE_URL", "http://127.0.0.1:4173")

RESOURCES = [
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
        "content": {
            "items": [
                {
                    "id": "q1",
                    "question": "插入前先保存什么？",
                    "answer": "next",
                    "explanation": "先保存 next 指针。",
                },
                {
                    "id": "q2",
                    "question": "头节点变量？",
                    "answer": "head",
                    "explanation": "使用 head。",
                },
                {
                    "id": "q3",
                    "question": "指针运算符？",
                    "answer": "->",
                    "explanation": "结构体指针使用 ->。",
                },
            ]
        },
    },
]


def sse(*events: tuple[str, dict[str, object]]) -> str:
    return "".join(
        f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for event, data in events
    )


def mock_api(route: Route) -> None:
    request = route.request
    path = urlparse(request.url).path
    if path == "/api/auth/session":
        route.fulfill(status=401, json={"code": "UNAUTHORIZED"})
        return
    if path == "/api/auth/guest":
        route.fulfill(status=201, json={"csrf_token": "c" * 64, "user": {"id": "user-1"}})
        return
    if path.startswith("/api/learning-units/"):
        route.fulfill(
            status=200,
            json={"id": "unit-1", "status": "ready", "scenes": [{"resources": RESOURCES}]},
        )
        return
    if path.startswith("/api/learning-operations/"):
        operation_id = path.rsplit("/", 1)[-1]
        if operation_id == "op-recover":
            route.fulfill(
                status=200,
                json={"status": "published", "learning_unit_id": "unit-1"},
            )
        else:
            route.fulfill(status=200, json={"status": "failed", "learning_unit_id": None})
        return
    if path != "/api/learning-sessions":
        route.fulfill(status=404, json={"code": "NOT_FOUND"})
        return

    goal = json.loads(request.post_data or "{}").get("goal", "")
    if "Provider 故障" in goal:
        body = sse(
            ("agent_start", {"operation_id": "op-provider", "stage": "preparing"}),
            (
                "error",
                {
                    "operation_id": "op-provider",
                    "code": "PROVIDER_UNAVAILABLE",
                    "message": "模型服务暂不可用，请稍后重试。",
                    "retryable": True,
                },
            ),
            ("done", {"operation_id": "op-provider", "status": "failed"}),
        )
    elif "审核拒绝" in goal:
        body = sse(
            ("agent_start", {"operation_id": "op-reject", "stage": "preparing"}),
            (
                "token",
                {"operation_id": "op-reject", "temporary": True, "delta": "这是一段临时讲解。"},
            ),
            ("stage_changed", {"operation_id": "op-reject", "stage": "reviewing"}),
            ("review_reject", {"operation_id": "op-reject", "attempt": 1, "retry": False}),
            ("done", {"operation_id": "op-reject", "status": "failed"}),
        )
    elif "SSE 恢复" in goal:
        body = (
            sse(
                ("agent_start", {"operation_id": "op-recover", "stage": "streaming_temporary"}),
                (
                    "token",
                    {
                        "operation_id": "op-recover",
                        "temporary": True,
                        "delta": "连接前已收到的首段。",
                    },
                ),
            )
            + "event: token\ndata: not-json\n\n"
        )
    else:
        body = sse(
            ("agent_start", {"operation_id": "op-success", "stage": "preparing"}),
            (
                "token",
                {"operation_id": "op-success", "temporary": True, "delta": "先理解 next 指针。"},
            ),
            ("stage_changed", {"operation_id": "op-success", "stage": "reviewing"}),
            ("review_pass", {"operation_id": "op-success", "attempt": 1}),
            (
                "scene_ready",
                {
                    "operation_id": "op-success",
                    "learning_unit_id": "unit-1",
                    "scene_id": "scene-1",
                    "version": 1,
                    "resource_ids": [resource["id"] for resource in RESOURCES],
                },
            ),
            ("done", {"operation_id": "op-success", "status": "published"}),
        )
    route.fulfill(status=200, content_type="text/event-stream", body=body)


def open_page(page: Page) -> None:
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
        # Vite's HMR connection can keep the dev page non-idle; DOM readiness is
        # sufficient once the explicit network-idle probe has timed out.
        page.wait_for_load_state("domcontentloaded")


def submit(page: Page, goal: str) -> None:
    page.get_by_label("学习目标").fill(goal)
    page.get_by_role("button", name="开始学习").click()


def run() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(5_000)
            print("E2E: success flow", flush=True)
            open_page(page)
            submit(page, "我想理解链表插入")
            expect(page.get_by_test_id("temporary-explanation")).to_contain_text("尚未审核")
            expect(page.get_by_test_id("published-state")).to_contain_text("已审核正式资源")
            page.get_by_role("button", name="代码", exact=True).click()
            expect(page.get_by_test_id("code-tab")).to_contain_text("node->next")
            page.get_by_role("button", name="练习", exact=True).click()
            page.get_by_label("插入前先保存什么？").fill("next")
            page.get_by_role("button", name="检查答案").first.click()
            expect(page.get_by_role("status")).to_contain_text("回答正确")
            page.screenshot(path="/tmp/edumind-t034-success.png", full_page=True)
            page.close()

            page = browser.new_page()
            page.set_default_timeout(5_000)
            print("E2E: provider failure", flush=True)
            open_page(page)
            submit(page, "模拟 Provider 故障")
            expect(page.get_by_text("模型服务暂不可用，请稍后重试。")).to_be_visible()
            page.close()

            page = browser.new_page()
            page.set_default_timeout(5_000)
            print("E2E: review rejection", flush=True)
            open_page(page)
            submit(page, "模拟审核拒绝")
            expect(page.get_by_test_id("review-rejected-state")).to_contain_text("不会被保存")
            page.close()

            page = browser.new_page()
            page.set_default_timeout(5_000)
            print("E2E: SSE recovery", flush=True)
            open_page(page)
            submit(page, "模拟 SSE 恢复")
            expect(page.get_by_test_id("published-state")).to_contain_text("已审核正式资源")
            expect(page.get_by_test_id("explanation-tab")).to_contain_text("链表节点")
            page.close()
        finally:
            browser.close()
    print("T034 browser E2E passed: success, provider failure, review rejection, SSE recovery")


if __name__ == "__main__":
    run()
