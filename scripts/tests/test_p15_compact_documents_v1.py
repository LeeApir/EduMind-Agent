"""Reversible offline document projection tests."""

from copy import deepcopy

import pytest

from scripts.isolated_diagnostics import p15_compact_documents_v1 as compact
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_document_v1 as document
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical


def test_nested_empty_unicode_and_unused_references_round_trip():
    value = document.build(
        {
            "one": '😀 `x` [甲"乙][a] ![](a) [](a)\n\n[a]: https://example.test/a "title"\n\n[unused]: https://other.test',
            "two": "> `b` [甲][a]\n\n[a]: https://another.test",
        }
    )
    packed = compact.pack(value)
    assert compact.unpack(packed) == value
    assert len(packed["references"]) == len(value["references"])


@pytest.mark.parametrize("change", ["reference", "original", "index", "missing"])
def test_tampering_is_rejected(change):
    value = document.build({"one": "`x` [a](https://example.test)"})
    packed = deepcopy(compact.pack(value))
    if change == "reference":
        packed["references"][0]["url"] += "evil"
    elif change == "original":
        packed["documents"]["one"]["original"] += "x"
    elif change == "index":
        packed["documents"]["one"]["tokens"][0]["children"][-1]["reference_index"] = 999
    else:
        packed["documents"].clear()
    with pytest.raises(c.ContractError):
        compact.unpack(packed)


def test_dense_occurrences_reduce_size_and_are_lossless():
    text = ("> " * 20) + ("[]()" * 990)
    value = document.build({f"d{i}": text for i in range(16)})
    packed = compact.pack(value)
    assert compact.unpack(packed) == value
    assert sum(len(row["occurrences"]) for row in value["documents"].values()) == 15840
    assert len(canonical(packed)) < len(canonical(value))
    print(
        f"documents original={len(canonical(value))} bytes; packed={len(canonical(packed))}"
    )


def test_conflicting_shadow_reference_is_not_silently_discarded():
    value = document.build({"one": "[a](https://example.test)"})
    packed = compact.pack(value)
    packed["documents"]["one"]["tokens"][0]["children"][0]["reference_id"] = (
        "ref_FORGED"
    )
    with pytest.raises(c.ContractError, match="COMPACT_DOCUMENT_CANONICAL"):
        compact.unpack(packed)


def test_lossless_unpack_does_not_imply_model_saw_original_ancestor_target():
    value = document.build({"one": "[hi](https://example.test)"})
    packed = compact.pack(value)
    original_ancestor = canonical(value["documents"]["one"])
    visible_ancestor = canonical(packed["documents"]["one"])
    assert original_ancestor != visible_ancestor
    assert (
        b'"occurrences"' in original_ancestor
        and b'"occurrences"' not in visible_ancestor
    )
    assert compact.unpack(packed) == value
