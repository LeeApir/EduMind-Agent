"""Browser E2E scenarios with deterministic, route-mocked API responses."""

import json
import os
from urllib.parse import urlparse

from playwright.sync_api import Page, Route, expect, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

BASE_URL = os.getenv("EDUMIND_E2E_BASE_URL", "http://127.0.0.1:4173")
LAST_QUIZ_RECEIPT: dict[str, object] | None = None
QUIZ_POST_COUNT = 0
PATH_REPLANNED = False
LEARNING_KEYS: list[str] = []
ANSWER_KEYS = {"q1": "A", "q2": "head", "q3": "->"}
OBJECTIVE_QUESTION = (
    "[单选题] 插入前先保存什么？\nA. 后继连接\nB. 空指针\nC. 类型名\nD. 节点数量\n仅填 A、B、C 或 D"
)

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
                    "question": OBJECTIVE_QUESTION,
                },
                {
                    "id": "q2",
                    "question": "头节点变量？",
                },
                {
                    "id": "q3",
                    "question": "指针运算符？",
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
    global LAST_QUIZ_RECEIPT, QUIZ_POST_COUNT, PATH_REPLANNED
    request = route.request
    path = urlparse(request.url).path
    if path == "/api/auth/session":
        route.fulfill(status=401, json={"code": "UNAUTHORIZED"})
        return
    if path == "/api/auth/guest":
        route.fulfill(status=201, json={"csrf_token": "c" * 64, "user": {"id": "user-1"}})
        return
    if path == "/api/learning-units/unit-reviewed-001/classroom":
        route.fulfill(status=200, json={
            "learning_unit_id": "unit-reviewed-001", "revision": 1,
            "message_cursor": 0, "scene_key": "intro", "scene_version": 1,
            "scene_progress": 0, "mode": "focus", "enabled_roles": [], "paused": False,
        })
        return
    if path == "/api/learning-units/unit-reviewed-001/classroom/controls":
        payload = json.loads(request.post_data or "{}")
        assert payload["action"] == "select_resource"
        assert payload["resource_type"] in {"explanation", "code", "exercise"}
        assert request.headers.get("if-match-classroom-revision") == "1"
        assert request.headers.get("idempotency-key")
        route.fulfill(status=200, json={
            "learning_unit_id": "unit-reviewed-001", "revision": 2,
            "message_cursor": 0, "scene_key": "intro", "scene_version": 1,
            "scene_progress": 0, "mode": "focus", "enabled_roles": [], "paused": False,
        })
        return
    if path == "/api/learning-units/unit-reviewed-001/classroom/messages":
        route.fulfill(status=200, json={"messages": [], "last_message_cursor": 0})
        return
    if path.startswith("/api/learning-units/"):
        route.fulfill(
            status=200,
            json={
                "id": "unit-reviewed-001",
                "status": "ready",
                "path_target_node_id": "linked-list-concept",
                "scenes": [{
                    "id": "scene-1", "scene_key": "intro", "version": 1,
                    "is_current": True, "resources": RESOURCES,
                }],
            },
        )
        return
    if path == "/api/graph":
        route.fulfill(
            status=200,
            json={
                "graph_version": "g1",
                "nodes": [
                    {"id": "array", "name": "数组", "prerequisites": []},
                    {"id": "c-pointer", "name": "C 指针", "prerequisites": []},
                    {
                        "id": "linked-list-concept",
                        "name": "链表概念",
                        "prerequisites": ["array", "c-pointer"],
                    },
                ],
            },
        )
        return
    if path == "/api/mastery":
        items = [
            {
                "knowledge_node_id": "array",
                "previous_score": 0.8,
                "score": 0.9,
                "status": "mastered",
                "revision": 3,
                "rule_version": "mastery-v1",
                "evidence_summary": ["数组测验通过"],
            }
        ]
        if LAST_QUIZ_RECEIPT:
            items.append(
                {
                    "knowledge_node_id": "c-pointer",
                    "previous_score": 0,
                    "score": 0.55,
                    "status": "learning",
                    "revision": 1,
                    "rule_version": "mastery-v1",
                    "evidence_summary": ["指针测验记录"],
                }
            )
        route.fulfill(status=200, json={"graph_version": "g1", "items": items})
        return
    if path in {"/api/path/current", "/api/path/replan"}:
        if path == "/api/path/replan":
            assert request.headers.get("if-match-path-version") == "1"
            assert request.headers.get("idempotency-key") and request.headers.get("x-csrf-token")
            PATH_REPLANNED = True
        recorded = bool(LAST_QUIZ_RECEIPT)
        route.fulfill(
            status=200,
            json={
                "version": 2 if PATH_REPLANNED else 1,
                "target_node_id": "linked-list-concept",
                "graph_version": "g1",
                "profile_version": 1,
                "mastery_revision_watermark": 4 if recorded else 3,
                "planner_rule_version": "path-v2",
                "nodes": ["c-pointer", "linked-list-concept"],
                "node_details": [
                    {
                        "node_id": "c-pointer",
                        "score": 0.55 if recorded else 0,
                        "status": "learning" if recorded else "unseen",
                        "cost": 0.2,
                        "recommended_resource": "exercise" if recorded else "explanation",
                        "estimated_minutes": 12,
                    },
                    {
                        "node_id": "linked-list-concept",
                        "score": 0,
                        "status": "unseen",
                        "cost": 0,
                        "recommended_resource": "explanation",
                        "estimated_minutes": 16,
                    },
                ],
                "current_node_id": "c-pointer",
                "prerequisite_node_ids": [],
                "next_node_id": "linked-list-concept",
                "reasons": [
                    {
                        "kind": "prerequisite",
                        "knowledge_node_id": "c-pointer",
                        "summary": "C 指针是链表概念的前置知识。",
                    }
                ],
                "changes": {
                    "kind": "path_change" if PATH_REPLANNED else "initial_plan",
                    "trigger": "mastery_changed" if PATH_REPLANNED else "initial_plan",
                    "added_node_ids": [],
                    "removed_node_ids": [],
                    "reordered_node_ids": [],
                },
                "is_stale": recorded and not PATH_REPLANNED,
            },
        )
        return
    if path.startswith("/api/learning-operations/"):
        operation_id = path.rsplit("/", 1)[-1]
        if operation_id == "op-recover":
            route.fulfill(
                status=200,
                json={"id": operation_id, "status": "published", "learning_unit_id": "unit-reviewed-001"},
            )
        else:
            route.fulfill(status=200, json={"id": operation_id, "status": "failed", "learning_unit_id": None})
        return
    if path == "/api/quiz-submissions/latest":
        if LAST_QUIZ_RECEIPT is None:
            route.fulfill(status=404, json={"code": "NOT_FOUND"})
        else:
            route.fulfill(status=200, json=LAST_QUIZ_RECEIPT)
        return
    if path == "/api/quiz-submissions":
        payload = json.loads(request.post_data or "{}")
        assert set(payload) == {"resource_id", "resource_version", "answers"}
        assert request.headers.get("idempotency-key") and request.headers.get("x-csrf-token")
        QUIZ_POST_COUNT += 1
        answers = {item["question_id"]: item["answer"] for item in payload["answers"]}
        question_results = [
            {
                "question_id": key,
                "correct": answers.get(key) == answer,
                "explanation": "服务端反馈：检查后继连接。",
                "error_patterns": [],
            }
            for key, answer in ANSWER_KEYS.items()
        ]
        correct_count = sum(item["correct"] for item in question_results)
        LAST_QUIZ_RECEIPT = {
            "evidence_id": "evidence-reviewed-001",
            "resource_id": payload["resource_id"],
            "resource_version": payload["resource_version"],
            "question_results": question_results,
            "score": correct_count / 3,
            "correct_count": correct_count,
            "question_count": 3,
            "quiz_schema_version": 1,
            "scoring_rule_version": "quiz-exact-text-v1",
            "mastery_changes": [
                {
                    "knowledge_node_id": "c-pointer",
                    "previous_score": 0,
                    "score": 0.55,
                    "status": "learning",
                    "revision": 1,
                    "rule_version": "mastery-v1",
                }
            ],
            "path_replan_required": True,
            "profile_update_status": "no_change",
        }
        route.fulfill(status=200, json=LAST_QUIZ_RECEIPT)
        return
    if path != "/api/learning-sessions":
        route.fulfill(status=404, json={"code": "NOT_FOUND"})
        return

    goal = json.loads(request.post_data or "{}").get("goal", "")
    LEARNING_KEYS.append(request.headers["idempotency-key"])
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
                    "learning_unit_id": "unit-reviewed-001",
                    "scene_id": "scene-1",
                    "version": 1,
                    "resource_ids": [resource["id"] for resource in RESOURCES],
                },
            ),
            ("done", {"operation_id": "op-success", "status": "published"}),
        )
    route.fulfill(status=200, content_type="text/event-stream", body=body)


