"""Offline artifact projection tests; no provider or hidden evaluation samples."""

from copy import deepcopy

import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as a
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC


@pytest.mark.parametrize("arm", ["B", "C"])
def test_artifact_retains_content_actions_answers_and_reconstructs(arm):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    value["paragraphs"][0]["text"] = "`code` [讲解][a]\n\n[a]: https://example.test/"
    ident = c.identity("dev", "slot", arm, 0, SPEC, None)
    artifact = a.assemble(value, ident, catalog if arm == "C" else None)
    a.verify(artifact, catalog)
    source = artifact["source"]
    first = source["blocks"][0]
    assert (
        source["documents"]["documents"][first["document"]]["original"]
        == value["paragraphs"][0]["text"]
    )
    assert len(source["documents"]["references"]) == 1
    assert len([b for b in source["blocks"] if b["kind"] == "question"]) == 4
    assert source["actions"]
    altered = deepcopy(artifact)
    altered["source"]["blocks"][0]["document"] = "forged"
    altered["artifact_digest"] = digest(
        {k: v for k, v in altered.items() if k != "artifact_digest"}
    )
    with pytest.raises(c.ContractError, match="ARTIFACT_RECONSTRUCTION"):
        a.verify(altered, catalog)


def test_reference_expansion_counterexample_does_not_use_legacy_assembler():
    text = "`a` " + ("[x][a] " * 240) + "\n\n[a]: https://a.test/" + "x" * 2000
    value = content()
    template = value["paragraphs"][0]
    value["paragraphs"] = [dict(template, key=f"p{i}", text=text) for i in range(8)]
    value["questions"]["caller_head"]["stem"] = text
    catalog = c.make_catalog(SPEC)
    artifact = a.assemble(value, c.identity("dev", "max", "C", 0, SPEC, None), catalog)
    assert len(canonical(artifact)) < 4 * 1024 * 1024
    assert len(artifact["source"]["documents"]["references"]) == 1
    a.verify(artifact, catalog)


def test_literal_template_markers_remain_content():
    from scripts.isolated_diagnostics.generate_p15_reference_player import build

    catalog = c.make_catalog(SPEC)
    value = content()
    value["paragraphs"][0]["text"] += " __QUESTIONS__ __PAYLOAD__ __DIGEST__"
    artifact = a.assemble(value, c.identity("dev", "slot", "C", 0, SPEC, None), catalog)
    rendered = build(artifact, catalog)
    assert "__QUESTIONS__ __PAYLOAD__ __DIGEST__" in rendered


def test_preview_states_are_bound_to_actual_catalog_and_refuses_b():
    import json
    import re

    from scripts.isolated_diagnostics.generate_p15_reference_player import build

    spec = dict(SPEC, allocation_success=[True, False, True, False])
    catalog = c.make_catalog(spec)
    course = a.assemble(
        content(), c.identity("dev", "slot", "C", 0, spec, None), catalog
    )
    page = build(course, catalog)
    data = json.loads(
        re.search(
            r'<script id="sample-data" type="application/json">(.*?)</script>', page
        ).group(1)
    )
    assert data["states"] == catalog["example"]["trace"]["steps"]
    assert data["actions"] == course["source"]["actions"]
    baseline = a.assemble(
        b_fixture(spec), c.identity("dev", "slot", "B", 0, spec, None), None
    )
    with pytest.raises(c.ContractError, match="PREVIEW_C_ONLY"):
        build(baseline, catalog)
