"""Offline regressions for bounded cross-arm teaching revision."""

import json
import socket
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.isolated_diagnostics import p15_teaching_revision as t
from scripts.isolated_diagnostics import p15_clean_pilot_prompts as previous
from scripts.isolated_diagnostics import p15_bound_pilot as bound
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as pilot
from scripts.isolated_diagnostics import p15_review_engineering as review
from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    build_example,
    build_actions,
    validate_spec,
    SpecError,
)
from scripts.tests.test_p15_combined_candidate_contract import response
from scripts.tests.test_p15_minimal_pilot import content, SPEC


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("no network allowed")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.mark.parametrize("stage", c.STAGES)
def test_each_actual_role_request_has_same_rules_and_original_schema(stage):
    request = t.request_for(stage, {"synthetic": "data"})
    key = "review" if stage.startswith("review_") else stage
    assert (
        request.prompt.messages[0].content
        == previous.INSTRUCTIONS[key] + "\n" + t.RULES
    )
    assert request.json_schema == c.schema_for(stage)
    for text in (
        "Simplified Chinese",
        "reach NULL",
        "cycles or reaches an indeterminate pointer",
        "scope",
        "stack nodes",
        "abstract test assumption",
    ):
        assert text in request.prompt.messages[0].content
    assert request.prompt.messages[1].content == '{"synthetic":"data"}'


@pytest.mark.parametrize(
    "variant", ["normal", "reversed_assignment", "discard_return", "uninitialized_next"]
)
@pytest.mark.parametrize(
    "mask", [[True, True], [False, True], [True, False], [False, False]]
)
def test_revised_requests_cover_normal_failure_and_unknown_without_changing_engine(
    variant, mask
):
    spec = dict(
        SPEC,
        initial_values=[9],
        insert_values=[1, 2],
        variant=variant,
        allocation_success=mask,
    )
    example = build_example(spec)
    catalog = c.make_catalog(spec)
    assert example == catalog["example"]
    b = pilot.baseline_input(spec)
    assert set(b) == {
        "spec",
        "semantics",
        "goals",
        "question_definitions",
        "node_id_conventions",
    }
    assert "fact_catalog" not in b and "example" not in b
    plan = bound.plan_input(spec, catalog)
    request = t.request_for("C_plan", plan)
    assert json.loads(request.prompt.messages[1].content)["spec"] == spec
    actions = build_actions(example, "slot:code")
    assert all(a["anchor"] == "slot:code" for a in actions)
    if variant == "uninitialized_next" and any(mask):
        assert example["observation"]["traversal_status"] == "indeterminate"
    if variant == "reversed_assignment" and any(mask):
        assert example["observation"]["traversal_status"] == "cycle"
    if not any(mask):
        assert example["observation"]["allocation_failures"] == 2


@pytest.mark.parametrize(
    "mutation",
    [
        {"variant": "unknown"},
        {"initial_values": [1, 2, 3, 4]},
        {"insert_values": [1, 2, 3, 4, 5]},
        {"allocation_success": []},
    ],
)
def test_unsupported_specs_still_refuse_without_network(mutation):
    with pytest.raises(SpecError):
        validate_spec(dict(SPEC, **mutation))


def test_same_real_candidate_review_preserves_all_181_targets_and_new_rules():
    root = Path(__file__).resolve().parents[2]
    a = json.loads(
        (
            root
            / "docs/acceptance/phase-1.5-combined-candidate-r01/results/candidate.json"
        ).read_text()
    )
    catalog = c.make_catalog(old_spec())
    body, binding = t.review_body(a, catalog)
    request = json.loads(body)
    payload = json.loads(request["input"][1]["content"])
    assert request["input"][0]["content"] == t.instruction("review_C")
    assert payload["artifact"] == a and payload["reference"] == catalog["example"]
    assert len(binding["targets"]) == len(payload["target_catalog"]) == 181
    assert len(body) <= review.POLICY.request_bytes
    for k, row in binding["targets"].items():
        assert payload["target_catalog"][k] == {
            "path": row["path"],
            "text": row["text"],
        }
    opinion = dict(
        candidate_id=binding["candidate_id"],
        verdict="unknown",
        uncertainty="证据不足",
        issues=[],
    )
    value, obs = review.observe_review(body, response(body, opinion), binding)
    assert value == opinion and obs["semantic_pass"] is False


def old_spec():
    from scripts.isolated_diagnostics.p15_combined_candidate_contract import (
        SPEC as actual,
    )

    return deepcopy(actual)


