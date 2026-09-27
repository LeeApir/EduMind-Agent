"""Real Chromium -> Vite proxy -> Uvicorn; no routes or synthetic resources."""

import argparse
import json
import platform
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError as BrowserTimeout
from playwright.sync_api import expect, sync_playwright

FAULT_SCRIPT = """
(() => {
  const realFetch = window.fetch.bind(window);
  window.__lost = false;
  window.fetch = async (...args) => {
    const response = await realFetch(...args);
    if (String(args[0]) !== '/api/learning-sessions' || !response.body) return response;
    const decoder = new TextDecoder();
    let buffered = '';
    const stream = response.body.pipeThrough(new TransformStream({
      async transform(chunk, controller) {
        buffered += decoder.decode(chunk, {stream: true});
        if (buffered.includes('event: scene_ready')) {
          window.__lost = true;
          await new Promise(resolve => { window.__releaseLost = resolve; });
          throw new TypeError('Acceptance: published response deliberately dropped');
        }
        controller.enqueue(chunk);
      }
    }));
    return new Response(stream, {status: response.status, headers: response.headers});
  };
})();
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:4181")
    args = parser.parse_args()
    if not args.confirm_billable:
        parser.error("Requires --confirm-billable")
    with args.output.open("x") as handle:
        handle.write("{}\n")
    report = {
        "started_at": datetime.now().isoformat(),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "concurrency": 1,
            "transport": "Chromium/Vite proxy/Uvicorn/PostgreSQL/real Provider",
        },
        "passed": False,
        "checks": {},
        "http_responses": [],
        "request_failures": [],
        "console": [],
        "page_errors": [],
    }
    step = "start"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                report["environment"]["browser"] = browser.version
                context.add_init_script(FAULT_SCRIPT)
                page = context.new_page()
                page.set_default_timeout(180_000)
                posts = []

                def request_seen(request):
                    if urlsplit(request.url).path == "/api/learning-sessions":
                        posts.append(
                            {
                                "csrf_present": bool(request.headers.get("x-csrf-token")),
                                "key": request.headers.get("idempotency-key"),
                            }
                        )

                page.on("request", request_seen)
                page.on(
                    "response",
                    lambda response: report["http_responses"].append(
                        {
                            "path": urlsplit(response.url).path,
                            "status": response.status,
                            "method": response.request.method,
                        }
                    )
                    if urlsplit(response.url).path.startswith("/api/")
                    else None,
                )
                page.on(
                    "requestfailed",
                    lambda request: report["request_failures"].append(
                        {"path": urlsplit(request.url).path, "error": request.failure}
                    ),
                )
                # Do not retain raw console output (it may include sensitive URLs).
                page.on("console", lambda message: report["console"].append({"type": message.type}))
                page.on(
                    "pageerror", lambda error: report["page_errors"].append(type(error).__name__)
                )
                step = "anonymous"
                print("browser step: anonymous", flush=True)
                page.goto(args.base_url, wait_until="domcontentloaded", timeout=20_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=3_000)
                    report["initial_network_idle"] = True
                except BrowserTimeout:
                    report["initial_network_idle"] = False
                expect(page.get_by_label("学习目标")).to_be_visible()
                page.get_by_label("学习目标").fill("我想理解单链表的前置知识，先看 C 代码。")
                started = time.monotonic()
                page.get_by_role("button", name="开始学习").click()
                step = "temporary"
                print("browser step: temporary", flush=True)
                expect(page.get_by_test_id("temporary-explanation")).to_contain_text("尚未审核")
                report["checks"]["temporary_first_screen"] = True
                expect(page.get_by_test_id("reviewing-state")).to_be_visible()
                report["checks"]["reviewing_display"] = True
                step = "publication_fault"
                print("browser step: publication_fault", flush=True)
                page.wait_for_function("window.__lost === true")
                report["publication_total_ms"] = round((time.monotonic() - started) * 1000)
                report["calls_before_recovery"] = len(
                    json.loads(args.ledger.read_text())["provider_calls"]
                )
                # Real network unavailable for the status query; not a mocked HTTP response.
                context.set_offline(True)
                page.evaluate("window.__releaseLost()")
                expect(page.locator(".error-state")).to_be_visible()
                report["checks"]["offline_recovery_failed_safely"] = True
                context.set_offline(False)
                page.get_by_role("button", name="重试恢复原请求", exact=True).click()
                expect(page.get_by_test_id("published-state")).to_be_visible()
                expect(page.get_by_test_id("explanation-tab")).to_contain_text("指针")
                unit_id = page.evaluate("sessionStorage.getItem('edumind:last-learning-unit')")
                report["learning_unit_id"] = unit_id
                report["calls_after_recovery"] = len(
                    json.loads(args.ledger.read_text())["provider_calls"]
                )
                assert report["calls_before_recovery"] == report["calls_after_recovery"]
                assert len(posts) == 1 and posts[0]["csrf_present"] and posts[0]["key"]
                report["checks"]["published_recovered_without_regeneration"] = True
                cookies = context.cookies()
                report["checks"]["anonymous_cookie"] = any(
                    c["name"] == "edumind_session" and c["httpOnly"] and c["secure"]
                    for c in cookies
                )
                assert report["checks"]["anonymous_cookie"]
                step = "resources"
                print("browser step: resources", flush=True)
                page.get_by_role("button", name="代码", exact=True).click()
                expect(page.get_by_test_id("code-tab").locator("code")).not_to_be_empty()
                page.get_by_role("button", name="练习", exact=True).click()
                page.wait_for_function(
                    "document.querySelectorAll('.quiz-question label').length > 0"
                )
                questions = page.locator(".quiz-question label").all_text_contents()
                report["public_questions"] = questions
                report["checks"]["three_resource_tabs"] = True
                print(json.dumps({"public_questions": questions}, ensure_ascii=False), flush=True)
                print("Enter independently solved answers as a JSON string array:", flush=True)
                answers = json.loads(sys.stdin.readline())
                assert len(answers) == len(questions) and all(isinstance(a, str) for a in answers)
                step = "quiz"
                print("browser step: quiz", flush=True)
                for attempt in range(2):
                    if attempt:
                        page.get_by_role("button", name="再做一次", exact=True).click()
                    inputs = page.locator(".quiz-question input")
                    for index, answer in enumerate(answers):
                        inputs.nth(index).fill(answer)
                    page.get_by_role("button", name="提交练习", exact=True).click()
                    receipt = page.get_by_role("region", name="最近一次练习提交回执")
                    expect(receipt).to_be_visible()
                    expect(receipt).to_contain_text(f"{len(questions)} / {len(questions)} 题正确")
                    expect(receipt).to_contain_text("0% → 55%" if attempt == 0 else "55% → 95%")
                    report.setdefault("quiz_receipts", []).append(receipt.inner_text())
                    expect(page.get_by_role("region", name="学习路径", exact=True)).to_contain_text(
                        f"路径 v{attempt + 2}"
                    )
                path = page.get_by_role("region", name="学习路径", exact=True)
                expect(path).to_contain_text("链表概念")
                expect(path).to_contain_text("路径 v3")
                report["checks"]["quiz_mastery_recommendation"] = True
                report["path_before_reload"] = path.inner_text()
                report["path_snapshot_before_reload"] = page.evaluate(
                    "async () => (await fetch('/api/path/current?"
                    "target_node_id=single-linked-list')).json()"
                )
                report["receipt_before_reload"] = receipt.inner_text()
                step = "reload"
                print("browser step: reload", flush=True)
                page.reload(wait_until="domcontentloaded", timeout=20_000)
                expect(page.get_by_test_id("published-state")).to_be_visible()
                page.get_by_role("button", name="练习", exact=True).click()
                receipt = page.get_by_role("region", name="最近一次练习提交回执")
                expect(receipt).to_contain_text("55% → 95%")
                path = page.get_by_role("region", name="学习路径", exact=True)
                expect(path).to_contain_text("路径 v3")
                expect(path.locator(".path-direction")).to_contain_text(
                    "当前：链表概念 · 下一步：单链表"
                )
                expect(path.locator('[data-node-id="c-pointer"]')).to_contain_text("已掌握 · 95%")
                report["path_after_reload"] = path.inner_text()
                report["path_snapshot_after_reload"] = page.evaluate(
                    "async () => (await fetch('/api/path/current?"
                    "target_node_id=single-linked-list')).json()"
                )
                assert (
                    report["path_snapshot_after_reload"] == report["path_snapshot_before_reload"]
                )
                assert (
                    page.evaluate("sessionStorage.getItem('edumind:last-learning-unit')") == unit_id
                )
                assert len(posts) == 1
                report["checks"]["reload_resource_receipt_path"] = True
                report["learning_post_count"] = len(posts)
                report["provider"] = json.loads(args.ledger.read_text())
                # Known negative reads: initial anonymous session/profile and no prior quiz.
                expected_negative = {
                    ("/api/auth/session", 401),
                    ("/api/profile/me", 401),
                    ("/api/profile/me", 404),
                    ("/api/quiz-submissions/latest", 404),
                }
                unexpected = [
                    r
                    for r in report["http_responses"]
                    if r["status"] >= 400 and (r["path"], r["status"]) not in expected_negative
                ]
                report["unexpected_http_failures"] = unexpected
                assert not unexpected and not report["page_errors"]
                assert all(
                    r["path"] == "/api/learning-sessions"
                    and r["error"] == "net::ERR_ABORTED"
                    or "learning-operations" in r["path"]
                    and r["error"] == "net::ERR_INTERNET_DISCONNECTED"
                    for r in report["request_failures"]
                )
                report["checks"]["network_console_classified"] = True
                report["passed"] = True
            finally:
                browser.close()
    except Exception as error:
        report["failure"] = {
            "step": step,
            "class": type(error).__name__,
            "line": traceback.extract_tb(error.__traceback__)[0].lineno,
        }
        print(json.dumps(report["failure"]), flush=True)
    finally:
        report["finished_at"] = datetime.now().isoformat()
        report["provider"] = json.loads(args.ledger.read_text()) if args.ledger.exists() else None
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "checks": report["checks"]}), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
