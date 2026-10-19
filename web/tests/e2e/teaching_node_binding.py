"""Real Chromium, route-mocked HTTP, zero Provider calls; exact snapshot recovery."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from playwright.sync_api import sync_playwright, expect
from learning_flow import RESOURCES, mock_api, sse

ROOT = Path(__file__).resolve().parents[3]
BASE = os.getenv("EDUMIND_TEACHING_UI_URL", "http://127.0.0.1:4194")
EVIDENCE = ROOT / "local-materials/phase-1-t064/browser"


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        state = {"posts": [], "context": None, "pending": False}
        errors, requests = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def api(route):
            req = route.request
            url = urlsplit(req.url)
            requests.append({"method": req.method, "path": url.path, "query": url.query})
            if url.path == "/api/learning-sessions":
                body = json.loads(req.post_data)
                state["posts"].append(body)
                recommended = body["teaching_mode"] == "recommended"
                state["context"] = {
                    "version": "teaching-node-binding-v1", "teaching_mode": body["teaching_mode"],
                    "target_node_id": "linked-list-insertion", "recommended_node_id": "c-pointer",
                    "teaching_node_id": "c-pointer" if recommended else "linked-list-insertion",
                    "original_request": body["goal"], "segment_goal": "先补指针" if recommended else body["goal"],
                    "selection_reason": "recommended_prerequisite" if recommended else "direct_target",
                    "segment_scope": "prerequisite_segment" if recommended else "target_lesson",
                    "path_version_id": "frozen-path", "path_version": 1, "graph_version": "g1", "graph_digest": "a" * 64,
                }
                end = ("review_required", {"operation_id": "teaching-op-001"}) if state["pending"] else (
                    "scene_ready", {"learning_unit_id": "unit-reviewed-001", "publication_version": 2})
                route.fulfill(status=200, content_type="text/event-stream", body=sse(
                    ("agent_start", {"operation_id": "teaching-op-001", "stage": "planning"}),
                    ("teaching_selected", {"operation_id": "teaching-op-001", "teaching_context": state["context"], "binding_status": "bound"}),
                    end, ("done", {"status": "awaiting_human" if state["pending"] else "completed"})))
            elif url.path == "/api/learning-operations/teaching-op-001":
                route.fulfill(status=200, json={"id": "teaching-op-001", "status": "awaiting_human" if state["pending"] else "completed",
                    "teaching_context": state["context"], "binding_status": "bound", "publication_version": 2,
                    "learning_unit_id": "unit-reviewed-001"})
            elif url.path == "/api/learning-units/unit-reviewed-001":
                assert not state["pending"], "unreviewed body fetched"
                assert parse_qs(url.query).get("publication_version") == ["2"]
                route.fulfill(status=200, json={"id": "unit-reviewed-001", "publication_version": 2,
                    "teaching_context": state["context"], "binding_status": "bound", "approval_source": "auto",
                    "knowledge_node_id": state["context"]["teaching_node_id"], "path_target_node_id": "linked-list-insertion",
                    "scenes": [{"id": f"scene-{r['type']}", "scene_key": r["type"], "version": 2,
                                "is_current": True, "resources": [r]} for r in RESOURCES]})
            else:
                mock_api(route)

        page.route(BASE + "/api/**", api)
        page.goto(BASE)
        page.wait_for_load_state("networkidle")
        page.get_by_label("学习目标", exact=True).fill("学习头插法")
        page.get_by_role("button", name="开始学习 →").click()
        expect(page.get_by_test_id("teaching-node")).to_have_text("链表插入")
        expect(page.get_by_test_id("recommended-node")).to_have_text("C 指针")
        expect(page.get_by_test_id("published-state")).to_be_visible()
        page.screenshot(path=str(EVIDENCE / "target.png"), full_page=True)
        page.reload(); page.wait_for_load_state("networkidle")
        expect(page.get_by_test_id("teaching-node")).to_have_text("链表插入")
        assert len(state["posts"]) == 1
        page.get_by_label("学习目标", exact=True).fill("学习头插法")
        page.get_by_label("本节安排").select_option("recommended")
        page.get_by_role("button", name="开始学习 →").click()
        expect(page.get_by_test_id("teaching-node")).to_have_text("C 指针")
        expect(page.get_by_test_id("target-node")).to_have_text("链表插入")
        expect(page.get_by_text("本节先补前置知识；原目标尚未交付，也不代表已掌握。", exact=True)).to_be_visible()
        page.reload(); page.wait_for_load_state("networkidle")
        expect(page.get_by_test_id("teaching-node")).to_have_text("C 指针")
        assert len(state["posts"]) == 2
        page.set_viewport_size({"width": 375, "height": 812})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(EVIDENCE / "recommended-mobile.png"), full_page=True)
        # Pending journey starts without an existing course so it cannot show unreviewed body.
        page.evaluate("sessionStorage.clear()")
        page.reload(); page.wait_for_load_state("networkidle")
        state["pending"] = True
        page.get_by_label("学习目标", exact=True).fill("学习头插法")
        page.get_by_label("本节安排").select_option("recommended")
        page.get_by_role("button", name="开始学习 →").click()
        expect(page.get_by_test_id("human-review-state")).to_be_visible()
        expect(page.get_by_test_id("published-state")).to_have_count(0)
        page.reload(); page.wait_for_load_state("networkidle")
        expect(page.get_by_test_id("human-review-state")).to_be_visible()
        expect(page.get_by_test_id("teaching-node")).to_have_text("C 指针")
        assert len(state["posts"]) == 3
        page.screenshot(path=str(EVIDENCE / "pending.png"), full_page=True)
        assert not errors, errors
        (EVIDENCE / "result.json").write_text(json.dumps({"provider_calls": 0, "posts": state["posts"], "requests": requests, "page_errors": errors}, ensure_ascii=False, indent=2))
        browser.close()
    print("Chromium passed: direct/prerequisite, exact refresh GET-only, pending unpublished, mobile; Provider 0")

if __name__ == "__main__":
    main()
