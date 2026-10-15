"""Real Chromium full-app journey against explicit mock HTTP, Provider calls zero."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from playwright.sync_api import sync_playwright, expect
from learning_flow import RESOURCES, mock_api, sse

ROOT = Path(__file__).resolve().parents[3]
BASE = os.getenv("EDUMIND_HYBRID_UI_URL", "http://127.0.0.1:4193")
EVIDENCE = ROOT / "local-materials/phase-1-t053/browser"


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        state = {"status": "awaiting_human", "posts": 0, "reads": 0}
        errors = []
        requests = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def api(route):
            request = route.request
            parsed = urlsplit(request.url)
            path = parsed.path
            requests.append(
                {"method": request.method, "path": path, "query": parsed.query}
            )
            if path == "/api/learning-sessions":
                assert request.method == "POST"
                body = json.loads(request.post_data)
                assert body["generation_protocol"] == "shared-plan-v1"
                state["posts"] += 1
                route.fulfill(
                    status=200,
                    content_type="text/event-stream",
                    body=sse(
                        (
                            "agent_start",
                            {
                                "operation_id": "hybrid-operation-001",
                                "stage": "planning",
                            },
                        ),
                        (
                            "stage_changed",
                            {
                                "operation_id": "hybrid-operation-001",
                                "stage": "consistency_check",
                            },
                        ),
                        (
                            "review_required",
                            {
                                "operation_id": "hybrid-operation-001",
                                "reason_code": "SEMANTIC_REVIEW_REQUIRED",
                            },
                        ),
                        (
                            "done",
                            {
                                "operation_id": "hybrid-operation-001",
                                "status": "awaiting_human",
                            },
                        ),
                    ),
                )
            elif path == "/api/learning-operations/hybrid-operation-001":
                state["reads"] += 1
                route.fulfill(
                    status=200,
                    json={
                        "id": "hybrid-operation-001",
                        "status": state["status"],
                        "learning_unit_id": "unit-reviewed-001",
                        "publication_version": 2
                        if state["status"] == "completed"
                        else None,
                        "review_summary": {
                            "state": "approved"
                            if state["status"] == "completed"
                            else "pending",
                            "approval_source": "human_assisted"
                            if state["status"] == "completed"
                            else None,
                            "reason_code": "SEMANTIC_REVIEW_REQUIRED",
                            "updated_at": "2026-10-15T00:00:00Z",
                        },
                    },
                )
            elif path == "/api/learning-units/unit-reviewed-001":
                assert state["status"] == "completed", (
                    "Read unreviewed body before approval"
                )
                assert parse_qs(parsed.query).get("publication_version") == ["2"]
                route.fulfill(
                    status=200,
                    json={
                        "id": "unit-reviewed-001",
                        "status": "ready",
                        "publication_version": 2,
                        "approval_source": "human_assisted",
                        "knowledge_node_id": "stack",
                        "scenes": [
                            {
                                "id": f"scene-{r['type']}",
                                "scene_key": r["type"],
                                "version": 2,
                                "is_current": True,
                                "resources": [r],
                            }
                            for r in RESOURCES
                        ],
                    },
                )
            elif path == "/api/learning-units/unit-reviewed-001/classroom":
                route.fulfill(
                    status=200,
                    json={
                        "learning_unit_id": "unit-reviewed-001",
                        "revision": 1,
                        "message_cursor": 0,
                        "scene_key": "explanation",
                        "scene_version": 2,
                        "publication_version": 2,
                        "scene_progress": 0,
                        "mode": "focus",
                        "enabled_roles": [],
                        "paused": False,
                    },
                )
            else:
                mock_api(route)

        page.route(BASE + "/api/**", api)
        page.goto(BASE)
        page.wait_for_load_state("networkidle")
        (EVIDENCE / "initial.html").write_text(page.content())
        page.screenshot(path=str(EVIDENCE / "initial.png"), full_page=True)
        assert not errors, errors
        page.get_by_label("学习目标", exact=True).fill("学习栈")
        page.get_by_role("button", name="开始学习 →").click()
        expect(page.get_by_test_id("human-review-state")).to_be_visible()
        assert state["posts"] == 1
        expect(page.get_by_test_id("published-state")).to_have_count(0)
        page.screenshot(path=str(EVIDENCE / "waiting.png"), full_page=True)
        page.reload()
        page.wait_for_load_state("networkidle")
        expect(page.get_by_test_id("human-review-state")).to_be_visible()
        assert state["posts"] == 1, "Reload repeated model generation"
        state["status"] = "completed"
        page.get_by_role("button", name="刷新复核状态").click()
        expect(page.get_by_text("人工复核后发布", exact=True)).to_be_visible()
        expect(
            page.get_by_text("链表节点通过 next 指针连接。", exact=True)
        ).to_be_visible()
        assert state["posts"] == 1
        assert any("publication_version=2" in r["query"] for r in requests)
        page.set_viewport_size({"width": 375, "height": 812})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(EVIDENCE / "approved-mobile.png"), full_page=True)
        assert not errors, errors
        (EVIDENCE / "requests.json").write_text(
            json.dumps(requests, ensure_ascii=False, indent=2)
        )
        browser.close()
    print(
        "Chromium: pending stream ended, reload GET-only, exact approved snapshot and source, mobile layout; Provider 0"
    )


if __name__ == "__main__":
    main()
