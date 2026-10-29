"""Check fixed sample against the engine and exercise every player action in Chromium."""

import json

from playwright.sync_api import sync_playwright

from scripts.isolated_diagnostics.generate_p15_bound_sample import OUT, build
from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    build_actions,
    build_example,
    digest,
)


def main() -> None:
    data, html = build()
    stored = json.loads((OUT / "sample.json").read_text())
    assert stored == data and (OUT / "course.html").read_text() == html
    example = data["example"]
    assert example == build_example(example["spec"])
    assert data["actions"] == build_actions(example, "sample:code")
    assert example["observation"]["caller_head"] == "t1"
    assert example["observation"]["traversal_status"] == "terminated"
    assert example["observation"]["reachable_prefix"] == [2, 1, 9]
    assert example["observation"]["allocation_failures"] == 0
    for action in data["actions"]:
        if action["kind"] == "show_state":
            assert action["state_digest"] == digest(
                example["trace"]["steps"][action["step"]]
            )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        external = []
        errors = []
        page.on(
            "request",
            lambda request: external.append(request.url)
            if request.url.startswith(("http:", "https:"))
            else None,
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((OUT / "course.html").as_uri(), wait_until="load")
        assert page.locator("#progress").get_attribute("data-cursor") == "-1"
        current_state, current_line = None, None
        for index, action in enumerate(data["actions"]):
            page.locator("#next").click()
            assert int(page.locator("#progress").get_attribute("data-cursor")) == index
            assert json.loads(page.locator("#event").inner_text()) == action
            if action["kind"] == "show_state":
                current_state = example["trace"]["steps"][action["step"]]
            if action["kind"] == "highlight_code":
                current_line = action["line"]
            assert json.loads(page.locator("#state").inner_text()) == current_state
            assert page.locator(".line.active").count() == int(current_line is not None)
            if current_line is not None:
                assert page.locator(".line.active").get_attribute("data-line") == str(
                    current_line
                )
        assert page.locator("#next").is_disabled()
        page.locator("#prev").click()
        assert (
            int(page.locator("#progress").get_attribute("data-cursor"))
            == len(data["actions"]) - 2
        )
        page.locator("#reset").click()
        assert page.locator("#progress").get_attribute("data-cursor") == "-1"
        assert page.locator("#state").inner_text() == "尚无状态"
        assert page.locator(".line.active").count() == 0
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
            arg=len(data["actions"]) - 1,
            timeout=10000,
        )
        assert (
            json.loads(page.locator("#state").inner_text())
            == example["trace"]["steps"][-1]
        )
        page.locator("#reset").click()
        page.wait_for_timeout(300)
        assert page.locator("#progress").get_attribute("data-cursor") == "-1"
        assert page.locator("details").count() == 4
        page.locator("details summary").first.click()
        assert page.locator("details").first.get_attribute("open") is not None
        page.screenshot(
            path="/private/tmp/edumind-p15-bound-sample-t093.png", full_page=True
        )
        assert not external and not errors, (external, errors)
        browser.close()
    print(
        f"verified: {len(example['trace']['steps'])} states, {len(data['actions'])} actions, 4 answers; Chromium play/pause/each step/back/reset; 0 external requests"
    )


if __name__ == "__main__":
    main()
