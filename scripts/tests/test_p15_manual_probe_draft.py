"""Safety and binding checks for synthetic-only, non-executable role drafts."""

from copy import deepcopy
import gzip
import json

import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as contract
from scripts.isolated_diagnostics import p15_synthetic_fixtures_v1 as fixtures
from scripts.isolated_diagnostics import p15_visible_request_budget_v1 as budget
from scripts.isolated_diagnostics import p15_visible_review_view_v1 as review
from scripts.isolated_diagnostics import prepare_p15_manual_probe_draft as draft
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical


def test_all_roles_use_versioned_instructions_and_b_has_no_engine_reference():
    bodies, index = draft.build()
    assert index["status"] == "development_only_not_execution_package"
    assert index["real_provider_calls"] == 0
    assert list(bodies) == [f"S{i}" for i in range(1, 8)]
    for item in index["requests"]:
        body = json.loads(bodies[item["slot"]])
        payload = json.loads(body["input"][1]["content"])
        assert payload["protocol_fixture_only"] is True
        assert payload["candidate_role_instruction_data"] == budget.instruction(item["stage"])[0]
        assert body["text"]["format"]["schema"] == contract.schema_for(item["stage"])
        assert body["stream"] is False and body["store"] is False
        assert len(bodies[item["slot"]]) <= draft.REQUEST_BYTES_LIMIT
        if item["stage"] in ("B_generate", "B_repair"):
            role_input = payload["role_input"]
            original = role_input if item["stage"] == "B_generate" else role_input["original_input"]
            assert set(original) == {
                "spec", "semantics", "goals", "question_definitions", "node_id_conventions"
            }


@pytest.mark.parametrize(("slot", "arm"), [("S6", "B"), ("S7", "C")])
def test_review_echo_quotes_are_bound_to_the_actually_supplied_view(slot, arm):
    bodies, _ = draft.build()
    body = json.loads(bodies[slot])
    payload = json.loads(body["input"][1]["content"])
    archive = json.loads(gzip.decompress(draft.ARCHIVE.read_bytes()))
    catalog = contract.make_catalog(archive["package"]["slots"][0]["spec"])
    candidate = archive["results"][arm]["versions"][0]
    expected_view, binding = review.build(candidate, catalog)
    assert payload["role_input"] == expected_view
    opinion = payload["expected_output"]
    assert opinion["issues"]
    review.validate_review(opinion, canonical(expected_view), candidate, catalog, binding)
    bad = deepcopy(opinion)
    bad["issues"][0]["evidence_quote"] = "__quote_absent_from_the_visible_text__"
    with pytest.raises(contract.ContractError, match="QUOTE_BINDING"):
        review.validate_review(bad, canonical(expected_view), candidate, catalog, binding)


def test_non_synthetic_archive_is_rejected(tmp_path, monkeypatch):
    source = json.loads(gzip.decompress(draft.ARCHIVE.read_bytes()))
    source["real_provider_calls"] = 1
    replacement = tmp_path / "not-synthetic.json.gz"
    replacement.write_bytes(gzip.compress(canonical(source)))
    monkeypatch.setattr(draft, "ARCHIVE", replacement)
    with pytest.raises(contract.ContractError, match="SYNTHETIC_ARCHIVE"):
        draft.build()


def synthetic_reply(request):
    body = json.loads(request)
    payload = json.loads(body["input"][1]["content"])
    reply = fixtures.envelope(body, payload["expected_output"])
    reply["text"] = {"format": deepcopy(body["text"]["format"])}
    return reply


@pytest.mark.parametrize("slot", [f"S{i}" for i in range(1, 8)])
def test_complete_synthetic_echo_response_is_checked_against_its_exact_request(slot):
    bodies, _ = draft.build()
    reply = synthetic_reply(bodies[slot])
    observed = draft.observe_synthetic_echo(slot, bodies[slot], canonical(reply))
    assert observed["schema_payload_echo"] == "matched"
    assert observed["admission_decision"] == "not_evaluated"
    assert observed["provider_identity_verified"] is False
    assert observed["teaching_evaluated"] is False


def test_echo_rejects_missing_schema_echo_or_excess_reported_usage():
    bodies, _ = draft.build()
    reply = synthetic_reply(bodies["S1"])
    del reply["text"]
    with pytest.raises(contract.ContractError, match="DRAFT_SCHEMA_ECHO_UNKNOWN"):
        draft.observe_synthetic_echo("S1", bodies["S1"], canonical(reply))
    reply = synthetic_reply(bodies["S1"])
    reply["usage"]["output_tokens"] = 513
    reply["usage"]["total_tokens"] = reply["usage"]["input_tokens"] + 513
    with pytest.raises(contract.ContractError, match="DRAFT_USAGE_LIMIT"):
        draft.observe_synthetic_echo("S1", bodies["S1"], canonical(reply))


def test_echo_rejects_cross_slot_request_and_invisible_review_quote():
    bodies, _ = draft.build()
    with pytest.raises(contract.ContractError, match="DRAFT_REQUEST_BINDING"):
        draft.observe_synthetic_echo("S6", bodies["S7"], canonical(synthetic_reply(bodies["S7"])))
    reply = synthetic_reply(bodies["S6"])
    text = reply["output"][0]["content"][0]["text"]
    value = json.loads(text)
    value["issues"][0]["evidence_quote"] = "__not_in_the_sent_view__"
    reply["output"][0]["content"][0]["text"] = canonical(value).decode()
    with pytest.raises(contract.ContractError, match="QUOTE_BINDING"):
        draft.observe_synthetic_echo("S6", bodies["S6"], canonical(reply))


def test_echo_keeps_missing_instruction_reasoning_and_format_fields_unknown():
    bodies, _ = draft.build()
    reply = synthetic_reply(bodies["S6"])
    del reply["instructions"]
    del reply["reasoning"]
    reply["text"]["format"] = {"schema": reply["text"]["format"]["schema"]}
    observed = draft.observe_synthetic_echo("S6", bodies["S6"], canonical(reply))
    assert observed["instruction_echo"] == "unavailable"
    assert observed["reasoning_echo"] == "unavailable"
    assert set(observed["format_field_echo"].values()) == {"unavailable"}
    assert observed["admission_decision"] == "not_evaluated"
