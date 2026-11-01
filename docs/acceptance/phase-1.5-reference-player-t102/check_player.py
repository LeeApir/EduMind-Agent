"""Offline browser checks for the reference-artifact preview."""

import json

from playwright.sync_api import sync_playwright

from scripts.isolated_diagnostics.generate_p15_reference_player import (
    OUT,
    build,
    sample,
)
from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    build_example,
    canonical,
)
from scripts.isolated_diagnostics.p15_combined_candidate_contract import SPEC
from scripts.isolated_diagnostics import p15_visible_review_view_v1 as visible
from scripts.isolated_diagnostics import p15_reference_document_v1 as document
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifacts
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.tests.test_p15_minimal_pilot import b_fixture
from scripts.tests.test_p15_minimal_pilot import content as c_content


def main():
    artifact, catalog, _ = sample()
    view, binding = visible.build(artifact, catalog)
    visible_text = {cell["id"]: cell["text"] for cell in view["cells"]}
    visible_cells = {cell["id"]: cell for cell in view["cells"]}
    target_ids = {
        row["pointer"]: key
        for key, row in binding["paths"].items()
        if row["root"] == "artifact"
        and row["projection"]["type"]
        in ("identity", "reference_occurrence", "reference_definition")
    }
    assert (OUT / "course.html").read_text() == build()
    source = artifact["source"]
    documents = source["documents"]
    actions = source["actions"]
    states = build_example(SPEC)["trace"]["steps"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        network, errors = [], []
        page.on(
            "request",
            lambda request: network.append(request.url)
            if request.url.startswith(("http:", "https:"))
            else None,
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((OUT / "course.html").as_uri(), wait_until="load")
        assert (
            page.locator("#candidate-digest").inner_text()
            == artifact["artifact_digest"]
        )
        assert page.evaluate("() => data.view_digest") == binding["view_digest"]
        for index, block in enumerate(
            b for b in source["blocks"] if b["kind"] == "text"
        ):
            assert (
                page.locator(".model-paragraph").nth(index).inner_text()
                == documents["documents"][block["document"]]["original"]
            )
            assert (
                page.locator(".model-paragraph")
                .nth(index)
                .get_attribute("data-target-id")
                == target_ids[f"/raw_output/paragraphs/{index}/text"]
            )
        assert page.locator("#references .reference").count() == len(
            documents["references"]
        )
        for i, ref in enumerate(documents["references"]):
            assert (
                page.locator("#references .reference")
                .nth(i)
                .get_attribute("data-target-id")
                == target_ids[f"/source/documents/references/{ref}"]
            )
            row = page.locator("#references .reference").nth(i)
            for selector, path in (
                (".reference-summary", f"/source/documents/references/{ref}"),
                (".reference-url", f"/source/documents/references/{ref}/url"),
                (".reference-title", f"/source/documents/references/{ref}/title"),
            ):
                assert (
                    row.locator(selector).get_attribute("data-target-id")
                    == target_ids[path]
                )
                assert (
                    row.locator(selector).text_content()
                    == visible_text[target_ids[path]]
                )
        assert page.locator("#occurrences .occurrence").count() == sum(
            len(row["occurrences"]) for row in documents["documents"].values()
        )
        index = 0
        for key, value in documents["documents"].items():
            for local_index, occurrence in enumerate(value["occurrences"]):
                row = page.locator("#occurrences .occurrence").nth(index)
                assert row.get_attribute("data-document") == key
                assert json.loads(row.get_attribute("data-path")) == occurrence["path"]
                assert row.get_attribute("data-id") == occurrence["reference_id"]
                assert (
                    row.get_attribute("data-target-id")
                    == target_ids[
                        f"/source/documents/documents/{key}/occurrences/{local_index}/{'label' if occurrence['label'] else 'kind'}"
                    ]
                )
                assert (
                    document.occurrence_label(documents, key, occurrence)
                    in row.inner_text()
                )
                assert (
                    visible_cells[row.get_attribute("data-target-id")]["reference_id"]
                    in row.inner_text()
                )
                assert (
                    row.locator(".evidence-target").text_content()
                    == visible_text[row.get_attribute("data-target-id")]
                )
                index += 1
        assert page.locator("a[href], img[src]").count() == 0
        assert page.locator(".model-paragraph script").count() == 0
        code = next(b["text"] for b in source["blocks"] if b["kind"] == "code")
        assert page.locator(".line").count() == len(code.splitlines())
        for i, line in enumerate(code.splitlines()):
            assert (
                page.locator(".line").nth(i).text_content()
                == str(i + 1).rjust(2) + "  " + line
            )
            assert (
                page.locator(".line").nth(i).get_attribute("data-target-id")
                == [
                    cell["id"] for cell in view["cells"] if cell["kind"] == "code_line"
                ][i]
            )
        for index, action in enumerate(actions):
            page.locator("#next").click()
            assert int(page.locator("#progress").get_attribute("data-cursor")) == index
            expected_action = [
                cell for cell in view["cells"] if cell["kind"] == "action"
            ][index]
            assert (
                page.locator("#event").get_attribute("data-target-id")
                == expected_action["id"]
            )
            assert page.locator("#event").text_content() == expected_action["text"]
            if action["kind"] == "highlight_code":
                assert page.locator(".line.active").get_attribute("data-line") == str(
                    action["line"]
                )
            if action["kind"] == "show_state":
                assert (
                    json.loads(page.locator("#state").inner_text())
                    == states[action["step"]]
                )
                expected_state = [
                    cell for cell in view["cells"] if cell["kind"] == "state"
                ][action["step"]]
                assert (
                    page.locator("#state").get_attribute("data-target-id")
                    == expected_state["id"]
                )
                assert page.locator("#state").text_content() == expected_state["text"]
        assert page.locator("#next").is_disabled()
        page.locator("#prev").click()
        assert (
            int(page.locator("#progress").get_attribute("data-cursor"))
            == len(actions) - 2
        )
        page.locator("#reset").click()
        assert page.locator("#progress").get_attribute("data-cursor") == "-1"
        page.locator("#play").click()
        page.wait_for_function(
            "() => Number(document.querySelector('#progress').dataset.cursor) >= 1",
            timeout=3000,
        )
        page.locator("#pause").click()
        before = page.locator("#progress").get_attribute("data-cursor")
        page.wait_for_timeout(400)
        assert page.locator("#progress").get_attribute("data-cursor") == before
        page.locator("#play").click()
        page.wait_for_function(
            "n => Number(document.querySelector('#progress').dataset.cursor) === n",
            arg=len(actions) - 1,
            timeout=10000,
        )
        page.locator("#reset").click()
        page.locator("#play").click()
        page.wait_for_function(
            "() => Number(document.querySelector('#progress').dataset.cursor) >= 0",
            timeout=3000,
        )
        page.locator("#reset").click()
        page.wait_for_timeout(400)
        assert page.locator("#progress").get_attribute("data-cursor") == "-1"
        questions = [block for block in source["blocks"] if block["kind"] == "question"]
        for i, question in enumerate(questions):
            row = page.locator(".question").nth(i)
            block_index = source["blocks"].index(question)
            assert (
                row.locator("summary").get_attribute("data-target-id")
                == target_ids[
                    f"/raw_output/questions/{question['observation_key']}/stem"
                ]
            )
            assert (
                row.locator("code").get_attribute("data-target-id")
                == target_ids[f"/source/blocks/{block_index}/answer_key"]
            )
            assert (
                row.locator(".explanation").get_attribute("data-target-id")
                == target_ids[
                    f"/raw_output/questions/{question['observation_key']}/explanation"
                ]
            )
            assert (
                row.locator("summary").inner_text()
                == documents["documents"][question["stem_document"]]["original"]
            )
            row.locator("summary").click()
            assert (
                row.locator(".explanation").inner_text()
                == documents["documents"][question["explanation_document"]]["original"]
            )
            assert canonical(question["answer_key"]).decode() in row.inner_text()
        # The development B fixture intentionally disagrees with the reference.
        # Playback must use the model-origin state, not catalog.example.
        b_value = b_fixture(SPEC)
        b_value["actions"]["states"][0]["nodes"][0]["data"] = 77
        b_value["answers"]["allocation_failures"] = 4
        b_value["code"] = b_value["code"].replace("\n", "\u2028")
        b_course = artifacts.assemble(
            b_value, c.identity("dev", "b_slot", "B", 0, SPEC, None), None
        )
        b_view, b_binding = visible.build(b_course, catalog)
        b_page = browser.new_page()
        b_page.on(
            "request",
            lambda request: network.append(request.url)
            if request.url.startswith(("http:", "https:"))
            else None,
        )
        b_page.on("pageerror", lambda error: errors.append(str(error)))
        b_page.set_content(build(b_course, catalog), wait_until="load")
        assert b_page.get_by_role("heading", name="模型题目与模型原始答案").count() == 1
        assert b_page.evaluate("() => data.view_digest") == b_binding["view_digest"]
        b_lines = [cell for cell in b_view["cells"] if cell["kind"] == "code_line"]
        assert (
            b_page.locator(".line").count()
            == len(b_value["code"].splitlines())
            == len(b_lines)
        )
        assert (
            "".join(cell["text"] + cell["line_ending"] for cell in b_lines)
            == b_value["code"]
        )
        for i, cell in enumerate(b_lines):
            assert (
                b_page.locator(".line").nth(i).get_attribute("data-target-id")
                == cell["id"]
            )
        b_page.locator("#next").click()
        assert (
            json.loads(b_page.locator("#state").inner_text())
            == b_course["source"]["actions"][0]["state"]
        )
        assert (
            json.loads(b_page.locator("#state").inner_text())["nodes"]["i0"]["data"]
            == 77
        )
        expected_b_state = next(
            cell for cell in b_view["cells"] if cell["kind"] == "state"
        )
        assert (
            b_page.locator("#state").get_attribute("data-target-id")
            == expected_b_state["id"]
        )
        assert b_page.locator("#state").text_content() == expected_b_state["text"]
        b_action_cells = [cell for cell in b_view["cells"] if cell["kind"] == "action"]
        for index, action in enumerate(b_course["source"]["actions"][1:], start=1):
            b_page.locator("#next").click()
            assert (
                b_page.locator("#event").get_attribute("data-target-id")
                == b_action_cells[index]["id"]
            )
            assert (
                b_page.locator("#event").text_content() == b_action_cells[index]["text"]
            )
            if action["kind"] == "show_state":
                assert (
                    json.loads(b_page.locator("#state").inner_text()) == action["state"]
                )
            elif action["kind"] == "highlight_code":
                assert b_page.locator(".line.active").get_attribute("data-line") == str(
                    action["line"]
                )
        b_answers = [
            cell["id"] for cell in b_view["cells"] if cell["kind"] == "question_answer"
        ]
        assert [
            row.get_attribute("data-target-id")
            for row in b_page.locator(".question code").all()
        ] == b_answers
        control_value = c_content()
        control_value["paragraphs"][0]["text"] = "甲\x00乙\r丙\r\n丁 😀"
        control_value["questions"]["caller_head"]["stem"] = "题\x00干\r\n结束"
        control_value["questions"]["caller_head"]["explanation"] = "解\r析\x00结束"
        control_course = artifacts.assemble(
            control_value, c.identity("dev", "controls", "C", 0, SPEC, None), catalog
        )
        control_view, control_binding = visible.build(control_course, catalog)
        control_page = browser.new_page()
        control_page.on(
            "request",
            lambda request: network.append(request.url)
            if request.url.startswith(("http:", "https:"))
            else None,
        )
        control_page.on("pageerror", lambda error: errors.append(str(error)))
        control_page.set_content(build(control_course, catalog), wait_until="load")
        control_targets = {cell["id"]: cell["text"] for cell in control_view["cells"]}
        assert (
            control_page.evaluate("() => data.view_digest")
            == control_binding["view_digest"]
        )
        for selector in (
            ".model-paragraph",
            ".question summary",
            ".question .explanation",
        ):
            for element in control_page.locator(selector).all():
                assert (
                    element.text_content()
                    == control_targets[element.get_attribute("data-target-id")]
                )
        assert (
            control_page.locator(".model-paragraph").first.text_content()
            == control_value["paragraphs"][0]["text"]
        )
        assert not network and not errors, (network, errors)
        browser.close()
    print(
        f"reference preview: {len(actions)} actions; text, references, highlights, play/pause/reset; zero external requests"
    )


if __name__ == "__main__":
    main()
