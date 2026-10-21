from pathlib import Path
import json
import argparse
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(
    description="Check the standalone P1.5 design prototype; no backend calls."
)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
    page.emulate_media(reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(root.joinpath("index.html").as_uri())
    page.screenshot(path=str(out / "home-desktop.png"), full_page=True)
    page.locator('.preview-bar [data-view="plan"]').click()
    page.screenshot(path=str(out / "plan-desktop.png"), full_page=True)
    page.locator('.preview-bar [data-view="course"]').click()
    page.screenshot(path=str(out / "course-desktop.png"), full_page=True)
    page.locator("#next-step").click()
    page.locator("#next-step").click()
    assert "8 → 3 → NULL" in page.locator("#trace-caption").inner_text()
    page.locator('[data-panel="code"]').click()
    assert page.locator(".code-line.highlight").get_attribute("data-line") == "3"
    page.locator('[data-panel="quiz"]').click()
    page.get_by_role("button", name="查看反馈", exact=True).click()
    assert "先选择" in page.locator("#quiz-feedback").inner_text()
    page.locator('input[value="correct"]').check()
    page.get_by_role("button", name="查看反馈", exact=True).click()
    assert "判断正确" in page.locator("#quiz-feedback").inner_text()
    page.locator('[data-scene="2"]').click()
    assert page.locator("#waiting-title").inner_text() == "这一节暂未完成"
    page.locator("#retry-scene").click()
    assert page.locator("#waiting-title").inner_text() == "重试仍未完成"
    page.locator('[data-scene="5"]').click()
    page.locator("#retry-scene").click()
    assert page.locator("#explain-panel").is_visible()
    page.locator("#report-issue").click()
    assert page.locator("dialog").is_visible()
    page.keyboard.press("Escape")
    page.locator('.preview-bar [data-view="home"]').click()
    page.locator("#preferences-button").click()
    assert page.locator("#preferences").is_visible()
    page.locator('#goal-form button[type="submit"]').click()
    assert page.locator("#plan-view").is_visible()
    page.locator("#edit-plan").click()
    page.locator("#plan-note").fill("多解释 next")
    page.wait_for_timeout(7600)
    assert page.locator("#plan-view").is_visible(), (
        "Editing should pause auto-navigation"
    )
    page.locator("#save-plan").click()
    page.locator("#enter-course").click()
    assert page.locator("#course-view").is_visible()
    widths = []
    for width in [1440, 1024, 768, 390, 320]:
        page.set_viewport_size({"width": width, "height": 900})
        for view in ["home", "plan", "course"]:
            page.locator(f'.preview-bar [data-view="{view}"]').click()
            metric = page.evaluate(
                "({viewport:innerWidth,scroll:document.documentElement.scrollWidth})"
            )
            assert metric["scroll"] <= width, (width, view, metric)
            widths.append([width, view, "no overflow"])
            if width == 390:
                page.screenshot(path=str(out / f"{view}-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#toggle-directory").click()
    assert page.locator("#course-directory").is_visible()
    page.locator('[data-scene="4"]').click()
    assert not page.locator("#course-directory").is_visible()
    page.locator("#open-tutor").click()
    assert page.locator("#tutor").is_visible()
    page.locator("#suggested-question").click()
    assert "自环" in page.locator("#tutor-reply").inner_text()
    page.locator("#close-tutor").click()
    page.locator("#menu-button").click()
    assert page.locator("#global-nav").is_visible()
    page.keyboard.press("Escape")
    assert not page.locator("#global-nav").is_visible()
    assert not errors, errors
    (out / "validation.json").write_text(
        json.dumps(
            {
                "page_errors": errors,
                "responsive": widths,
                "interactions": "passed: trace, code highlight, quiz, failure, ready, feedback, preferences, edit pauses transition, mobile directory, tutor, menu",
                "scope": "static prototype only; no backend or Provider",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(
        "PASS: interactive checks and 15 responsive page checks; no browser exceptions"
    )
    b.close()
