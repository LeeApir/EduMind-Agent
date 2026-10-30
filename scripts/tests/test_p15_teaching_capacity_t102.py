"""Development-only capacity probes; fixtures are neither model output nor evaluation truth."""

from copy import deepcopy

import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as contract
from scripts.isolated_diagnostics import p15_review_engineering as review
from scripts.isolated_diagnostics import p15_teaching_revision as teaching
from scripts.tests.test_p15_minimal_pilot import b_fixture, content


SPEC = {
    "version": "head-insertion-spec-v1",
    "initial_values": [10, 20, 30],
    "insert_values": [1, 2, 3, 4],
    "variant": "normal",
    "allocation_success": [True, True, True, True],
}


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize("length", [120, 600])
@pytest.mark.parametrize("revision", [0, 1])
def test_long_supported_development_case_exceeds_frozen_review_limit(
    monkeypatch, arm, length, revision
):
    catalog = contract.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    template = value["paragraphs"][0]
    value["paragraphs"] = [
        dict(template, key=f"p{i}", text="学" * length) for i in range(8)
    ]
    for question in value["questions"].values():
        question.update(stem="问" * length, explanation="答" * length)
    if revision:
        value["paragraphs"][0]["text"] += "修订"
    contract.validate(
        "C_repair" if arm == "C" and revision else
        "C_content" if arm == "C" else
        "B_repair" if revision else "B_generate",
        value,
        catalog=catalog if arm == "C" else None,
    )
    ident = contract.identity(
        "development", "capacity", arm, revision, SPEC, "a" * 64 if revision else None
    )
    artifact = contract.assemble(value, ident, catalog if arm == "C" else None)
    with pytest.raises(contract.ContractError, match="REVIEW_REQUEST_SIZE"):
        teaching.review_body(artifact, catalog)

    # Diagnostic measurement only. This does not alter or approve frozen policy.
    frozen = deepcopy(review.POLICY)
    monkeypatch.setattr(review, "POLICY", review.ReviewPolicy(request_bytes=2_000_000))
    raw, binding = teaching.review_body(artifact, catalog)
    assert len(raw) > frozen.request_bytes
    assert binding["artifact"] == artifact
    print(f"{arm} revision={revision} length={length} bytes={len(raw)}")


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize(
    "variant,mask",
    [
        ("normal", [False, False, False, False]),
        ("normal", [True, False, True, False]),
        ("reversed_assignment", [True, True, True, True]),
        ("uninitialized_next", [True, True, True, True]),
        ("discard_return", [True, True, True, True]),
    ],
)
def test_maximum_spec_variants_and_escaped_chinese_preserve_review_body(
    monkeypatch, arm, variant, mask
):
    spec = dict(SPEC, variant=variant, allocation_success=mask)
    catalog = contract.make_catalog(spec)
    value = content() if arm == "C" else b_fixture(spec)
    value["paragraphs"][0]["text"] = ('中文"\\\n' * 120)
    contract.validate(
        "C_content" if arm == "C" else "B_generate",
        value,
        catalog=catalog if arm == "C" else None,
    )
    artifact = contract.assemble(
        value,
        contract.identity("development", "capacity", arm, 0, spec, None),
        catalog if arm == "C" else None,
    )
    monkeypatch.setattr(review, "POLICY", review.ReviewPolicy(request_bytes=2_000_000))
    raw, binding = teaching.review_body(artifact, catalog)
    assert binding["artifact"] == artifact
    print(f"{arm} variant={variant} mask={mask} bytes={len(raw)}")
