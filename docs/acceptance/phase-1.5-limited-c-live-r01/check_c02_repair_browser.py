"""Independent C02 repair lesson check. No provider or C execution.

Pointer/line/answer expectations below were hand-derived from this fixed C source,
not read from the engine's computed states or reference answers.
"""

import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
CANDIDATE = "94b98e3411cdffdce46a77387aac92d3333731e5bae340e2e886cad82596dea0"
PARENT = "11733f29cba774f7273429bc20326f40eae9b38e02f727f9ebf6435df9573a51"
PAGE_SHA = "92d7468a3b0a0b85eb5684bad9b56e16716701b6d0ccd790744f251baed31461"


def changes(left, right, path=()):
    if isinstance(left, dict) and isinstance(right, dict):
        assert left.keys() == right.keys()
        return [p for key in left for p in changes(left[key], right[key], (*path, key))]
    if isinstance(left, list) and isinstance(right, list):
        assert len(left) == len(right)
        return [
            p
            for i, (a, b) in enumerate(zip(left, right))
            for p in changes(a, b, (*path, i))
        ]
    return [] if left == right else [path]


def main():
    candidate = json.loads((OUT / "C02-repair.candidate.json").read_text())
    first = json.loads((OUT / "C02-generate.candidate.json").read_text())
    page_path = OUT / "C02-repair.course.html"
    assert candidate["artifact_digest"] == CANDIDATE
    assert candidate["parent_digest"] == first["artifact_digest"] == PARENT
    assert hashlib.sha256(page_path.read_bytes()).hexdigest() == PAGE_SHA
    text = candidate["raw_output"]
    assert changes(first["raw_output"], text) == [
        ("questions", "reachable_prefix", "stem")
    ]
    assert "请只回答一个 JSON 整数数组" in text["questions"]["reachable_prefix"]["stem"]
    # Independent manual expectations: no t0; all caller chains remain empty
    # until main receives the second return value at source line 13.
    lines = [None, 4, 5, 12, 4, 5, 6, 7, 8, 13]
    chains = ["caller_head → NULL"] * 9 + ["caller_head → t1(5) → NULL"]
    values = [None, None, None, None, "未知", "未知", "5", "5", "5", "5"]
    nexts = [None, None, None, None, "未知", "未知", "未知", "NULL", "NULL", "NULL"]
    errors, requests = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on(
            "request",
            lambda req: requests.append(req.url)
            if req.url.startswith(("http:", "https:"))
            else None,
        )
        page.goto(page_path.as_uri(), wait_until="networkidle")
        for key in ["prerequisites", "learning_summary", "lifecycle", "failure_scope"]:
            assert page.locator("#" + key).inner_text() == text[key]
        assert page.locator("#paragraphs p").all_inner_texts() == [
            r["text"] for r in text["paragraphs"]
        ]
        code = next(
            b["text"]
            for b in candidate["base_artifact"]["source"]["blocks"]
            if b["kind"] == "code"
        )
        assert page.locator(".line").all_inner_texts() == [
            f"{i + 1}  {line}" for i, line in enumerate(code.rstrip().splitlines())
        ]
        for i, line in enumerate(lines):
            if i:
                page.locator("#next").click()
            assert page.locator("#progress").get_attribute("data-cursor") == str(i)
            assert page.locator("#chain").inner_text() == chains[i]
            assert (
                page.locator("#step-title").inner_text()
                == text["step_notes"][i]["title"]
            )
            assert (
                page.locator("#step-note").inner_text() == text["step_notes"][i]["note"]
            )
            assert page.locator(".line.active").count() == int(line is not None)
            if line is not None:
                assert page.locator(".line.active").get_attribute("data-line") == str(
                    line
                )
            assert "t0" not in page.locator("#nodes").inner_text()
            if values[i] is None:
                assert page.locator(".node").count() == 0
            else:
                assert page.locator(".node").all_inner_texts() == [
                    f"t1 | data: {values[i]} | next: {nexts[i]}"
                ]
            variables = page.locator("#vars").inner_text()
            if i in (0, 3, 9):
                assert "不在作用域" in variables
            elif i in (1, 2):
                assert "head = NULL" in variables and "p = NULL" in variables
            else:
                assert "head = NULL" in variables and "p = t1" in variables
        assert page.locator("#next").is_disabled()
        page.locator("#prev").click()
        assert page.locator("#progress").get_attribute("data-cursor") == "8"
        page.locator("#reset").click()
        page.locator("#play").click()
        page.wait_for_function(
            "() => document.querySelector('#progress').dataset.cursor !== '0'"
        )
        page.locator("#pause").click()
        paused = page.locator("#progress").get_attribute("data-cursor")
        page.wait_for_timeout(1250)
        assert page.locator("#progress").get_attribute("data-cursor") == paused
        page.locator("#play").click()
        page.locator("#reset").click()
        page.wait_for_timeout(1250)
        assert page.locator("#progress").get_attribute("data-cursor") == "0"
        answers = [
            ("allocation_failures", "1"),
            ("caller_head", "t1"),
            ("reachable_prefix", "[5]"),
            ("traversal_status", "terminated"),
        ]
        for i, (key, answer) in enumerate(answers):
            q = page.locator(".question").nth(i)
            assert text["questions"][key]["stem"] in q.locator("label").inner_text()
            q.locator("input").fill("wrong")
            q.locator("button").click()
            assert q.get_attribute("data-correct") != "true"
            q.locator("input").fill(answer)
            q.locator("input").press("Enter")
            assert q.get_attribute("data-correct") == "true"
            q.locator("summary").click()
            assert (
                text["questions"][key]["explanation"]
                in q.locator("details p").inner_text()
            )
        assert page.locator("#score").inner_text() == "已答对 4 / 4 题"
        prefix = page.locator(".question").nth(2)
        prefix.locator("input").fill("[5]，这是完整遍历")
        prefix.locator("button").click()
        assert "格式不正确" in prefix.locator('[role="status"]').inner_text()
        prefix.locator("input").fill("[5]")
        prefix.locator("button").click()
        assert prefix.get_attribute("data-correct") == "true"
        page.screenshot(
            path="/private/tmp/edumind-c02-repair-independent-desktop.png",
            full_page=True,
        )
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#next").focus()
        page.keyboard.press("Enter")
        assert page.locator("#progress").get_attribute("data-cursor") == "1"
        page.locator("#reset").click()
        page.screenshot(
            path="/private/tmp/edumind-c02-repair-independent-mobile.png",
            full_page=True,
        )
        assert not errors and not requests, (errors, requests)
        browser.close()
    print(
        json.dumps(
            dict(
                candidate_digest=CANDIDATE,
                parent_digest=PARENT,
                course_sha256=PAGE_SHA,
                checks="full text identity, 10 hand-derived frames/chain/nodes/highlight/scope, play/pause/prev/reset, 4 wrong/correct/explanations, repaired input contract, keyboard/390px mobile",
                page_errors=errors,
                http_requests=requests,
                real_provider_calls=0,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
