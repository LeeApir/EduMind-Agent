"""ADR-0049 visible-only evidence tests. All replies are synthetic, offline."""

from copy import deepcopy
import json

import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact
from scripts.isolated_diagnostics import p15_visible_review_view_v1 as visible
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC


def make(arm):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    value["paragraphs"][0]["text"] = '`c` [甲"乙][a] [](x)\n\n[a]: https://example.test'
    if arm == "B":
        value["answers"]["allocation_failures"] = (
            4  # deliberate wrong model output; no engine fill
        )
    course = artifact.assemble(
        value,
        c.identity("dev", "slot", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    view, binding = visible.build(course, catalog)
    return course, catalog, view, binding


def issue(view, cell, quote):
    return dict(
        candidate_id=view["candidate_id"],
        verdict="revise",
        uncertainty="",
        issues=[
            dict(
                severity="minor",
                area="difficulty",
                target_id=cell["id"],
                evidence_quote=quote,
                reason="需要解释。",
            )
        ],
    )


@pytest.mark.parametrize("arm", ["B", "C"])
def test_visible_actual_text_supports_exact_quotes_and_has_all_teaching_content(arm):
    course, catalog, view, binding = make(arm)
    cells = view["cells"]
    kinds = [row["kind"] for row in cells]
    for kind in (
        "original_goal",
        "plan_constraints",
        "upstream",
        "goals",
        "question_definitions",
        "source_provenance",
        "block_binding",
        "paragraph",
        "code_line",
        "question_stem",
        "question_answer",
        "question_explanation",
        "state",
        "action",
        "reference_definition",
        "reference_occurrence",
        "reference_example",
        "reference_state",
        "reference_observation",
    ):
        assert kind in kinds
    assert sum(kind == "question_stem" for kind in kinds) == 4
    assert "".join(
        row["text"] + row["line_ending"] for row in cells if row["kind"] == "code_line"
    ) == next(
        row["text"] for row in course["source"]["blocks"] if row["kind"] == "code"
    )
    paragraph = next(row for row in cells if row["kind"] == "paragraph")
    value = issue(view, paragraph, '甲"乙')
    visible.validate_review(value, canonical(view), course, catalog, binding)
    if arm == "B":
        pos = list(c.QUESTION_KEYS).index("allocation_failures")
        assert [row for row in cells if row["kind"] == "question_answer"][pos][
            "text"
        ] == "4"
        assert any(row["kind"] == "model_raw_states" for row in cells)


@pytest.mark.parametrize(
    "mutation",
    [
        "quote",
        "id",
        "candidate",
        "view",
        "binding",
        "not_visible",
        "source_root",
        "projection",
    ],
)
def test_hidden_quote_wrong_id_or_wrong_binding_fails(mutation):
    course, catalog, view, binding = make("C")
    paragraph = next(row for row in view["cells"] if row["kind"] == "paragraph")
    opinion = issue(view, paragraph, "甲")
    sent = canonical(view)
    if mutation == "quote":
        opinion["issues"][0]["evidence_quote"] = "not present"
    elif mutation == "id":
        opinion["issues"][0]["target_id"] = "t01"
    elif mutation == "candidate":
        opinion["candidate_id"] = "candidate_stale"
    elif mutation == "view":
        changed = deepcopy(view)
        changed["cells"][0]["text"] += "changed"
        sent = canonical(changed)
    elif mutation == "binding":
        binding = deepcopy(binding)
        binding["view_digest"] = "0" * 64
    elif mutation == "source_root":
        binding = deepcopy(binding)
        binding["paths"][paragraph["id"]]["root"] = "catalog"
    elif mutation == "projection":
        binding = deepcopy(binding)
        binding["paths"][paragraph["id"]]["projection"] = {
            "type": "lf_line",
            "index": 1,
        }
    else:
        opinion["issues"][0]["evidence_quote"] = "untransmitted-internal-tree-fragment"
    with pytest.raises((c.ContractError, ValueError)):
        visible.validate_review(opinion, sent, course, catalog, binding)


def test_json_escape_is_compared_after_parsing_and_noncanonical_json_is_rejected():
    course, catalog, view, binding = make("C")
    cell = next(row for row in view["cells"] if row["kind"] == "paragraph")
    visible.validate_review(
        issue(view, cell, '甲"乙'), canonical(view), course, catalog, binding
    )
    with pytest.raises(c.ContractError, match="VISIBLE_BINDING"):
        visible.validate_review(
            issue(view, cell, "甲"),
            json.dumps(view, ensure_ascii=False).encode(),
            course,
            catalog,
            binding,
        )


def test_quote_is_not_unicode_normalized():
    catalog = c.make_catalog(SPEC)
    value = content()
    value["paragraphs"][0]["text"] = "组合字符 e\u0301 与普通文字"
    course = artifact.assemble(
        value, c.identity("dev", "slot", "C", 0, SPEC, None), catalog
    )
    view, binding = visible.build(course, catalog)
    cell = next(row for row in view["cells"] if row["kind"] == "paragraph")
    visible.validate_review(
        issue(view, cell, "e\u0301"), canonical(view), course, catalog, binding
    )
    with pytest.raises(c.ContractError, match="QUOTE_BINDING"):
        visible.validate_review(
            issue(view, cell, "é"), canonical(view), course, catalog, binding
        )


def test_old_opinion_cannot_attach_to_new_revision_even_if_short_id_reused():
    old_course, catalog, old_view, _ = make("C")
    paragraph = next(row for row in old_view["cells"] if row["kind"] == "paragraph")
    opinion = issue(old_view, paragraph, "甲")
    revised = artifact.assemble(
        deepcopy(old_course["raw_output"]),
        c.identity("dev", "slot", "C", 1, SPEC, old_course["artifact_digest"]),
        catalog,
    )
    new_view, new_binding = visible.build(revised, catalog)
    assert (
        paragraph["id"]
        == next(row for row in new_view["cells"] if row["kind"] == "paragraph")["id"]
    )
    with pytest.raises(c.ContractError, match="CANDIDATE_ID"):
        visible.validate_review(
            opinion, canonical(new_view), revised, catalog, new_binding
        )


@pytest.mark.parametrize("separator", ["\r\n", "\r", "\u2028", "\x85"])
def test_code_line_boundaries_preserve_exact_model_code(separator):
    catalog = c.make_catalog(SPEC)
    value = b_fixture(SPEC)
    value["code"] = value["code"].replace("\n", separator)
    course = artifact.assemble(
        value, c.identity("dev", "slot", "B", 0, SPEC, None), None
    )
    view, _ = visible.build(course, catalog)
    lines = [cell["text"] for cell in view["cells"] if cell["kind"] == "code_line"]
    assert (
        "".join(
            cell["text"] + cell["line_ending"]
            for cell in view["cells"]
            if cell["kind"] == "code_line"
        )
        == value["code"]
    )
    assert len(lines) == len(value["code"].splitlines())
    assert max(action["line"] for action in value["actions"]["highlights"]) <= len(
        lines
    )


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize("labelled", [False, True])
def test_dense_supported_references_remain_directly_visible(arm, labelled):
    text = "[a] " * 996 + "\n\n[a]: x" if labelled else ("> " * 20) + ("[]()" * 990)
    value = content() if arm == "C" else b_fixture(SPEC)
    template = value["paragraphs"][0]
    value["paragraphs"] = [dict(template, key=f"p{i}", text=text) for i in range(8)]
    for question in value["questions"].values():
        question.update(stem=text, explanation=text)
    catalog = c.make_catalog(SPEC)
    course = artifact.assemble(
        value,
        c.identity("dev", "dense", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    view, binding = visible.build(course, catalog)
    rows = [cell for cell in view["cells"] if cell["kind"] == "reference_occurrence"]
    assert len(rows) == (15_936 if labelled else 15_840)
    assert len(binding["paths"]) == len(view["cells"])
    assert all(
        cell["text"] == text
        for cell in view["cells"]
        if cell["kind"] in ("paragraph", "question_stem", "question_explanation")
    )
    print(
        f"{arm} labelled={labelled}: visible view {len(canonical(view))} bytes; {len(rows)} occurrences"
    )


@pytest.mark.parametrize("arm", ["B", "C"])
def test_reference_occurrence_is_a_distinct_visible_exact_evidence_target(arm):
    course, catalog, view, binding = make(arm)
    rows = [cell for cell in view["cells"] if cell["kind"] == "reference_occurrence"]
    labelled = next(cell for cell in rows if cell["label"] == '甲"乙')
    empty = next(cell for cell in rows if cell["label"] == "")
    assert labelled["id"] != empty["id"]
    visible.validate_review(
        issue(view, labelled, '甲"乙'), canonical(view), course, catalog, binding
    )
    visible.validate_review(
        issue(view, empty, empty["reference_kind"]),
        canonical(view),
        course,
        catalog,
        binding,
    )
    assert binding["paths"][labelled["id"]]["pointer"].endswith("/label")
    assert binding["paths"][empty["id"]]["pointer"].endswith("/kind")


def test_structurally_valid_b_combined_code_and_reference_capacity_gap():
    text = "[a] " * 996 + "\n\n[a]: x"
    value = b_fixture(SPEC)
    template = value["paragraphs"][0]
    value["paragraphs"] = [dict(template, key=f"p{i}", text=text) for i in range(8)]
    for question in value["questions"].values():
        question.update(stem=text, explanation=text)
    value["code"] = "\n" * 20_000
    catalog = c.make_catalog(SPEC)
    course = artifact.assemble(
        value, c.identity("dev", "max", "B", 0, SPEC, None), None
    )
    view, _ = visible.build(course, catalog)
    assert len(canonical(value)) < c.MAX_PAYLOAD
    assert (
        len([cell for cell in view["cells"] if cell["kind"] == "code_line"]) == 20_000
    )
    assert len(canonical(view)) > 4 * 1024 * 1024
    print(
        f"B combined capacity: raw={len(canonical(value))} view={len(canonical(view))}"
    )


@pytest.mark.parametrize("arm", ["B", "C"])
def test_definition_url_and_title_are_exact_visible_targets(arm):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    value["paragraphs"][0]["text"] = (
        "`c` [标签][a]\n\n[a]: https://example.test/a '甲\"乙'"
    )
    course = artifact.assemble(
        value,
        c.identity("dev", "slot", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    view, binding = visible.build(course, catalog)
    url = next(cell for cell in view["cells"] if cell["kind"] == "reference_url")
    title = next(cell for cell in view["cells"] if cell["kind"] == "reference_title")
    assert url["text"] == "https://example.test/a" and title["text"] == '甲"乙'
    visible.validate_review(
        issue(view, url, "example.test"), canonical(view), course, catalog, binding
    )
    visible.validate_review(
        issue(view, title, '甲"乙'), canonical(view), course, catalog, binding
    )
    assert binding["paths"][url["id"]]["pointer"].endswith("/url")
    assert binding["paths"][title["id"]]["pointer"].endswith("/title")


def test_empty_markdown_title_remains_in_raw_text_even_if_parser_normalizes_it():
    catalog = c.make_catalog(SPEC)
    value = content()
    text = '[x](https://example.test "")'
    value["paragraphs"][0]["text"] = text
    course = artifact.assemble(
        value, c.identity("dev", "slot", "C", 0, SPEC, None), catalog
    )
    view, binding = visible.build(course, catalog)
    paragraph = next(cell for cell in view["cells"] if cell["kind"] == "paragraph")
    title = next(cell for cell in view["cells"] if cell["kind"] == "reference_title")
    assert paragraph["text"] == text
    assert title["text"] == "null" and binding["paths"][title["id"]][
        "pointer"
    ].endswith("/title")
    visible.validate_review(
        issue(view, paragraph, '""'), canonical(view), course, catalog, binding
    )
