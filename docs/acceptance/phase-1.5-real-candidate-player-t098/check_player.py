"""Chromium verifies the actual frozen candidate's full action sequence."""

import json

from playwright.sync_api import sync_playwright

from scripts.isolated_diagnostics.generate_p15_real_candidate_player import (
    OUT,
    SOURCE,
    build,
)
from scripts.isolated_diagnostics.p15_combined_candidate_contract import SPEC
from scripts.isolated_diagnostics.p15_head_insertion_engine import build_example


def main():
    artifact = json.loads(SOURCE.read_text())
    source = artifact["source"]
    example = build_example(SPEC)
    actions = source["actions"]
    states = example["trace"]["steps"]
    assert (OUT / "course.html").read_text() == build()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        external = []
        errors = []
        page.on(
            "request",
            lambda req: external.append(req.url)
            if req.url.startswith(("http:", "https:"))
            else None,
        )
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto((OUT / "course.html").as_uri(), wait_until="load")
        assert (
            page.locator("#candidate-digest").inner_text()
            == artifact["artifact_digest"]
        )
        paragraphs = [b["markdown"] for b in source["blocks"] if b["kind"] == "text"]
        assert page.locator(".model-paragraph").all_inner_texts() == paragraphs
        questions = [b for b in source["blocks"] if b["kind"] == "question"]
        assert page.locator(".question summary").all_inner_texts() == [
            q["stem"] for q in questions
        ]
        code = next(b["text"] for b in source["blocks"] if b["kind"] == "code")
        assert page.locator(".line").count() == len(code.strip().splitlines())
        shown = None
        line = None
        for i, action in enumerate(actions):
            page.locator("#next").click()
            assert int(page.locator("#progress").get_attribute("data-cursor")) == i
            assert json.loads(page.locator("#event").inner_text()) == action
            if action["kind"] == "show_state":
                shown = states[action["step"]]
                line = None
            if action["kind"] == "highlight_code":
                line = action["line"]
            assert json.loads(page.locator("#state").inner_text()) == shown
            assert page.locator(".line.active").count() == int(line is not None)
            if line is not None:
                assert page.locator(".line.active").get_attribute("data-line") == str(
                    line
                )
            if action["kind"] == "advance_step":
                assert "即将进入步骤" in page.locator("#scope").inner_text()
            if shown["phase"] == "caller":
                assert "返回前快照" in page.locator("#scope").inner_text()
            if shown["phase"] == "initial":
                assert "不在作用域" in page.locator("#scope").inner_text()
        assert page.locator("#next").is_disabled()
        page.locator("#prev").click()
        assert (
            int(page.locator("#progress").get_attribute("data-cursor"))
            == len(actions) - 2
        )
        page.locator("#reset").click()
        assert (
            page.locator("#progress").get_attribute("data-cursor") == "-1"
            and page.locator(".line.active").count() == 0
        )
        page.locator("#play").click()
        page.wait_for_function(
            "() => Number(document.querySelector('#progress').dataset.cursor) >= 1",
            timeout=3000,
        )
        page.locator("#pause").click()
        paused = page.locator("#progress").get_attribute("data-cursor")
        page.wait_for_timeout(500)
        assert page.locator("#progress").get_attribute("data-cursor") == paused
        page.locator("#play").click()
        page.wait_for_function(
            "n => Number(document.querySelector('#progress').dataset.cursor) === n",
            arg=len(actions) - 1,
            timeout=10000,
        )
        assert json.loads(page.locator("#state").inner_text()) == states[-1]
        page.locator("#reset").click()
        page.locator("#play").click()
        page.wait_for_function(
            "() => Number(document.querySelector('#progress').dataset.cursor) >= 0",
            timeout=3000,
        )
        page.locator("#reset").click()
        page.wait_for_timeout(500)
        assert page.locator("#progress").get_attribute("data-cursor") == "-1"
        for i, q in enumerate(questions):
            page.locator(".question summary").nth(i).click()
            assert (
                q["explanation"]
                == page.locator(".question .explanation").nth(i).inner_text()
            )
            assert (
                json.dumps(q["answer_key"], ensure_ascii=False)
                in page.locator(".question").nth(i).inner_text()
            )
        page.screenshot(
            path="/private/tmp/edumind-real-candidate-t098.png", full_page=True
        )
        assert not external and not errors, (external, errors)
        browser.close()
    print(
        f"actual candidate: {len(paragraphs)} paragraphs, {len(questions)} questions, {len(states)} states, {len(actions)} actions; play/pause/each step/back/reset/highlights verified; no external requests"
    )


if __name__ == "__main__":
    main()
