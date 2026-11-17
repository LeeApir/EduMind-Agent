"""Actual Vue/API/PG learning journeys; no browser route mocks, no Provider."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-replay-t107"
URL = "http://127.0.0.1:5197"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True, parents=True)
    errors, requests, scenarios = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width in (1440, 390):
            context = browser.new_context(viewport={"width": width, "height": 1000})
            page = context.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on(
                "response",
                lambda r: requests.append(
                    dict(method=r.request.method, url=r.url, status=r.status)
                ),
            )
            page.goto(URL)
            page.wait_for_load_state("networkidle")
            auth = page.evaluate(
                "async()=>await (await fetch('/api/auth/session')).json()"
            )
            owner = auth["user"]["id"]
            for slot in ("C01", "C02"):
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts/head_course_replay.py"),
                        "--import-case",
                        slot,
                        "--owner",
                        owner,
                    ],
                    env=os.environ,
                    check=True,
                    capture_output=True,
                )
            page.reload()
            page.wait_for_load_state("networkidle")

            def nav(name):
                if width <= 850:
                    page.get_by_role("button", name="打开导航", exact=True).click()
                page.get_by_role("navigation", name="主导航").get_by_role(
                    "button", name=name, exact=True
                ).click()

            for slot in ("C01", "C02"):
                nav("学习记录")
                page.get_by_role(
                    "button", name="单链表头插：既有真实候选回放 " + slot, exact=True
                ).click()
                page.get_by_role(
                    "button", name="读取此版本的头插完整课程 · " + slot, exact=True
                ).click()
                panel = page.get_by_role(
                    "region", name="过程演示与代码对照", exact=True
                )
                panel.wait_for()
                expect(
                    page.get_by_role("complementary", name="课程来源")
                ).to_contain_text("既有真实候选回放 · " + slot)
                expected = json.loads(
                    (PACKAGE / f"{slot}.public.proposed.json").read_text()
                )
                private = json.loads(
                    (PACKAGE / f"{slot}.private.proposed.json").read_text()
                )
                steps = next(
                    b["steps"]
                    for b in expected["blocks"]
                    if b["kind"] == "visualization"
                )
                for b in expected["blocks"]:
                    if b["kind"] == "text":
                        assert (
                            b["markdown"] in page.locator(".scene-content").inner_text()
                        )
                for i, step in enumerate(steps):
                    frame = step["head_frame"]
                    expect(panel.locator(".head-replay-frame")).to_have_attribute(
                        "data-frame", frame["frame_id"]
                    )
                    expect(panel.locator(".head-step-note")).to_have_text(frame["note"])
                    expect(panel.locator(".head-replay-frame h4")).to_have_text(
                        frame["title"]
                    )
                    active = panel.locator(".active-code-line")
                    if frame["line"] is None:
                        expect(active).to_have_count(0)
                    else:
                        expect(active).to_have_count(1)
                        expect(active).to_have_attribute(
                            "data-line", str(frame["line"])
                        )
                    if frame["locals_scope"] == "inactive":
                        expect(panel).to_contain_text("head / p：不在作用域")
                    for node in frame["state"]["nodes"].values():
                        if node["next"] == "indeterminate":
                            expect(panel.locator(".head-nodes")).to_contain_text(
                                "未知（未初始化）"
                            )
                    if i == 1 and width == 1440:
                        panel.screenshot(
                            path=str(args.output / f"{slot}-frame-{width}.png")
                        )
                    if i < len(steps) - 1:
                        panel.get_by_role("button", name="下一步", exact=True).click()
                panel.get_by_role("button", name="上一步", exact=True).click()
                expect(panel.locator(".head-replay-frame")).to_have_attribute(
                    "data-frame", steps[-2]["head_frame"]["frame_id"]
                )
                panel.get_by_role("button", name="重置", exact=True).click()
                expect(panel.locator(".head-replay-frame")).to_have_attribute(
                    "data-frame", "f00"
                )
                panel.get_by_role("button", name="播放", exact=True).click()
                expect(
                    panel.get_by_role("button", name="暂停", exact=True)
                ).to_be_enabled()
                panel.get_by_role("button", name="暂停", exact=True).click()
                paused = panel.locator(".head-replay-frame").get_attribute("data-frame")
                page.wait_for_timeout(1300)
                expect(panel.locator(".head-replay-frame")).to_have_attribute(
                    "data-frame", paused
                )
                panel.get_by_role("button", name="重置", exact=True).focus()
                page.keyboard.press("Enter")
                expect(panel.locator(".head-replay-frame")).to_have_attribute(
                    "data-frame", "f00"
                )
                exercise = page.get_by_role("region", name="随堂练习", exact=True)
                for area in exercise.locator("textarea").all():
                    area.fill("wrong")
                exercise.get_by_role("button", name="提交本次作答", exact=True).click()
                expect(exercise).to_contain_text("暂定比较")
                expect(exercise).to_contain_text("请输入一个 JSON 整数数组")
                exercise.get_by_role(
                    "button", name="继续完善或新作答", exact=True
                ).click()
                for i, item in enumerate(private["exercise"]["items"]):
                    value = item["answer_key"]
                    if item["input_type"] == "json_integer_array":
                        value = json.dumps(json.loads(value), indent=1)
                    exercise.locator("textarea").nth(i).fill(value)
                exercise.get_by_role("button", name="提交本次作答", exact=True).click()
                expect(exercise).to_contain_text("与暂定参考的匹配比例：100%")
                for item in private["exercise"]["items"]:
                    assert item["solution"] in exercise.inner_text()
                before = sum(
                    r["method"] == "POST" and "/attempts" in r["url"] for r in requests
                )
                page.reload()
                page.wait_for_load_state("networkidle")
                exercise = page.get_by_role("region", name="随堂练习", exact=True)
                expect(exercise).to_contain_text("与暂定参考的匹配比例：100%")
                assert before == sum(
                    r["method"] == "POST" and "/attempts" in r["url"] for r in requests
                )
                assert page.evaluate(
                    "document.documentElement.scrollWidth<=innerWidth"
                ), (slot, width)
                page.screenshot(
                    path=str(args.output / f"{slot}-{width}.png"), full_page=True
                )
                scenes = page.evaluate(
                    "async()=>await (await fetch('/api/free-courses')).json()"
                )["items"]
                cid = next(
                    c["course_id"] for c in scenes if c["original_goal"].endswith(slot)
                )
                manifest = page.evaluate(
                    "async path=>await (await fetch(path)).json()",
                    f"/api/free-courses/{cid}",
                )["head"]
                scene = page.evaluate(
                    "async path=>await (await fetch(path)).json()",
                    f"/api/free-courses/{cid}/versions/{manifest['version']}/scenes/{manifest['scenes'][0]['scene_id']}",
                )
                assert '"answer_key"' not in json.dumps(
                    scene
                ) and '"solution"' not in json.dumps(scene)
                scenarios.append(
                    dict(
                        slot=slot,
                        width=width,
                        frames=len(steps),
                        course_id=cid,
                        scene_version_id=scene["scene_version_id"],
                        candidate_digest=scene["replay_source"]["candidate_digest"],
                        refresh_duplicate_attempts=0,
                        questions=4,
                    )
                )
            context.close()
        browser.close()
    (args.output / "browser-results.json").write_text(
        json.dumps(
            dict(
                page_errors=errors,
                api_route_mocks=0,
                provider_calls=0,
                scenarios=scenarios,
                requests=requests,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    assert not errors
    print(
        "PASS: actual Vue/API/PG 4 journeys, full frames/controls/questions/refresh; no route mocks"
    )


if __name__ == "__main__":
    main()
