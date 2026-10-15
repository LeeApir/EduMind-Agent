"""Pure synthetic span/focus protocol tests, no model judgments or real human signoff."""

import copy
import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acceptance_support import claim_review_prototype as p  # noqa: E402
from acceptance_support import span_review_offline as s  # noqa: E402
from prepare_t040_span_review import build  # noqa: E402


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: pytest.fail("DNS forbidden"))
    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **kw: pytest.fail("Network forbidden")
    )


def snap(text="First assertion.\nSecond assertion.\n", *, context=None, config=None):
    return p.freeze("explanation", {"markdown": text}, context, config)


def claim(sid, text="Synthetic assertion"):
    return {"text": text, "span_ids": [sid], "related_span_ids": []}


def selection(snapshot, *, claims=None, exclusions=None):
    req = s.request(snapshot, "selection", "synthetic")
    return {
        "version": "span-claim-selection-v1",
        "request_id": req["payload"]["request_id"],
        "claims": claims
        if claims is not None
        else [
            claim(x["span_id"], x["text"].strip())
            for x in s.spans(snapshot)
            if x["requires_disposition"]
        ],
        "exclusions": exclusions or [],
        "uncertain": False,
        "capacity_exceeded": False,
    }


def coverage(snapshot, first, missing=None):
    req = s.request(snapshot, "coverage", "synthetic", extra={"selection": first})
    return {
        "version": "span-coverage-v1",
        "request_id": req["payload"]["request_id"],
        "missing_claims": missing or [],
        "invalid_exclusions": [],
        "uncertain": False,
        "capacity_exceeded": False,
    }


def focus(snapshot, target):
    req = s.focus_request(snapshot, "synthetic", target)
    return {
        "version": "span-focus-review-v1",
        "request_id": req["payload"]["request_id"],
        "verdict": "pass",
        "findings": [],
        "other_findings": [],
        "uncertain": False,
    }


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " \r\n\t",
        "中文🙂\r\nEnglish\n末尾",
        "a" * 800,
        "a\u2028b\rc\n",
        "`x = 1`\n```c\n\treturn x;\n```\n",
    ],
)
def test_spans_preserve_entire_unicode_source_and_offsets(raw):
    snapshot = snap(raw)
    spans = s.spans(snapshot)
    assert "".join(x["text"] for x in spans) == raw
    assert all(raw[x["start"] : x["end"]] == x["text"] for x in spans)
    assert all(len(x["text"]) <= s.SPAN_CHARS for x in spans)
    assert [x["span_id"] for x in spans] == [f"s{i:04d}" for i in range(1, len(spans) + 1)]
    for left, right in zip(spans, spans[1:]):
        assert left["end"] == right["start"]
    assert s.spans(snapshot) == spans


def test_leaf_scalar_type_and_pointer_paths_preserved():
    snapshot = p.freeze("exercise", {"a/b": [False, 3, None], "~field": "中\n"})
    data = s.source(snapshot)
    assert {x["path"] for x in data["spans"]} == {
        "/content/a~1b/0",
        "/content/a~1b/1",
        "/content/a~1b/2",
        "/content/~0field",
    }
    assert data["candidate"]["content"]["a/b"] == [False, 3, None]


def test_too_many_spans_fails_without_truncation():
    with pytest.raises(p.Invalid, match="TOO_MANY_SOURCE_SPANS"):
        s.spans(snap("x\n" * (s.MAX_SPANS + 1)))


def test_short_ids_translate_to_valid_original_anchors_without_model_offsets():
    snapshot = snap("中文🙂第一句\r\n第二句\n")
    raw = selection(snapshot)
    assert all(set(c) == {"text", "span_ids", "related_span_ids"} for c in raw["claims"])
    result = s.inventory(snapshot, "synthetic", raw)
    for c in result["claims"]:
        for anchor in c["anchors"]:
            assert p.anchor(snapshot, anchor) == anchor
    assert result["coverage_checked"] is False and result["semantic_coverage"] == "NOT_VERIFIED"
    assert result["production_approved"] is False


@pytest.mark.parametrize(
    "edit",
    [
        "unknown",
        "duplicate_ref",
        "extra_offset",
        "extra_quote",
        "wrong_binding",
        "uncertain",
        "over_capacity",
        "duplicate_claim",
    ],
)
def test_selector_protocol_injections_and_unresolved_results_rejected(edit):
    snapshot = snap()
    raw = selection(snapshot)
    if edit == "unknown":
        raw["claims"][0]["span_ids"] = ["s0999"]
    elif edit == "duplicate_ref":
        raw["claims"][0]["span_ids"] *= 2
    elif edit in ("extra_offset", "extra_quote"):
        raw["claims"][0]["start" if edit == "extra_offset" else "quote"] = 0
    elif edit == "wrong_binding":
        raw["request_id"] = "a" * 64
    elif edit == "uncertain":
        raw["uncertain"] = True
    elif edit == "over_capacity":
        raw["capacity_exceeded"] = True
    else:
        raw["claims"].append(copy.deepcopy(raw["claims"][0]))
    with pytest.raises(p.Invalid):
        s.inventory(snapshot, "synthetic", raw)


