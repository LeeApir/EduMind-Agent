"""Offline guardrails for the unwired prompt candidate and existing contract."""

from copy import deepcopy
import json
import socket

import pytest

from scripts.isolated_diagnostics import p15_clean_pilot_prompts as clean
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as old


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("network forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def test_candidate_does_not_change_old_runtime_or_inherit_old_version():
    snapshot = json.loads(
        (c.ROOT / "docs/acceptance/phase-1.5-minimal-output-adapter-r01/prompt-snapshot.json").read_text()
    )
    assert old.PROMPT_VERSION == snapshot["version"]
    assert old.INSTRUCTIONS == snapshot["instructions"]
    assert clean.PROMPT_VERSION != old.PROMPT_VERSION
    assert set(clean.INSTRUCTIONS) == {"C_plan", "C_content", "C_repair", "B_generate", "B_repair", "review"}
    assert c.identity("run", "slot", "B", 0, spec(), None)["prompt_version"] == old.PROMPT_VERSION


def spec():
    return json.loads((c.DESIGN / "context-example.json").read_text())["spec"]


def example(name):
    cases = json.loads((c.DESIGN / "examples.json").read_text())["cases"]
    return deepcopy(next(row["payload"] for row in cases if row["id"] == name))


def test_new_review_instructions_avoid_legacy_field_override():
    review = clean.INSTRUCTIONS["review"]
    for obsolete in ("source_sha256", "source_pointer", "scope_status", "uncertain_reason", "reject", "uncertain"):
        # uncertainty is a current field; match legacy names as whole words.
        import re
        assert re.search(r"\b" + obsolete + r"\b", review) is None
    for current in ("candidate_id", "target_id", "evidence_quote", "uncertainty", "unknown"):
        assert current in review
    assert "coverage" in clean.INSTRUCTIONS["C_plan"]
    assert "do not return\ncoverage" in clean.INSTRUCTIONS["C_plan"]


def test_valid_fact_reference_does_not_validate_its_explanation():
    catalog = c.make_catalog(spec())
    content = example("positive_C_content")
    content["paragraphs"][0]["text"] = "Deliberately false teaching statement."
    c.validate("C_content", content, catalog=catalog)
    artifact = c.assemble(content, c.identity("run", "slot", "C", 0, spec(), None), catalog)
    assert artifact["raw_output"]["paragraphs"][0]["text"] == "Deliberately false teaching statement."


def test_baseline_wrong_answer_preserved_and_missing_answer_rejected():
    value = example("positive_B_generate")
    value["answers"]["caller_head"] = "none"
    c.validate("B_generate", value)
    result = c.assemble(value, c.identity("run", "slot", "B", 0, spec(), None))
    assert result["raw_output"]["answers"]["caller_head"] == "none"
    assert result["source"]["provenance"]["answers"] == "model"
    del value["answers"]["caller_head"]
    with pytest.raises(c.ContractError):
        c.validate("B_generate", value)


def test_review_quote_must_belong_to_the_current_target():
    content = example("positive_C_content")
    catalog = c.make_catalog(spec())
    artifact = c.assemble(content, c.identity("run", "slot", "C", 0, spec(), None), catalog)
    binding = c.make_binding(artifact)
    target, entry = next((k, v) for k, v in binding["targets"].items() if v["path"] == "/raw_output/paragraphs/0/text")
    review = dict(candidate_id=binding["candidate_id"], verdict="revise", uncertainty="", issues=[dict(severity="minor", area="difficulty", target_id=target, evidence_quote=entry["text"][:1], reason="Review suggestion")])
    c.validate("review_C", review, binding=binding)
    review["issues"][0]["evidence_quote"] = "NOT_IN_THE_TARGET_7a95"
    with pytest.raises(c.ContractError, match="QUOTE_BINDING"):
        c.validate("review_C", review, binding=binding)