def open_page(page: Page) -> None:
    global LAST_QUIZ_RECEIPT, QUIZ_POST_COUNT, PATH_REPLANNED
    LAST_QUIZ_RECEIPT = None
    QUIZ_POST_COUNT = 0
    PATH_REPLANNED = False
    LEARNING_KEYS.clear()
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
            learning_path = page.get_by_role("region", name="学习路径", exact=True)
            expect(learning_path).to_contain_text("当前：C 指针 · 下一步：链表概念")
            expect(learning_path.locator('[data-node-id="array"]')).to_contain_text("已掌握 · 90%")
            objective_label = page.get_by_label(OBJECTIVE_QUESTION, exact=True)
            objective_label.fill("A")
            assert page.locator('label[for="answer-q1"]').evaluate(
                "element => getComputedStyle(element).whiteSpace"
            ) == "pre-wrap"
            page.get_by_label("头节点变量？").fill("head")
            page.get_by_label("指针运算符？").fill("->")
            page.get_by_role("button", name="提交练习", exact=True).click()
            expect(page.get_by_role("region", name="最近一次练习提交回执")).to_contain_text(
                "0% → 55%"
            )
            assert QUIZ_POST_COUNT == 1
            expect(learning_path).to_contain_text("路径 v2")
            expect(learning_path.locator('[data-node-id="c-pointer"]')).to_contain_text(
                "学习中 · 55%"
            )
            expect(learning_path.locator('[data-node-id="array"]')).to_have_attribute(
                "data-changed", "false"
            )
            learning_path.locator('[data-node-id="array"] button').focus()
            page.keyboard.press("Enter")
            expect(learning_path.get_by_role("region", name="节点推荐依据")).to_contain_text(
                "数组测验通过"
            )
            learning_path.screenshot(
                path="/tmp/edumind-mvp02-t021-desktop.png", animations="disabled"
            )
            page.locator(".published-workspace").screenshot(
                path="/tmp/edumind-mvp02-t020-desktop.png", animations="disabled"
            )
            page.reload(wait_until="networkidle")
            page.get_by_role("button", name="练习", exact=True).click()
            expect(page.get_by_role("region", name="最近一次练习提交回执")).to_contain_text(
                "服务端已记录"
            )
            assert QUIZ_POST_COUNT == 1
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator(".published-workspace").screenshot(
                path="/tmp/edumind-mvp02-t020-mobile.png", animations="disabled"
            )
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            learning_path.screenshot(
                path="/tmp/edumind-mvp02-t021-mobile.png", animations="disabled"
            )
            page.close()

            page = browser.new_page()
            page.set_default_timeout(5_000)
            print("E2E: provider failure", flush=True)
            open_page(page)
            submit(page, "模拟 Provider 故障")
            expect(page.get_by_text("原请求已失败或取消。", exact=False)).to_be_visible()
            page.get_by_role("button", name="重试恢复原请求", exact=True).click()
            expect(page.get_by_text("原请求已失败或取消。", exact=False)).to_be_visible()
            assert len(LEARNING_KEYS) == 1
            page.get_by_test_id("regenerate-learning").click()
            expect(page.get_by_text("原请求已失败或取消。", exact=False)).to_be_visible()
            assert len(LEARNING_KEYS) == 2 and LEARNING_KEYS[0] != LEARNING_KEYS[1]
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
            assert len(LEARNING_KEYS) == 1
            page.close()

            page = browser.new_page()
            page.set_default_timeout(5_000)
            print("E2E: learning controls and scene versions", flush=True)
            open_page(page)
            scene_state = {"version": 1, "revision": 1}

            def scene_api(route: Route) -> None:
                request = route.request
                path = urlparse(request.url).path
                unit = "/api/learning-units/unit-reviewed-001"
                if path == unit:
                    newer = [{
                        "id": "scene-2", "scene_key": "intro", "version": 2,
                        "is_current": True,
                        "resources": [
                            {**resource,
                             "id": f"{resource['id']}-v2",
                             "version": 2,
                             "content": {"markdown": "新版：先保存后继再修改指针。"}
                             if resource["type"] == "explanation" else resource["content"]}
                            for resource in RESOURCES
                        ],
                    }] if scene_state["version"] == 2 else []
                    older = [{
                        "id": "scene-1", "scene_key": "intro", "version": 1,
                        "is_current": scene_state["version"] == 1,
                        "resources": RESOURCES,
                    }]
                    route.fulfill(status=200, json={"id": "unit-reviewed-001", "status": "ready",
                                                    "scenes": newer + older})
                    return
                if path == f"{unit}/classroom":
                    route.fulfill(status=200, json={
                        "learning_unit_id": "unit-reviewed-001", "revision": scene_state["revision"],
                        "message_cursor": 0, "scene_key": "intro",
                        "scene_version": scene_state["version"], "scene_progress": 0,
                        "mode": "focus", "enabled_roles": [], "paused": False,
                    })
                    return
                if path.endswith("/reexplanations"):
                    payload = json.loads(request.post_data or "{}")
                    assert request.headers.get("if-match-classroom-revision") == str(scene_state["revision"])
                    assert request.headers.get("idempotency-key")
                    if payload["action"] == "simpler":
                        scene_state["version"] = 2
                        scene_state["revision"] = 2
                        body = sse(
                            ("agent_start", {"operation_id": "op-reexplain-ok"}),
                            ("token", {"temporary": True, "delta": "候选新版"}),
                            ("review_pass", {"kind": "reexplanation"}),
                            ("scene_ready", {"scene_key": "intro", "scene_version": 2}),
                            ("done", {"status": "published"}),
                        )
                    else:
                        body = sse(
                            ("agent_start", {"operation_id": "op-reexplain-failed"}),
                            ("token", {"temporary": True, "delta": "未审核候选"}),
                            ("content_retracted", {"code": "REVIEW_REJECTED"}),
                            ("error", {"code": "REVIEW_REJECTED", "message": "审核未通过", "retryable": False}),
                            ("done", {"status": "failed"}),
                        )
                    route.fulfill(status=200, content_type="text/event-stream", body=body)
                    return
                if path == "/api/classroom-operations/op-reexplain-failed":
                    route.fulfill(status=200, json={"id": "op-reexplain-failed", "status": "failed",
                                                    "kind": "reexplanation", "learning_unit_id": "unit-reviewed-001",
                                                    "base_revision": 2})
                    return
                route.fallback()

            page.route(f"{BASE_URL}/api/**", scene_api)
            submit(page, "我想理解链表插入")
            expect(page.get_by_test_id("explanation-tab")).to_contain_text("链表节点")
            controls = page.get_by_test_id("learning-controls")
            controls.get_by_role("button", name="更简单").click()
            expect(page.get_by_test_id("explanation-tab")).to_contain_text("新版：先保存后继")
            controls.get_by_role("button", name="intro · 版本 1 · 旧版只读").click()
            expect(page.get_by_test_id("explanation-tab")).to_contain_text("链表节点")
            page.reload(wait_until="domcontentloaded")
            expect(page.get_by_test_id("explanation-tab")).to_contain_text("链表节点")
            controls.get_by_role("button", name="intro · 版本 2 · 当前").click()
            controls.get_by_role("button", name="更深入").click()
            expect(controls).to_contain_text("上次重解释未发布，原正式版本仍可学习")
            expect(page.get_by_test_id("explanation-tab")).to_contain_text("新版：先保存后继")
            expect(controls.get_by_label("临时讲解")).to_have_count(0)
            controls.screenshot(path="/tmp/edumind-mvp03-t022-controls.png", animations="disabled")
            page.close()
        finally:
            browser.close()
    print(
        "Browser route-mock E2E passed: quiz submit/reload, mobile, "
        "provider failure, review rejection, SSE recovery, controls and scene versions"
    )


if __name__ == "__main__":
    run()