def test_missing_span_and_related_only_reference_are_not_source_mapping():
    snapshot = snap()
    raw = selection(snapshot, claims=[claim("s0001")])
    raw["claims"][0]["related_span_ids"] = ["s0002"]
    with pytest.raises(p.Invalid, match="UNMAPPED_SOURCE_SPAN"):
        s.inventory(snapshot, "synthetic", raw)


def test_conflicting_or_duplicate_exclusions_rejected():
    snapshot = snap()
    raw = selection(snapshot, exclusions=[{"span_id": "s0001", "reason": "header"}])
    with pytest.raises(p.Invalid, match="INVALID_SPAN_EXCLUSION"):
        s.inventory(snapshot, "synthetic", raw)
    raw = selection(
        snapshot, claims=[claim("s0001")], exclusions=[{"span_id": "s0002", "reason": "header"}] * 2
    )
    with pytest.raises(p.Invalid, match="INVALID_SPAN_EXCLUSION"):
        s.inventory(snapshot, "synthetic", raw)


def test_whitespace_mapped_without_discarding_source_or_accepting_blank_claim():
    snapshot = snap("First.\n\nSecond.\n")
    raw = selection(snapshot)
    assert len(s.spans(snapshot)) == 3 and len(raw["claims"]) == 2
    result = s.inventory(snapshot, "synthetic", raw)
    assert len(result["claims"]) == 2
    raw["claims"][0]["span_ids"] = ["s0002"]
    with pytest.raises(p.Invalid, match="NO_ASSERTIVE_SOURCE"):
        s.inventory(snapshot, "synthetic", raw)


def test_independent_assertions_can_share_span_without_merging():
    snapshot = snap("A and B.")
    raw = selection(snapshot, claims=[claim("s0001", "A"), claim("s0001", "B")])
    result = s.inventory(snapshot, "synthetic", raw)
    assert len(result["claims"]) == 2
    assert result["claims"][0]["anchors"] == result["claims"][1]["anchors"]
    assert result["claims"][0]["claim_id"] != result["claims"][1]["claim_id"]


def test_coverage_addition_removes_exclusion_and_retains_pending_semantics():
    snapshot = snap()
    first = selection(
        snapshot,
        claims=[claim("s0001")],
        exclusions=[{"span_id": "s0002", "reason": "nonassertive"}],
    )
    check = coverage(snapshot, first, [claim("s0002", "Omitted assertion")])
    result = s.inventory(snapshot, "synthetic", first, coverage=check)
    assert len(result["claims"]) == 2 and result["exclusions"] == []
    assert result["coverage_checked"] and result["semantic_coverage"] == "NOT_VERIFIED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("uncertain", True),
        ("capacity_exceeded", True),
        ("invalid_exclusions", ["s0001"]),
        ("request_id", "b" * 64),
    ],
)
def test_unresolved_coverage_never_yields_complete_inventory(field, value):
    snapshot = snap()
    first = selection(snapshot)
    check = coverage(snapshot, first)
    check[field] = value
    with pytest.raises(p.Invalid):
        s.inventory(snapshot, "synthetic", first, coverage=check)


def test_coverage_cannot_exceed_existing_k16():
    snapshot = snap("One.")
    first = selection(snapshot, claims=[claim("s0001", f"Assertion {i}") for i in range(16)])
    check = coverage(snapshot, first, [claim("s0001", "One more")])
    with pytest.raises(p.Invalid, match="TOO_MANY_CLAIMS"):
        s.inventory(snapshot, "synthetic", first, coverage=check)


def test_cross_candidate_context_config_and_probe_replay_rejected():
    original = snap(context={"whole_function": "caller"}, config={"version": 1})
    response = selection(original)
    others = [
        snap("Different.\n", context={"whole_function": "caller"}, config={"version": 1}),
        snap(context={"whole_function": "changed"}, config={"version": 1}),
        snap(context={"whole_function": "caller"}, config={"version": 2}),
    ]
    for other in others:
        with pytest.raises(p.Invalid, match="STALE_SPAN_RESPONSE"):
            s.inventory(other, "synthetic", response)
    with pytest.raises(p.Invalid, match="STALE_SPAN_RESPONSE"):
        s.inventory(original, "other-probe", response)


