"""Review of the same versioned reference artifact; offline only."""

import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact
from scripts.isolated_diagnostics import p15_reference_review_v1 as review
from scripts.isolated_diagnostics import p15_review_path_v2 as policy
from scripts.tests.test_p15_combined_candidate_contract import response
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC


@pytest.mark.parametrize("arm", ["B", "C"])
def test_review_uses_same_artifact_and_located_evidence(arm):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    value["paragraphs"][0]["text"] = "`code` [示例][a]\n\n[a]: https://example.test/"
    course = artifact.assemble(
        value,
        c.identity("dev", "slot", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    body, binding = review.review_body(course, catalog)
    request = c.strict_json(body)
    payload = c.strict_json(request["input"][1]["content"].encode())
    assert payload["artifact"] == course
    key, target = next(
        (key, row)
        for key, row in binding["targets"].items()
        if row["path"] == "/raw_output/paragraphs/0/text"
    )
    issue = dict(
        severity="minor",
        area="difficulty",
        target_id=key,
        evidence_quote="示例",
        reason="补充解释。",
    )
    opinion = dict(
        candidate_id=binding["candidate_id"],
        verdict="revise",
        uncertainty="",
        issues=[issue],
    )
    observed, _ = review.observe(
        body, response(body, opinion), binding, policy.reservation(body)
    )
    assert c.review_disposition(observed) == "ordinary_revise"
    assert "示例" in target["text"]


def test_prior_markdown_expansion_example_is_reviewable_with_shared_references():
    text = "`a` " + ("[x][a] " * 240) + "\n\n[a]: https://a.test/" + "x" * 2000
    value = content()
    template = value["paragraphs"][0]
    value["paragraphs"] = [dict(template, key=f"p{i}", text=text) for i in range(8)]
    value["questions"]["caller_head"]["stem"] = text
    catalog = c.make_catalog(SPEC)
    course = artifact.assemble(
        value, c.identity("dev", "max", "C", 0, SPEC, None), catalog
    )
    body, binding = review.review_body(course, catalog)
    assert len(body) < policy.POLICY.request_bytes
    assert len(course["source"]["documents"]["references"]) == 1
    assert binding["artifact"] == course
    print(f"shared-reference review request: {len(body)} bytes")


def test_occurrence_labels_are_distinct_exact_targets_with_quotes():
    catalog = c.make_catalog(SPEC)
    value = content()
    value["paragraphs"][0]["text"] = (
        '`code` [甲"乙][a] [甲"乙][a]\n\n[a]: https://example.test/'
    )
    course = artifact.assemble(
        value, c.identity("dev", "slot", "C", 0, SPEC, None), catalog
    )
    body, binding = review.review_body(course, catalog)
    rows = [
        (key, row)
        for key, row in binding["targets"].items()
        if "/occurrences/" in row["path"] and row["path"].endswith("/label")
    ]
    assert len(rows) == 2 and rows[0][0] != rows[1][0]
    assert all(row["text"] == '甲"乙' for _, row in rows)
    issue = dict(
        severity="minor",
        area="difficulty",
        target_id=rows[0][0],
        evidence_quote='甲"乙',
        reason="说明引用。",
    )
    opinion = dict(
        candidate_id=binding["candidate_id"],
        verdict="revise",
        uncertainty="",
        issues=[issue],
    )
    observed, _ = review.observe(
        body, response(body, opinion), binding, policy.reservation(body)
    )
    assert observed == opinion
    opinion["issues"][0]["evidence_quote"] = "不存在"
    with pytest.raises(c.ContractError, match="QUOTE_BINDING"):
        review.observe(body, response(body, opinion), binding, policy.reservation(body))


@pytest.mark.parametrize("arm", ["B", "C"])
def test_empty_reference_label_has_independent_nonempty_kind_target(arm):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    value["paragraphs"][0]["text"] = (
        "`code` [](https://example.test/a) ![](https://example.test/a)"
    )
    course = artifact.assemble(
        value,
        c.identity("dev", "slot", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    body, binding = review.review_body(course, catalog)
    rows = [
        (key, row)
        for key, row in binding["targets"].items()
        if "/occurrences/" in row["path"] and row["path"].endswith("/kind")
    ]
    assert len(rows) == 2 and {row["text"] for _, row in rows} == {"link", "image"}
    for key, row in rows:
        issue = dict(
            severity="minor",
            area="difficulty",
            target_id=key,
            evidence_quote=row["text"],
            reason="补充说明。",
        )
        opinion = dict(
            candidate_id=binding["candidate_id"],
            verdict="revise",
            uncertainty="",
            issues=[issue],
        )
        observed, _ = review.observe(
            body, response(body, opinion), binding, policy.reservation(body)
        )
        assert observed == opinion


@pytest.mark.parametrize("arm", ["B", "C"])
def test_repeated_nested_references_across_all_16_fields(arm):
    text = (
        ("> " * 20)
        + "`a` "
        + ("[x][a] " * 240)
        + "\n\n[a]: https://a.test/"
        + "x" * 2000
    )
    value = content() if arm == "C" else b_fixture(SPEC)
    template = value["paragraphs"][0]
    value["paragraphs"] = [dict(template, key=f"p{i}", text=text) for i in range(8)]
    for question in value["questions"].values():
        question.update(stem=text, explanation=text)
    catalog = c.make_catalog(SPEC)
    course = artifact.assemble(
        value,
        c.identity("dev", "max", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    body, binding = review.review_body(course, catalog)
    docs = course["source"]["documents"]
    assert len(docs["documents"]) == 16 and len(docs["references"]) == 1
    assert sum(len(row["occurrences"]) for row in docs["documents"].values()) == 3840
    assert len(body) <= policy.POLICY.request_bytes
    print(f"{arm}: {len(body)} bytes, {len(binding['targets'])} targets")


def test_dense_short_references_expose_unsupported_capacity():
    from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

    text = "`a` " + ("[a] " * 985) + "\n\n[a]: https://a.test/"
    value = content()
    template = value["paragraphs"][0]
    value["paragraphs"] = [dict(template, key=f"p{i}", text=text) for i in range(8)]
    for question in value["questions"].values():
        question.update(stem=text, explanation=text)
    catalog = c.make_catalog(SPEC)
    course = artifact.assemble(
        value, c.identity("dev", "dense", "C", 0, SPEC, None), catalog
    )
    assert len(canonical(value)) < c.MAX_PAYLOAD
    assert (
        sum(
            len(row["occurrences"])
            for row in course["source"]["documents"]["documents"].values()
        )
        == 15760
    )
    assert len(canonical(course)) > policy.POLICY.request_bytes
    with pytest.raises(c.ContractError, match="REVIEW_REQUEST_SIZE"):
        review.review_body(course, catalog)
