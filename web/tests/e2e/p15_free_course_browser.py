"""Real browser + actual loopback API/PG/worker. No browser route mocks."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    trace = []
    errors = []
    scenarios = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width in [1440, 320]:
            context = browser.new_context(
                viewport={"width": width, "height": 1000}, reduced_motion="reduce"
            )
            page = context.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))

            def log(response):
                if urlsplit(response.url).path.startswith("/api/"):
                    trace.append(
                        {
                            "width": width,
                            "method": response.request.method,
                            "path": urlsplit(response.url).path,
                            "status": response.status,
                        }
                    )

                    (args.output / "requests.json").write_text(
                        json.dumps(trace, ensure_ascii=False, indent=2) + "\n"
                    )

            page.on("response", log)
            page.goto("http://127.0.0.1:5192")
            page.wait_for_load_state("networkidle")

            def nav(name):
                if width <= 850:
                    page.get_by_role("button", name="打开导航", exact=True).click()
                page.get_by_role("navigation", name="主导航").get_by_role(
                    "button", name=name, exact=True
                ).click()

            def capture(name):
                assert page.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ), (name, width)
                page.screenshot(
                    path=str(args.output / f"{name}-{width}.png"), full_page=True
                )

            goal = f"学习数组与单链表，解释代码并完成练习（隔离浏览器 {width}）"
            entry = page.get_by_label("这次学习的目标", exact=True)
            entry.fill(goal)
            nav("模型设置")
            page.get_by_role("heading", name="模型设置", exact=True).wait_for()
            capture("settings-return")
            page.get_by_role("button", name="← 返回原页面", exact=True).click()
            expect(entry).to_have_value(goal)
            page.get_by_role("button", name="组织我的课程 →", exact=True).click()
            page.get_by_text("明确 Mock：原始场景 1。", exact=False).wait_for(
                timeout=20000
            )
            # The actual worker is still running, while the first scene is already readable.
            if width <= 620:
                page.get_by_role("button", name="课程目录", exact=True).click()
            page.get_by_text("后续场景仍在生成", exact=False).wait_for()
            capture("first-scene")
            if width <= 620:
                page.get_by_role("button", name="课程目录", exact=True).click()
            page.get_by_text("阅读版本 v3", exact=True).wait_for(timeout=25000)
            page.wait_for_load_state("networkidle")
            capture("complete-course")
            creation = [
                r
                for r in trace
                if r["width"] == width
                and r["method"] == "POST"
                and r["path"] == "/api/free-courses"
            ]
            assert len(creation) == 1 and creation[0]["status"] == 201
            # Actual public exercise answers; no answer_key is ever read by browser.
            page.locator(".exercise-question textarea").nth(0).fill("0")
            page.locator(".exercise-question textarea").nth(1).fill("1")
            page.get_by_role("button", name="提交本次作答", exact=True).click()
            page.get_by_text("暂定比较 · 答案尚未可靠核定", exact=True).wait_for()
            capture("attempt")
            before = len([r for r in trace if r["method"] != "GET"])
            page.reload()
            page.wait_for_load_state("networkidle")
            page.get_by_text("暂定比较 · 答案尚未可靠核定", exact=True).wait_for()
            assert len([r for r in trace if r["method"] != "GET"]) == before
            page.get_by_role("button", name="有疑问？打开导师区域", exact=True).click()
            page.get_by_label("记下问题", exact=True).fill("为何先连接旧链表？")
            page.locator(".assistance-consent input").check()
            page.get_by_role("button", name="发送本次提问", exact=True).click()
            page.get_by_text("先连接旧链表，再更新头指针", exact=False).wait_for(
                timeout=15000
            )
            capture("tutor")
            page.get_by_label("反馈位置", exact=True).select_option(label="1. 讲解 · t")
            page.get_by_label("问题描述", exact=True).fill("请核对当前段落的说明")
            page.get_by_role("button", name="提交问题反馈", exact=True).click()
            page.get_by_text("已提交 · 待核对", exact=True).wait_for()
            capture("feedback")
            page.get_by_role("button", name="准备局部修订", exact=True).click()
            page.get_by_label("希望怎样修改这个场景？", exact=True).fill(
                "补充数组按下标访问的例子"
            )
            page.get_by_label(
                "确认受影响场景、证据撤销与新操作预算", exact=True
            ).check()
            page.get_by_role("button", name="确认开始局部修订", exact=True).click()
            page.get_by_role("button", name="确认读取最新版本 v4", exact=True).wait_for(
                timeout=25000
            )
            page.get_by_role("button", name="确认读取最新版本 v4", exact=True).click()
            page.get_by_text("明确 Mock：修订后的场景 1。", exact=False).wait_for()
            capture("atomic-revision")
            nav("学习记录")
            page.get_by_role("heading", name="学习记录", exact=True).wait_for()
            page.get_by_role("button", name=goal, exact=True).click()
            page.get_by_role("button", name="读取练习作答", exact=False).first.click()
            page.get_by_text("原始作答 · 课程 v3", exact=True).wait_for()
            capture("history")
            page.get_by_role("button", name="恢复准确阅读位置", exact=True).click()
            page.get_by_text("明确 Mock：修订后的场景 1。", exact=False).wait_for()
            page.reload()
            page.wait_for_load_state("networkidle")
            page.get_by_text("明确 Mock：修订后的场景 1。", exact=False).wait_for()
            capture("restored")
            for name in ["图谱与路径", "画像与掌握度", "签核课程目录"]:
                nav(name)
                page.wait_for_load_state("networkidle")
                capture(
                    {
                        "图谱与路径": "graph",
                        "画像与掌握度": "profile",
                        "签核课程目录": "catalog",
                    }[name]
                )
            nav("学习")
            page.get_by_label("这次学习的目标", exact=True).fill(
                "学习数组与单链表，验证后续局部失败仍可阅读"
            )
            page.get_by_role("button", name="组织我的课程 →", exact=True).click()
            page.get_by_text("明确 Mock：原始场景 1。", exact=False).wait_for(
                timeout=20000
            )
            if width <= 620:
                page.get_by_role("button", name="课程目录", exact=True).click()
            page.get_by_text("生成尚未完整", exact=False).wait_for(timeout=25000)
            expect(
                page.get_by_text("明确 Mock：原始场景 1。", exact=False)
            ).to_be_visible()
            capture("partial-failure")
            page.reload()
            page.wait_for_load_state("networkidle")
            page.get_by_text("明确 Mock：原始场景 1。", exact=False).wait_for()
            if width <= 620:
                page.get_by_role("button", name="课程目录", exact=True).click()
            page.get_by_text("生成尚未完整", exact=False).wait_for()
            capture("partial-restored")
            assert (
                len(
                    [
                        r
                        for r in trace
                        if r["width"] == width
                        and r["method"] == "POST"
                        and r["path"] == "/api/free-courses"
                    ]
                )
                == 2
            )
            scenarios.append(
                {
                    "width": width,
                    "created": 2,
                    "feedback": 1,
                    "revision": 1,
                    "tutor": 1,
                    "refresh_duplicate_writes": 0,
                    "partial_failure_readable": True,
                }
            )
            context.close()
        browser.close()
    assert not errors, errors
    assert all(
        200 <= r["status"] < 300
        or (
            r["method"] == "GET"
            and (
                (r["status"] == 401 and r["path"] == "/api/auth/session")
                or (r["status"] == 404 and r["path"] == "/api/profile/me")
            )
        )
        for r in trace
    ), [r for r in trace if r["status"] >= 400]
    (args.output / "requests.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n"
    )
    (args.output / "browser-results.json").write_text(
        json.dumps(
            {
                "scenarios": scenarios,
                "page_errors": errors,
                "api_route_mocks": 0,
                "backend": "actual loopback API/PostgreSQL/persistent scheduler",
                "model": "explicit deterministic MockTransport/FakeTutor",
                "real_provider_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        "PASS actual API/PG/persistent worker, desktop/mobile first scene and full course, answers/refresh/tutor/feedback/atomic revision/history, all pages, partial failure still readable, 0 real Provider"
    )


if __name__ == "__main__":
    main()
