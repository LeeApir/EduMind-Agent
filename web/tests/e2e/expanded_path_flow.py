"""Actual Chromium UI checks against explicit mock HTTP; no Provider or database."""

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
BASE = os.getenv("EDUMIND_EXPANDED_UI_URL", "http://127.0.0.1:4189")
EVIDENCE = ROOT / "local-materials/phase-1-t034/browser"


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    expanded = json.loads((ROOT / "data/knowledge/phase-1.1.0.json").read_text())
    legacy = json.loads((ROOT / "data/knowledge_graph.yaml").read_text())
    catalog = {
        "status": "ready",
        "releases": [
            {
                "id": "release",
                "package_id": "TEST_ONLY",
                "version": "1",
                "digest": "TEST_ONLY",
                "nodes": legacy["nodes"],
            }
        ],
    }
    mastery = {
        "graph_version": expanded["graph_version"],
        "items": [
            {
                "knowledge_node_id": "array",
                "previous_score": 0,
                "score": 0.9,
                "status": "mastered",
                "revision": 1,
                "rule_version": "mastery-v1",
                "evidence_summary": ["TEST_ONLY"],
            }
        ],
    }
    history = {
        "version": 1,
        "target_node_id": "array",
        "graph_version": "mvp-0.2.0",
        "profile_version": 1,
        "mastery_revision_watermark": 0,
        "planner_rule_version": "path-v2",
        "nodes": ["array"],
        "node_details": [
            {
                "node_id": "array",
                "score": 0,
                "mastery_known": False,
                "status": "unseen",
                "cost": 0,
                "recommended_resource": "explanation",
                "estimated_minutes": 12,
            }
        ],
        "current_node_id": "array",
        "prerequisite_node_ids": [],
        "next_node_id": None,
        "reasons": [{"kind": "goal", "summary": "TEST_ONLY historical goal"}],
        "changes": {
            "kind": "initial_plan",
            "trigger": "initial_plan",
            "added_node_ids": ["array"],
            "removed_node_ids": [],
            "reordered_node_ids": [],
        },
        "is_stale": True,
        "learning_availability": [
            {
                "node_id": "array",
                "status": "available",
                "reason": "approved_catalog",
                "catalog_release_id": "release",
                "learning_unit_id": None,
            }
        ],
    }
    temp_root = ROOT / "web/tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="expanded-ui-", dir=temp_root) as directory:
        harness = Path(directory) / "index.html"
        harness.write_text("""<!doctype html><html lang="zh"><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><div id="app"></div>
<script type="module">
import {createApp,h} from 'vue';
import KnowledgeExplorer from '/src/components/KnowledgeExplorer.vue';
import LearningPathPanel from '/src/components/LearningPathPanel.vue';
import '/src/styles.css';
createApp({render(){return h('main',[
 h(KnowledgeExplorer,{csrfToken:'TEST_ONLY',canPlan:true,fixedCompletedNodeId:'array'}),
 h(LearningPathPanel,{targetNodeId:'array',csrfToken:'TEST_ONLY'})]);}}).mount('#app');
</script></html>""")
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1100, "height": 900})
            errors = []
            requests = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def api(route):
                request = route.request
                requests.append({"method": request.method, "url": request.url})
                parsed = urlsplit(request.url)
                if parsed.path == "/api/graph":
                    payload = (
                        legacy
                        if parse_qs(parsed.query).get("version") == ["mvp-0.2.0"]
                        else expanded
                    )
                elif parsed.path == "/api/mastery":
                    payload = mastery
                elif parsed.path == "/api/catalog":
                    payload = catalog
                elif parsed.path == "/api/path/current":
                    payload = history
                else:
                    route.fulfill(status=503, json={"code": "UNEXPECTED_TEST_REQUEST"})
                    return
                route.fulfill(status=200, json=payload)

            page.route(f"{BASE}/api/**", api)
            page.goto(f"{BASE}/{harness.relative_to(ROOT / 'web')}")
            page.wait_for_load_state("networkidle")
            explorer = page.get_by_role("region", name="知识结构浏览")
            expect(explorer.locator("[data-knowledge-id]")).to_have_count(30)
            expect(page.get_by_text("正在查看历史路径。", exact=False)).to_be_visible()
            page.screenshot(path=str(EVIDENCE / "desktop.png"), full_page=True)
            bfs = explorer.locator('[data-knowledge-id="breadth-first-search"]')
            bfs.focus()
            page.keyboard.press("Enter")
            expect(bfs).to_have_attribute("aria-pressed", "true")
            detail = explorer.get_by_role("region", name="知识点详情")
            expect(
                detail.get_by_text("该知识点暂未提供已审核课程。", exact=True)
            ).to_be_visible()
            expect(detail.get_by_role("button", name="学习已审核课程")).to_have_count(0)
            detail.get_by_role("button", name="队列", exact=True).focus()
            page.keyboard.press("Enter")
            expect(explorer.locator('[data-knowledge-id="queue"]')).to_have_attribute(
                "aria-pressed", "true"
            )
            page.set_viewport_size({"width": 375, "height": 812})
            expect(explorer.locator('[data-knowledge-id="queue"]')).to_be_visible()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
            page.screenshot(path=str(EVIDENCE / "mobile.png"), full_page=True)
            assert all(request["method"] == "GET" for request in requests), requests
            assert any("version=mvp-0.2.0" in request["url"] for request in requests)
            assert not errors, errors
            (EVIDENCE / "requests.json").write_text(json.dumps(requests, indent=2))
            browser.close()
    print(
        "Thirty nodes, native keyboard navigation, 375px no overflow, historical graph read, no automatic mutation; Provider 0"
    )


if __name__ == "__main__":
    main()
