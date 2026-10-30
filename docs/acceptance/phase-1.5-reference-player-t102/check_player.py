"""Offline browser checks for the reference-artifact preview."""

import json

from playwright.sync_api import sync_playwright

from scripts.isolated_diagnostics.generate_p15_reference_player import (
    OUT,
    build,
    sample,
)
from scripts.isolated_diagnostics.p15_head_insertion_engine import build_example
from scripts.isolated_diagnostics.p15_combined_candidate_contract import SPEC
from scripts.isolated_diagnostics import p15_reference_review_v1 as review
from scripts.isolated_diagnostics import p15_reference_document_v1 as document


def main():
    artifact, catalog, _ = sample()
    _, binding = review.review_body(artifact, catalog)
    target_ids = {row["path"]: key for key, row in binding["targets"].items()}
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
                index += 1
        assert page.locator("a[href], img[src]").count() == 0
        assert page.locator(".model-paragraph script").count() == 0
        for index, action in enumerate(actions):
            page.locator("#next").click()
            assert int(page.locator("#progress").get_attribute("data-cursor")) == index
            if action["kind"] == "highlight_code":
                assert page.locator(".line.active").get_attribute("data-line") == str(
                    action["line"]
                )
            if action["kind"] == "show_state":
                assert (
                    json.loads(page.locator("#state").inner_text())
                    == states[action["step"]]
                )
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
            assert (
                row.locator("summary").inner_text()
                == documents["documents"][question["stem_document"]]["original"]
            )
            row.locator("summary").click()
            assert (
                row.locator(".explanation").inner_text()
                == documents["documents"][question["explanation_document"]]["original"]
            )
            assert (
                json.dumps(question["answer_key"], ensure_ascii=False)
                in row.inner_text()
            )
        assert not network and not errors, (network, errors)
        browser.close()
    print(
        f"reference preview: {len(actions)} actions; text, references, highlights, play/pause/reset; zero external requests"
    )


if __name__ == "__main__":
    main()
