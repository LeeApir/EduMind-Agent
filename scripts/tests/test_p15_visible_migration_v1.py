"""Offline per-target migration, not proof of HTTP provenance."""

from copy import deepcopy

import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact
from scripts.isolated_diagnostics import p15_reference_review_v1 as old_review
from scripts.isolated_diagnostics import p15_visible_migration_v1 as migration
from scripts.isolated_diagnostics import p15_visible_review_view_v1 as visible
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize("with_reference", [False, True])
def test_each_old_target_is_reported_and_program_checks_are_truthfully_marked(
    arm, with_reference
):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    if with_reference:
        value["paragraphs"][0]["text"] = (
            "`c` [甲][a] [](x)\n\n[a]: https://example.test '甲\"乙'"
        )
    course = artifact.assemble(
        value,
        c.identity("dev", "slot", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    report = migration.build(course, catalog)
    old = old_review.make_binding(course)
    view, binding = visible.build(course, catalog)
    assert {row["old_id"] for row in report["targets"]} == set(old["targets"])
    assert all(row["visible_ids"] or row["program_checks"] for row in report["targets"])
    assert report["checks"]["RECEIPT_AND_PARENT_CHAIN"] == "pending_controlled_http"
    assert all(
        short in binding["paths"]
        for row in report["targets"]
        for short in row["visible_ids"]
    )
    assert len(view["cells"]) == len(binding["paths"])
    if with_reference:
        rows = [
            row
            for row in report["targets"]
            if row["old_path"].startswith("/source/documents/references/ref_")
        ]
        assert len(rows) == 2
        assert all(len(row["visible_ids"]) == 3 for row in rows)


def test_wrong_artifact_does_not_produce_migration_report():
    catalog = c.make_catalog(SPEC)
    course = artifact.assemble(
        content(), c.identity("dev", "slot", "C", 0, SPEC, None), catalog
    )
    course = deepcopy(course)
    course["source"]["blocks"][0]["document"] = "forged"
    with pytest.raises(c.ContractError):
        migration.build(course, catalog)


def test_document_ancestor_maps_used_and_unused_definitions_without_cross_document_mix():
    catalog = c.make_catalog(SPEC)
    value = content()
    value["paragraphs"][0]["text"] = (
        "`c` [link][a]\n\n[a]: https://one.test\n[unused]: https://unused.test"
    )
    second = deepcopy(value["paragraphs"][0])
    second.update(key="second", text="`c` [z][b]\n\n[b]: https://two.test")
    value["paragraphs"].append(second)
    course = artifact.assemble(
        value, c.identity("dev", "slot", "C", 0, SPEC, None), catalog
    )
    report = migration.build(course, catalog)
    view, binding = visible.build(course, catalog)
    doc = course["source"]["documents"]["documents"]["paragraph:intro"]
    expected_refs = {row["reference_id"] for row in doc["occurrences"]} | {
        row["reference_id"] for row in doc["declared_references"].values()
    }
    other_refs = set(course["source"]["documents"]["references"]) - expected_refs
    row = next(
        row
        for row in report["targets"]
        if row["old_path"] == "/source/documents/documents/paragraph:intro"
    )
    mapped = {binding["paths"][short]["pointer"] for short in row["visible_ids"]}
    assert all(
        f"/source/documents/references/{ref}/url" in mapped for ref in expected_refs
    )
    assert all(
        f"/source/documents/references/{ref}/url" not in mapped for ref in other_refs
    )
    assert all(
        short in {cell["id"] for cell in view["cells"]} for short in row["visible_ids"]
    )


def test_occurrence_kind_does_not_alias_equal_label_quote():
    catalog = c.make_catalog(SPEC)
    value = content()
    value["paragraphs"][0]["text"] = "`c` [link](https://example.test)"
    course = artifact.assemble(
        value, c.identity("dev", "slot", "C", 0, SPEC, None), catalog
    )
    old = old_review.make_binding(course)
    ids = {row["path"]: key for key, row in old["targets"].items()}
    prefix = "/source/documents/documents/paragraph:intro/occurrences/0"
    assert (
        migration.classify_quote(course, catalog, ids[prefix + "/label"], "link")[
            "status"
        ]
        == "visible"
    )
    assert (
        migration.classify_quote(course, catalog, ids[prefix + "/kind"], "link")[
            "status"
        ]
        == "program_only"
    )


def test_shared_fact_digest_is_program_only_not_a_quote_from_parent():
    catalog = c.make_catalog(SPEC)
    course = artifact.assemble(
        content(), c.identity("dev", "slot", "C", 0, SPEC, None), catalog
    )
    old = old_review.make_binding(course)
    targets = [
        (identifier, row)
        for identifier, row in old["targets"].items()
        if row["path"].endswith("/example_digest") and "/resolved_facts/" in row["path"]
    ]
    assert len(targets) >= 2
    assert len({row["text"] for _, row in targets}) == 1
    for identifier, row in targets:
        assert (
            migration.classify_quote(course, catalog, identifier, row["text"])["status"]
            == "program_only"
        )
