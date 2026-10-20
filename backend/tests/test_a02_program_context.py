"""Source/context integrity and existing routing only; mock verdicts are not semantic proof."""

import asyncio
import json
from copy import deepcopy

import pytest
from test_a01_process_generation import ROOT, actual_workspace
from test_hybrid_resource_review import ReviewGateway, answer
from test_review_input import fixture

from app.agents.hybrid_resource_review import UNIT_CHECKS, review_once, route_review
from app.agents.review_program_context import PROGRAM_CONTEXT_INSTRUCTION, program_context
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import LearningContractError
from app.services.teaching_actions import anchor_catalog, assemble_actions
from app.services.unit_material import unit_material


def material(w):
    scenes = [
        dict(
            role=c.role,
            scene_key=c.role,
            scene_id=c.id,
            scene_version=1,
            resource_id=c.id,
            resource_digest=c.content_digest,
            dependency_digest=c.dependency_digest,
        )
        for c in w.candidates()
    ]
    return unit_material(w, scenes, assemble_actions(w.candidates()))


def pointer(data, path):
    for key in path.strip("/").split("/"):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def send(w, verdict, *, role=None, gap=None):
    cs = w.candidates() if role is None else tuple(c for c in w.candidates() if c.role == role)
    m = material(w)
    value = answer(verdict, "unit" if role is None else "resource")
    if role is None:
        value["coverage"]["checked"] = sorted(UNIT_CHECKS)
    if gap:
        value["unresolved"] = [gap]
    g = ReviewGateway([value])
    payload = (
        {"unit": m, "reference_context": w.reference_context}
        if role is None
        else {
            "plan": w.plan,
            "candidate": cs[0].payload(),
            "reference_context": w.reference_context,
        }
    )
    record = asyncio.run(
        review_once(
            g,
            CallWindow(),
            binding=w.binding,
            target_digest=m["unit_digest"] if role is None else cs[0].content_digest,
            payload=payload,
            candidates=cs,
            scope="unit" if role is None else "resource",
            input_snapshot=w.input_snapshot,
        )
    )
    return record, json.loads(g.requests[0].prompt.messages[1].content), g.requests[0]


def test_a02_full_source_and_caller_are_located_without_invented_scope():
    w = actual_workspace("A02")
    record, data, request = send(w, "needs_human", gap="细化逐步状态测量不足；非指针事实错误。")
    context = data["program_context"]
    assert context["availability"] == "whole_unit_supplied"
    assert context["scope_or_call_relationship_inferred"] is False
    assert context["source_completeness_or_safety_certified"] is False
    assert len(context["code_source_fields"]) == 1
    source = context["code_source_fields"][0]
    text = pointer(data, source["content_pointer"])
    assert text == w.candidates()[1].envelope["content"]["source"]
    assert "void free_list(Node **head)" in text
    assert "*head = NULL" in text and "free_list(&head)" in text
    anchor = next(a for a in data["anchor_catalog"] if a["anchor_id"] == source["anchor_id"])
    assert anchor["resource_digest"] == source["resource_digest"]
    assert anchor["json_pointer"] == "/source"
    narrative = next(x for x in context["other_claim_fields"] if x["anchor_pointer"] == "/markdown")
    assert "Node *p = head;" in pointer(data, narrative["content_pointer"])
    assert PROGRAM_CONTEXT_INSTRUCTION in request.prompt.messages[0].content
    assert record["local_routing"]["verdict"] == "needs_human"
    assert not record["result"]["findings"]


def test_resource_only_fragment_has_no_fabricated_sibling_source():
    w = actual_workspace("A02")
    gap = "讲解释放片段未给出外围函数/形参及调用方，不能证明caller悬垂。"
    record, data, _ = send(w, "needs_human", role="explanation", gap=gap)
    assert data["program_context"]["availability"] == "selected_resource_only"
    assert data["program_context"]["code_source_fields"] == []
    assert "unit" not in data and data["candidate"]["role"] == "explanation"
    assert record["result"]["unresolved"] == [gap]
    assert record["local_routing"]["verdict"] == "needs_human"


def test_correct_complete_pointer_program_not_forced_to_unknown():
    w = actual_workspace("A02")
    record, data, _ = send(w, "pass", role="code")
    assert record["local_routing"]["verdict"] == "pass"
    assert pointer(data, data["program_context"]["code_source_fields"][0]["content_pointer"])


@pytest.mark.parametrize("name", ["trace-complete", "trace-distributed"])
def test_complete_and_distributed_controls_keep_full_content(name):
    w, _ = fixture(name)
    record, data, _ = send(w, "pass")
    assert record["local_routing"]["verdict"] == "pass"
    assert data["unit"]["candidates"] == [c.payload() for c in w.candidates()]


def test_real_reachable_bounds_error_stays_rejected_with_unknown_runtime_value():
    w, _ = fixture("trace-complete", unsafe_code=True)
    # The existing fact/severity policy still handles a concrete reachable violation.
    # Script the correctly grounded safety result, not a semantic evaluation by a mock.
    value = answer("reject", "unit")
    value["coverage"]["checked"] = sorted(UNIT_CHECKS)
    cat = anchor_catalog(w.candidates())
    aid = next(
        a["anchor_id"]
        for a in cat
        if a["resource_id"] == w.candidates()[1].id and a["json_pointer"] == "/source"
    )
    value["findings"] = [
        dict(
            category="code_safety",
            severity="severe",
            anchors=[aid],
            condition_or_counterexample="长度3数组在sum调用时访问a[4]，合法下标0..2。",
            impact="越界可达，不保证具体数值或正常返回。",
        )
    ]
    routed = route_review(value, scope="unit", catalog=cat)
    assert routed["verdict"] == "reject"


def test_bad_or_unlocated_index_metadata_is_rejected():
    w = actual_workspace("A02")
    m = material(w)
    cs = w.candidates()
    catalog = anchor_catalog(cs)
    bad = deepcopy(catalog)
    bad[0]["resource_digest"] = "f" * 64
    with pytest.raises(LearningContractError, match="REVIEW_PROGRAM_CONTEXT_UNBOUND"):
        program_context({"unit": m}, cs, bad)
    m["candidates"][0]["envelope"]["content"]["markdown"] += "tamper"
    with pytest.raises(LearningContractError, match="REVIEW_PROGRAM_CONTEXT_UNBOUND"):
        program_context({"unit": m}, cs, catalog)


def test_old_false_reject_is_preserved_not_silently_rewritten_by_schema_checks():
    data = json.loads(
        (
            ROOT / "docs/acceptance/phase-1-five-hour-remaining-six-r01/actual-results.json"
        ).read_text()
    )
    old = next(c for c in data["cases"] if c["case_id"] == "A02")
    review = next(r for r in old["reviews"] if r["result"]["scope"] == "unit")
    before = deepcopy(review["result"])
    assert (
        route_review(before, scope="unit", catalog=review["anchor_catalog"])["verdict"] == "reject"
    )
    assert before == review["result"]
    # Deliberately documents the limit: evidence semantics are not enforced by Schema.
    # We neither call a second judge nor silently downgrade a model's severe conclusion.
