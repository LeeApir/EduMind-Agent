"""Offline tests for isolated reference document representation."""

from copy import deepcopy

import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_document_v1 as d
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest


def test_repeated_reference_is_centralized_without_losing_source_or_locations():
    raw = "`a` " + ("[x][a] " * 240) + "\n\n[a]: https://a.test/" + "x" * 2000
    docs = {f"block_{i}": raw for i in range(9)}
    value = d.build(docs)
    assert len(value["references"]) == 1
    assert len(value["documents"]["block_0"]["occurrences"]) == 240
    assert all(value["documents"][key]["original"] == raw for key in docs)
    assert len(canonical(value)) < 4 * 1024 * 1024
    d.verify(value)


@pytest.mark.parametrize("change", ["missing", "wrong_target", "raw", "tokens"])
def test_recomputed_digest_does_not_hide_tampering(change):
    value = d.build({"one": "`code` [text][a]\n\n[a]: https://example.test/a"})
    value = deepcopy(value)
    if change == "missing":
        value["documents"]["one"]["occurrences"].clear()
    elif change == "wrong_target":
        value["documents"]["one"]["occurrences"][0]["reference_id"] = "forged"
    elif change == "raw":
        value["documents"]["one"]["original"] += "edited"
    else:
        value["documents"]["one"]["tokens"].clear()
    value["digest"] = digest({k: v for k, v in value.items() if k != "digest"})
    with pytest.raises(c.ContractError, match="DOCUMENT_BINDING"):
        d.verify(value)


def test_html_and_javascript_links_are_untrusted_data():
    value = d.build({"one": "<script>alert(1)</script>\n\n`c` [x](javascript:alert)"})
    assert "<script>" in value["documents"]["one"]["original"]
    assert list(value["references"].values())[0]["url"] == "javascript:alert"
    d.verify(value)


def test_unused_declared_reference_is_preserved_centrally():
    value = d.build({"one": '正文\n\n[unused]: https://example.test/doc "标题"'})
    declared = value["documents"]["one"]["declared_references"]["UNUSED"]
    assert value["references"][declared["reference_id"]] == {
        "url": "https://example.test/doc",
        "title": "标题",
    }
    assert value["documents"]["one"]["occurrences"] == []
    d.verify(value)


def test_scope_unicode_escapes_and_code_references_remain_distinct():
    one = "😀 e\u0301 `not [x][r]` [甲][r] \\[无]\\[r]\n\n[r]: https://example.test/a"
    two = "`b` [乙][r]\n\n[r]: https://example.test/b"
    value = d.build({"one": one, "two": two})
    assert value["documents"]["one"]["original"] == one
    assert value["documents"]["two"]["original"] == two
    assert len(value["references"]) == 2
    first = value["documents"]["one"]["occurrences"]
    second = value["documents"]["two"]["occurrences"]
    assert len(first) == 1 and len(second) == 1
    assert first[0]["reference_id"] != second[0]["reference_id"]
    for key, row in (("one", first[0]), ("two", second[0])):
        node = value["documents"][key]["tokens"]
        for depth, i in enumerate(row["path"]):
            node = node[i]
            if depth + 1 < len(row["path"]):
                node = node["children"]
        assert node["reference_id"] == row["reference_id"]
    d.verify(value)
