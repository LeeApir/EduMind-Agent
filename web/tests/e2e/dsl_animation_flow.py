"""Browser UI contract check using mock HTTP/SSE; no Provider or database calls.

Run with a Vite server (e.g. webapp-testing/scripts/with_server.py) on port 4189:
    backend/.venv/bin/python web/tests/e2e/dsl_animation_flow.py
"""

import json
import os
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
BASE = os.getenv("EDUMIND_DSL_UI_URL", "http://127.0.0.1:4189")
SCENE = "123e4567-e89b-42d3-a456-426614174001"
EVIDENCE = ROOT / "local-materials/phase-1-t029/browser"


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    harness_root = ROOT / "web/tmp"
    harness_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dsl-ui-", dir=harness_root) as directory:
        harness = Path(directory) / "index.html"
        harness.write_text(
            f"""<!doctype html><html lang="zh"><meta charset="UTF-8"><div id="app"></div>
<script type="module">
import {{createApp, ref, h}} from 'vue';
import AnimationPanel from '/src/components/AnimationPanel.vue';
import '/src/styles.css';
createApp({{setup(){{const version=ref(1); const dynamic=ref(true); return () => h('main', [
 h('h1','链表课堂'), h('p','讲解与练习可以继续。'),
 h('button',{{id:'change',onClick:()=>version.value++}},'切换版本'),
 h('button',{{id:'catalog',onClick:()=>dynamic.value=false}},'课程目录模式'),
 h(AnimationPanel,{{unitId:'unit',nodeId:'linked-list-insertion',sceneId:'{SCENE}',
 sceneVersion:version.value,dynamicEnabled:dynamic.value,csrfToken:'test-csrf'}})
]);}}}}).mount('#app');
</script></html>""",
            encoding="utf-8",
        )
        url = f"{BASE}/{harness.relative_to(ROOT / 'web')}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1100, "height": 850})
            errors = []
            requests = []
            operation = None
            mode = "fallback"
            job = None
            page.on("pageerror", lambda error: errors.append(str(error)))

            def api(route):
                nonlocal operation, job
                request = route.request
                path = request.url.split(BASE)[-1]
                requests.append({"method": request.method, "path": path})
                if path.endswith("/generate"):
                    operation = request.headers["x-animation-operation-id"]
                    assert (
                        request.headers["x-animation-allow-template-fallback"] == "true"
                    )
                    snapshot = {
                        "id": operation,
                        "stage": "reserved",
                        "deadline": "2030-01-01T00:00:00Z",
                    }
                    if mode == "cancel":
                        data = f"event: agent_start\ndata: {json.dumps(snapshot)}\n\n"
                    else:
                        job = {
                            "id": "dsl-job",
                            "learning_unit_id": "unit",
                            "template_id": None,
                            "render_kind": "dsl",
                            "candidate_id": "candidate",
                            "generation_id": operation,
                            "status": "failed",
                            "attempt": 2,
                            "progress": 0,
                            "last_event_id": 5,
                        }
                        snapshot.update(
                            stage="handed_off", job_id="dsl-job", source="generated_dsl"
                        )
                        data = f"event: agent_start\ndata: {json.dumps(snapshot)}\n\nevent: done\ndata: {json.dumps(snapshot)}\n\n"
                    route.fulfill(content_type="text/event-stream", body=data)
                elif "dsl-job/events" in path:
                    event = {
                        "job_id": "dsl-job",
                        "fallback_job_id": "template-job",
                        "fallback_source": "template_fallback",
                    }
                    route.fulfill(
                        content_type="text/event-stream",
                        body=f"id: 5\nevent: failed\ndata: {json.dumps(event)}\n\n",
                    )
                elif path.endswith("/template-job"):
                    route.fulfill(
                        json={
                            **job,
                            "id": "template-job",
                            "render_kind": "template",
                            "template_id": "linked-list-insertion",
                            "candidate_id": None,
                            "fallback_of": "dsl-job",
                            "fallback_reason_code": "DSL_RENDER_FAILED",
                        }
                    )
                elif path.endswith("/dsl-job"):
                    route.fulfill(json=job)
                elif path.endswith("/cancel"):
                    route.fulfill(
                        json={
                            "id": operation,
                            "stage": "cancelled",
                            "deadline": "2030-01-01T00:00:00Z",
                        }
                    )
                else:
                    route.fulfill(status=404, json={"code": "NOT_FOUND"})

            page.route(f"{BASE}/api/**", api)
            page.goto(url)
            page.wait_for_load_state("networkidle")
            (EVIDENCE / "initial.html").write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(EVIDENCE / "initial.png"), full_page=True)
            assert not errors, errors
            expect(page.get_by_test_id("generate-animation")).to_be_visible()
            page.locator('input[type="checkbox"]').check()
            page.get_by_test_id("generate-animation").click()
            expect(page.get_by_test_id("animation-source")).to_contain_text(
                "生成动画失败，已改用审核模板"
            )
            expect(page.get_by_test_id("animation-source")).to_contain_text(
                "DSL_RENDER_FAILED"
            )
            page.screenshot(path=str(EVIDENCE / "fallback.png"), full_page=True)
            posts = sum(r["method"] == "POST" for r in requests)
            page.reload()
            expect(page.get_by_test_id("animation-source")).to_contain_text(
                "已改用审核模板"
            )
            assert sum(r["method"] == "POST" for r in requests) == posts
            page.locator("#change").click()
            expect(page.get_by_test_id("animation-source")).to_have_count(0)
            page.locator("#catalog").click()
            expect(page.get_by_test_id("generate-animation")).to_have_count(0)
            expect(page.get_by_test_id("request-animation")).to_be_visible()
            page.screenshot(path=str(EVIDENCE / "catalog.png"), full_page=True)
            page.evaluate("sessionStorage.clear()")
            mode = "cancel"
            page.reload()
            page.locator('input[type="checkbox"]').check()
            page.get_by_test_id("generate-animation").click()
            expect(page.get_by_test_id("cancel-preparation")).to_be_visible()
            page.get_by_test_id("cancel-preparation").click()
            expect(page.get_by_test_id("preparation-status")).to_contain_text("已取消")
            expect(page.get_by_test_id("use-template-animation")).to_be_visible()
            assert not errors, errors
            (EVIDENCE / "requests.json").write_text(
                json.dumps(requests, indent=2), encoding="utf-8"
            )
            browser.close()
    print(
        "PASS: browser fallback/source, GET-only refresh, version isolation, catalog template and preparation cancel; Provider=0"
    )


if __name__ == "__main__":
    main()
