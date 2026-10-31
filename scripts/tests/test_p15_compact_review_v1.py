"""Compressed wire is a separate offline experiment, never a real call."""

from copy import deepcopy

import pytest

from scripts.isolated_diagnostics import p15_compact_review_v1 as compact
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact
from scripts.isolated_diagnostics import p15_review_path_v2 as policy
from scripts.tests.test_p15_combined_candidate_contract import response
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC


@pytest.mark.parametrize("arm", ["B", "C"])
def test_wire_alias_maps_to_original_target_and_exact_quote(arm):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    value["paragraphs"][0]["text"] = (
        '`c` [甲"乙][a] [甲"乙][a]\n\n[a]: https://example.test'
    )
    course = artifact.assemble(
        value,
        c.identity("dev", "slot", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    body, binding, local = compact.build(course, catalog)
    key = next(key for key, row in binding["targets"].items() if row["text"] == '甲"乙')
    alias = next(
        alias for alias, original in local["aliases"].items() if original == key
    )
    opinion = dict(
        candidate_id=binding["candidate_id"],
        verdict="revise",
        uncertainty="",
        issues=[
            dict(
                severity="minor",
                area="difficulty",
                target_id=alias,
                evidence_quote='甲"乙',
                reason="补充说明。",
            )
        ],
    )
    original, translated, observation = compact.observe(
        body, response(body, opinion), binding, local, policy.reservation(body)
    )
    assert original == opinion and translated["issues"][0]["target_id"] == key
    assert observation["semantic_pass"] is False
    altered = deepcopy(local)
    altered["aliases"][alias] = "invalid"
    with pytest.raises(c.ContractError, match="REVIEW_REQUEST_BINDING"):
        compact.observe(
            body, response(body, opinion), binding, altered, policy.reservation(body)
        )


def test_dense_references_remain_a_capacity_gate_not_silently_sampled():
    text = "[](a)" * 800
    value = content()
    paragraph = value["paragraphs"][0]
    value["paragraphs"] = [dict(paragraph, key=f"p{i}", text=text) for i in range(8)]
    for question in value["questions"].values():
        question.update(stem=text, explanation=text)
    catalog = c.make_catalog(SPEC)
    course = artifact.assemble(
        value, c.identity("dev", "dense", "C", 0, SPEC, None), catalog
    )
    raised = policy.Policy(request_bytes=100_000_000)
    body, binding, local = compact.build(course, catalog, raised)
    print(
        f"compact dense request={len(body)} bytes; all {len(binding['targets'])} targets retained"
    )
    assert len(local["aliases"]) == len(binding["targets"])
    # This measured case is evidence only; it is not a proof of 4 MiB coverage.


def test_maximum_density_development_size_round_trip_not_provider_readiness():
    from scripts.isolated_diagnostics import p15_compact_documents_v1 as docs
    from scripts.isolated_diagnostics import p15_pilot_wire as wire
    from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

    text = ("> " * 20) + ("[]()" * 990)
    value = content()
    template = value["paragraphs"][0]
    value["paragraphs"] = [dict(template, key=f"p{i}", text=text) for i in range(8)]
    for question in value["questions"].values():
        question.update(stem=text, explanation=text)
    catalog = c.make_catalog(SPEC)
    course = artifact.assemble(
        value, c.identity("dev", "max", "C", 0, SPEC, None), catalog
    )
    body, binding, local = compact.build(
        course, catalog, policy.Policy(request_bytes=100_000_000)
    )
    body_object = wire.strict_json(body)
    payload = wire.strict_json(body_object["input"][1]["content"])
    original = payload["artifact"]["source"]["documents"]
    packed = docs.pack(original)
    assert docs.unpack(packed) == original
    payload["artifact"]["source"]["documents"] = packed
    body_object["input"][1]["content"] = canonical(payload).decode()
    reduced = canonical(body_object)
    assert len(reduced) < len(body)
    assert len(local["aliases"]) == len(binding["targets"])
    print(
        f"dense: targets-only={len(body)} bytes, reversible-document-experiment={len(reduced)} bytes; targets={len(binding['targets'])}"
    )
