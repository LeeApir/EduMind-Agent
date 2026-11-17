"""Actual Chromium assembly check using explicitly synthetic text, never a model course."""

import json
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from test_preparation import content
import prepare as p


def main():
    errors, external = [], []
    with tempfile.TemporaryDirectory(prefix="edumind-t104-synthetic-") as folder:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            page.on("pageerror", lambda err: errors.append(str(err)))
            page.on(
                "request",
                lambda req: external.append(req.url)
                if req.url.startswith(("http:", "https:"))
                else None,
            )
            for slot in p.SPECS:
                value = content(slot)
                value["step_notes"][0]["note"] = (
                    "合成测试 </script><script>alert(1)</script>"
                )
                target = Path(folder) / (slot + ".html")
                target.write_text(p.render(slot, value))
                page.goto(target.as_uri(), wait_until="networkidle")
                assert (
                    page.locator("#step-note").inner_text()
                    == value["step_notes"][0]["note"]
                )
                cat = p.c.make_catalog(p.SPECS[slot])
                frames = p.frames(cat)
                for i, f in enumerate(frames):
                    if i:
                        page.locator("#next").click()
                    assert page.locator("#progress").get_attribute(
                        "data-cursor"
                    ) == str(i)
                    assert (
                        page.locator("#step-note").inner_text()
                        == value["step_notes"][i]["note"]
                    )
                    assert page.locator(".active").count() == int(f["line"] is not None)
                    if f["line"] is not None:
                        assert page.locator(".active").get_attribute(
                            "data-line"
                        ) == str(f["line"])
                expected = (
                    "caller_head → t1(2) → t0(1) → i0(9) → NULL"
                    if slot == "C01"
                    else "caller_head → t1(5) → NULL"
                )
                assert page.locator("#chain").inner_text() == expected
                assert page.locator("#next").is_disabled()
                page.locator("#prev").click()
                page.locator("#reset").click()
                page.locator("#play").click()
                page.wait_for_function(
                    "() => document.querySelector('#progress').dataset.cursor !== '0'"
                )
                page.locator("#pause").click()
                paused = page.locator("#progress").get_attribute("data-cursor")
                page.wait_for_timeout(1200)
                assert page.locator("#progress").get_attribute("data-cursor") == paused
                page.locator("#reset").click()
                for i, key in enumerate(sorted(p.c.QUESTION_KEYS)):
                    div = page.locator(".question").nth(i)
                    answer = cat["example"]["observation"][key]
                    if key == "caller_head" and answer is None:
                        answer = "none"
                    div.locator("input").fill("wrong")
                    div.locator("button").click()
                    assert div.get_attribute("data-correct") != "true"
                    div.locator("input").fill(
                        answer if isinstance(answer, str) else json.dumps(answer)
                    )
                    div.locator("input").press("Enter")
                    assert div.get_attribute("data-correct") == "true"
                    div.locator("summary").click()
                    assert "合成解析" in div.inner_text()
                assert page.locator("#score").inner_text() == "已答对 4 / 4 题"
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                )
                page.locator("#next").focus()
                page.keyboard.press("Enter")
                assert page.locator("#progress").get_attribute("data-cursor") == "1"
                page.set_viewport_size({"width": 1200, "height": 900})
            browser.close()
    assert not errors and not external, (errors, external)
    result = dict(
        material="synthetic offline fixture only; not a generated course or semantic quality evidence",
        samples=["C01:13 frames", "C02:10 frames"],
        checks=[
            "all frame texts and highlights",
            "independent final chains",
            "play/pause/prev/reset",
            "four wrong/correct/answer explanations",
            "textContent escaping",
            "keyboard and 390px mobile",
        ],
        page_errors=errors,
        http_requests=external,
        real_provider_calls=0,
    )
    (p.HERE / "browser-check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
