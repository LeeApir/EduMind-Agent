"""Actual goal input → explicit offline fixtures → existing learning and refresh; zero Provider."""

import json
import os
from pathlib import Path
import subprocess
import sys

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from app.services.head_course_materials import GOAL  # noqa: E402

OUT = Path("/tmp/edumind-t108/browser")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    scenarios = []
    requests = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for key, width in [("head-new-A", 1440), ("head-new-B", 390)]:
            ctx = browser.new_context(viewport={"width": width, "height": 1000})
            page = ctx.new_page()
            page.on("pageerror", lambda err: errors.append(str(err)))
            page.on(
                "response",
                lambda r: requests.append(
                    dict(url=r.url, method=r.request.method, status=r.status)
                ),
            )
            page.goto("http://127.0.0.1:5198")
            page.wait_for_load_state("networkidle")
            page.get_by_label("这次学习的目标", exact=True).fill(GOAL)
            with page.expect_response(
                lambda r: r.url.endswith("/api/free-courses")
                and r.request.method == "POST"
            ) as response:
                page.get_by_role("button", name="组织我的课程 →", exact=True).click()
            assert response.value.status == 201
            created = response.value.json()
            auth = page.evaluate(
                "async()=>await (await fetch('/api/auth/session')).json()"
            )
            owner = auth["user"]["id"]
            command = [
                sys.executable,
                str(ROOT / "scripts/head_course_goal_fixture.py"),
                "--offline-fixture",
                "--owner",
                owner,
                "--course",
                created["course_id"],
                "--operation",
                created["operation_id"],
                "--example",
                key,
            ]
            completed = subprocess.run(
                command, env=os.environ, check=True, capture_output=True, text=True
            )
            binding = json.loads(completed.stdout)
            page.get_by_role("button", name="重新读取进度", exact=True).click()
            # Existing outline automatically enters the first ready scene.
            page.get_by_label("新课程来源", exact=True).wait_for()
            page.wait_for_load_state("networkidle")
            expect(page.get_by_role("heading", name=GOAL, exact=True)).to_be_visible()
            expect(page.get_by_label("新课程来源", exact=True)).to_contain_text(
                "离线接线夹具 · 非真实生成"
            )
            expect(page.get_by_label("新课程来源", exact=True)).to_contain_text(
                "本页教学文字为离线接线夹具，未调用模型"
            )
            scene = page.evaluate(
                "async ({cid,sid})=>await (await fetch(`/api/free-courses/${cid}/versions/2/scenes/${sid}`)).json()",
                dict(cid=binding["course_id"], sid=binding["scene_id"]),
            )
            assert "replay_source" not in scene and "answer_key" not in json.dumps(
                scene
            )
            visual = next(b for b in scene["blocks"] if b["kind"] == "visualization")
            panel = page.get_by_role("region", name="过程演示与代码对照", exact=True)
            for i, step in enumerate(visual["steps"]):
                frame = step["head_frame"]
                expect(panel.locator(".head-replay-frame")).to_have_attribute(
                    "data-frame", frame["frame_id"]
                )
                expect(panel.locator(".head-step-note")).to_have_text(frame["note"])
                active = panel.locator(".active-code-line")
                if frame["line"] is None:
                    expect(active).to_have_count(0)
                else:
                    expect(active).to_have_attribute("data-line", str(frame["line"]))
                if i < len(visual["steps"]) - 1:
                    panel.get_by_role("button", name="下一步", exact=True).click()
            panel.get_by_role("button", name="上一步", exact=True).click()
            panel.get_by_role("button", name="重置", exact=True).click()
            expect(panel.locator(".head-replay-frame")).to_have_attribute(
                "data-frame", "f00"
            )
            panel.get_by_role("button", name="播放", exact=True).click()
            panel.get_by_role("button", name="暂停", exact=True).click()
            paused = panel.locator(".head-replay-frame").get_attribute("data-frame")
            page.wait_for_timeout(1200)
            expect(panel.locator(".head-replay-frame")).to_have_attribute(
                "data-frame", paused
            )
            ex = page.get_by_role("region", name="随堂练习", exact=True)
            assert "例如" not in ex.inner_text()
            for box in ex.locator("textarea").all():
                box.fill("wrong")
            ex.get_by_role("button", name="提交本次作答", exact=True).click()
            expect(ex).to_contain_text("请输入一个 JSON 整数数组")
            ex.get_by_role("button", name="继续完善或新作答", exact=True).click()
            for i, answer in enumerate(["i0", "[11, 30, 40]", "[\n30,40\n]", "1"]):
                ex.locator("textarea").nth(i).fill(answer)
            ex.get_by_role("button", name="提交本次作答", exact=True).click()
            expect(ex).to_contain_text("与暂定参考的匹配比例：100%")
            before = sum(
                r["method"] == "POST" and "/attempts" in r["url"] for r in requests
            )
            page.reload()
            page.wait_for_load_state("networkidle")
            expect(
                page.get_by_role("region", name="随堂练习", exact=True)
            ).to_contain_text("与暂定参考的匹配比例：100%")
            assert before == sum(
                r["method"] == "POST" and "/attempts" in r["url"] for r in requests
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            after = page.evaluate(
                "async ({cid,sid})=>await (await fetch(`/api/free-courses/${cid}/versions/2/scenes/${sid}`)).json()",
                dict(cid=binding["course_id"], sid=binding["scene_id"]),
            )
            assert after == scene
            page.screenshot(path=str(OUT / f"{key}-{width}.png"), full_page=True)
            scenarios.append(
                dict(
                    example=key,
                    width=width,
                    binding=binding,
                    goal_preserved=True,
                    all_frames=len(visual["steps"]),
                    feedback_and_refresh=True,
                    provenance="offline_fixture",
                    model_success=False,
                )
            )
            ctx.close()
        browser.close()
    assert not errors, errors
    assert all(r["url"].startswith("http://127.0.0.1:5198") for r in requests)
    result = dict(
        status="pass_offline_wiring_only",
        provider_calls=0,
        pageerrors=errors,
        scenarios=scenarios,
        requests=requests,
    )
    (OUT / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        "PASS: actual UI goal input, two explicit offline fixture courses, frames/controls/feedback/refresh. Real model successes 0."
    )


if __name__ == "__main__":
    main()