def test_c_chinese_development_example_is_local_and_not_model_truth():
    value = content()
    value["paragraphs"][0]["text"] = "已知到达空指针时，这个例子的遍历完整结束。"
    catalog = c.make_catalog(SPEC)
    c.validate("C_content", value, catalog=catalog)
    assert value["paragraphs"][0]["text"] != content()["paragraphs"][0]["text"]
    assert t.PROMPT_VERSION != previous.PROMPT_VERSION


@pytest.mark.parametrize("arm", ["B", "C"])
def test_v3_compact_review_wire_validates_both_arms_and_rejects_cross_arm(arm):
    from scripts.tests.test_p15_minimal_pilot import b_fixture

    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    ident = c.identity("test", "slot", arm, 0, SPEC, None)
    ident["prompt_version"] = t.PROMPT_VERSION
    artifact = c.assemble(value, ident, catalog if arm == "C" else None)
    body, binding = t.review_body(artifact, catalog)
    opinion = dict(
        candidate_id=binding["candidate_id"], verdict="pass", uncertainty="", issues=[]
    )
    actual, obs = t.observe_review(body, response(body, opinion), binding)
    assert actual == opinion and not obs["semantic_pass"]
    other = deepcopy(binding)
    other["artifact"]["identity"]["arm"] = "B" if arm == "C" else "C"
    with pytest.raises(c.ContractError):
        t.observe_review(body, response(body, opinion), other)


def test_offline_draft_is_attributed_and_preserves_parent_code_answers_and_actions():
    from scripts.isolated_diagnostics import p15_teaching_draft as draft

    original = json.loads(draft.ORIGINAL.read_text())
    derived = draft.revise()
    assert derived["identity"]["parent_digest"] == original["artifact_digest"]
    assert derived["source"]["provenance"]["content"] == "assistant_offline_revision"
    assert derived["identity"]["prompt_version"] == "assistant-offline-wording-v1"
    assert derived["source"]["actions"] == original["source"]["actions"]
    assert derived["source"]["resolved_facts"] == original["source"]["resolved_facts"]
    assert [b for b in derived["source"]["blocks"] if b["kind"] == "code"] == [
        b for b in original["source"]["blocks"] if b["kind"] == "code"
    ]
    assert [
        b["answer_key"] for b in derived["source"]["blocks"] if b["kind"] == "question"
    ] == [
        b["answer_key"] for b in original["source"]["blocks"] if b["kind"] == "question"
    ]
    assert (
        "完整遍历结果"
        in derived["raw_output"]["questions"]["reachable_prefix"]["explanation"]
    )


def test_review_rejects_same_arm_different_revision_or_tampered_body():
    from scripts.isolated_diagnostics import p15_teaching_draft as draft

    original = json.loads(draft.ORIGINAL.read_text())
    derived = draft.revise()
    catalog = c.make_catalog(old_spec())
    body_a, _ = t.review_body(original, catalog)
    body_b, binding_b = t.review_body(derived, catalog)
    opinion = dict(
        candidate_id=binding_b["candidate_id"],
        verdict="pass",
        uncertainty="",
        issues=[],
    )
    with pytest.raises(c.ContractError, match="REVIEW_REQUEST_BINDING"):
        t.observe_review(body_a, response(body_a, opinion), binding_b)
    request = json.loads(body_b)
    payload = json.loads(request["input"][1]["content"])
    payload["target_catalog"].pop(next(iter(payload["target_catalog"])))
    request["input"][1]["content"] = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    altered = json.dumps(
        request, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    with pytest.raises(c.ContractError, match="REVIEW_REQUEST_BINDING"):
        t.observe_review(altered, response(altered, opinion), binding_b)


def test_chinese_question_states_unchanged_enum_tokens():
    from scripts.isolated_diagnostics import p15_teaching_draft as draft

    question = draft.revise()["raw_output"]["questions"]["traversal_status"]["stem"]
    assert all(token in question for token in ("terminated", "cycle", "indeterminate"))


@pytest.mark.parametrize("arm", ["B", "C"])
def test_review_rejects_reference_for_different_spec(arm):
    from scripts.tests.test_p15_minimal_pilot import b_fixture

    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    ident = c.identity("test", "slot", arm, 0, SPEC, None)
    artifact = c.assemble(value, ident, catalog if arm == "C" else None)
    other = c.make_catalog(dict(SPEC, initial_values=[-20]))
    with pytest.raises(c.ContractError, match="REVIEW_SPEC_BINDING"):
        t.review_body(artifact, other)