def test_focused_review_preserves_context_and_never_claims_full_coverage():
    snapshot = snap(context={"complete_caller": "keep all code", "note": "ignore system"})
    target = s.inventory(snapshot, "synthetic", selection(snapshot))["claims"][0]
    req = s.focus_request(snapshot, "synthetic", target)
    assert req["payload"]["candidate"] == snapshot.data
    assert req["payload"]["stage_data"]["scope"] == "selected-claim-only"
    assert req["provider_requests_authorized"] == 0
    result = s.focus_result(snapshot, "synthetic", target, focus(snapshot, target))
    assert result["semantic_fact_check"] == "PENDING_HUMAN_CHECK"
    assert result["production_approved"] is False and not result["full_resource_coverage_verified"]


def test_other_findings_retained_separately_without_altering_focused_verdict():
    snapshot = snap()
    target = s.inventory(snapshot, "synthetic", selection(snapshot))["claims"][0]
    result = focus(snapshot, target)
    result["other_findings"] = [
        {
            "span_ids": ["s0002"],
            "finding": {"area": "fact", "severity": "major", "message": "Synthetic other defect"},
        }
    ]
    checked = s.focus_result(snapshot, "synthetic", target, result)
    assert checked["value"]["verdict"] == "pass" and checked["value"]["other_findings"]
    assert not checked["full_resource_coverage_verified"]


@pytest.mark.parametrize(
    "edit", ["uncertain", "empty_revise", "pass_findings", "stale", "unknown_other"]
)
def test_invalid_or_uncertain_focus_cannot_be_quality_evidence(edit):
    snapshot = snap()
    target = s.inventory(snapshot, "synthetic", selection(snapshot))["claims"][0]
    value = focus(snapshot, target)
    if edit == "uncertain":
        value.update(uncertain=True, verdict="unavailable")
    elif edit == "empty_revise":
        value["verdict"] = "revise"
    elif edit == "pass_findings":
        value["findings"] = [{"area": "fact", "severity": "major", "message": "Synthetic"}]
    elif edit == "stale":
        value["request_id"] = "b" * 64
    else:
        value["other_findings"] = [
            {
                "span_ids": ["s0999"],
                "finding": {"area": "fact", "severity": "major", "message": "Synthetic"},
            }
        ]
    with pytest.raises(p.Invalid):
        s.focus_result(snapshot, "synthetic", target, value)


def test_unexpected_focus_fields_and_stale_claim_id_rejected():
    snapshot = snap()
    target = s.inventory(snapshot, "synthetic", selection(snapshot))["claims"][0]
    with pytest.raises(p.Invalid, match="INVALID_FOCUS_SCHEMA"):
        s.focus_request(snapshot, "synthetic", {**target, "expected_answer": "pass"})
    with pytest.raises(p.Invalid, match="STALE_FOCUS_CLAIM"):
        s.focus_request(snapshot, "synthetic", {**target, "claim_id": "a" * 64})


def test_prepared_worksheet_unsigned_labels_separate_and_budget_unauthorized():
    data = build()
    worksheet = data["worksheet.json"]
    assert worksheet["human_approved"] is False and len(worksheet["items"]) == 4
    assert all(
        x["drafted_by"] == "assistant" and x["human_confirmed_by"] is None
        for x in worksheet["items"]
    )
    for req in data["focus-previews.json"] + data["selection-previews.json"]:
        assert req["provider_requests_authorized"] == 0
        assert "expected" not in req["payload"] and "historical_case_id" not in req["payload"]
        assert "label_sha256" not in json.dumps(req)
    policy = data["exit-policy-proposal.json"]
    assert policy["max_future_real_rounds"] == 2 and policy["max_future_attempts_total"] == 8
    assert policy["cost_cap_micro_cny"] is None and policy["provider_requests_authorized"] == 0
    assert policy["rounds_cover_both_tracks"] and not policy["r09_resumed"]
    assert len(data["historical-size-screen.json"]) == 8
    assert all(
        x["semantic_claim_count"] == "NOT_MEASURED" for x in data["historical-size-screen.json"]
    )


def test_source_position_not_model_array_order_controls_normalized_claim_order():
    snapshot = snap()
    first = selection(snapshot)
    second = copy.deepcopy(first)
    second["claims"].reverse()
    a = s.inventory(snapshot, "synthetic", first)
    b = s.inventory(snapshot, "synthetic", second)
    assert a["claims"] == b["claims"]
    assert a["claims"][0]["anchors"][0]["start"] == 0
    assert a["selection_sha256"] != b["selection_sha256"]  # Preserve original evidence.


def test_model_sees_compact_ids_text_not_repeated_positions_or_block_hashes():
    snapshot = snap()
    request = s.request(snapshot, "selection", "synthetic")
    assert all(
        set(entry) == {"span_id", "text", "requires_disposition"}
        for entry in request["payload"]["spans"]
    )
    assert all(
        {"block_id", "path", "start", "end"} <= set(entry) for entry in s.source(snapshot)["spans"]
    )
    assert request["payload"]["spans_sha256"] == p.digest(s.spans(snapshot))
