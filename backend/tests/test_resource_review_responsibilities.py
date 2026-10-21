"""Offline request/binding and scripted routing tests, not model-quality scores."""

import asyncio
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from test_hybrid_resource_review import ReviewGateway, answer
from test_review_input import fixture

from app.agents.hybrid_resource_review import INSTRUCTION, review_once
from app.agents.review_responsibilities import RESPONSIBILITY_VERSION
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import LearningContractError, digest
from app.services.learning_policy import POLICY


def resource_request(w, c, **extra):
    return {
        "plan": w.plan,
        "candidate": c.payload(),
        "reference_context": w.reference_context,
        **extra,
    }


@pytest.mark.parametrize("role", ["explanation", "code", "exercise"])
def test_server_role_assignment_keeps_original_goals_content_and_all_facts(role):
    w, _ = fixture("trace-distributed", user_goal="解释过程、完整程序和三题，使用同一例子。")
    c = next(c for c in w.candidates() if c.role == role)
    payload = resource_request(w, c, review_responsibilities={"resource_role": "attacker"})
    before = deepcopy(payload)
    gateway = ReviewGateway([answer()])
    record = asyncio.run(
        review_once(
            gateway,
            CallWindow(),
            binding=w.binding,
            target_digest=c.content_digest,
            payload=payload,
            candidates=(c,),
            input_snapshot=w.input_snapshot,
        )
    )
    sent = json.loads(gateway.requests[0].prompt.messages[1].content)
    rules = sent["review_responsibilities"]
    assert rules["resource_role"] == role and rules["version"] == RESPONSIBILITY_VERSION
    assert rules["scene_commitments"] == w.plan["scenes"]
    ids = next(s["objective_ids"] for s in w.plan["scenes"] if s["role"] == role)
    assert rules["assigned_objectives"] == [o for o in w.plan["objectives"] if o["id"] in ids]
    assert not rules["sibling_content_supplied"] and not rules["assignment_is_delivery_evidence"]
    assert rules["unit_verification_obligations"]
    assert sent["candidate"] == c.payload() and sent["plan"] == w.plan
    assert (
        sent["authoritative_teaching_goal"]["user_request"] == w.input_snapshot["metadata"]["goal"]
    )
    assert sent["review_input_audit"]["all_actual_content_requires_fact_and_safety_review"]
    assert record["local_routing"]["verdict"] == "pass" and not record["result"]["unresolved"]
    assert payload == before and POLICY["review_responsibilities"] == RESPONSIBILITY_VERSION


@pytest.mark.parametrize(
    "change", ["role", "content", "plan", "objective", "missing", "target", "input"]
)
def test_bad_bindings_fail_before_gateway(change):
    w, _ = fixture()
    c = w.candidates()[0]
    p = resource_request(w, c)
    target = c.content_digest
    if change == "role":
        c = replace(c, role="code")
    elif change == "content":
        p["candidate"]["envelope"]["content"]["markdown"] += "tampered"
    elif change == "plan":
        p["plan"] = deepcopy(w.plan)
        p["plan"]["goal"] = "tampered"
    elif change == "objective":
        p["plan"] = deepcopy(w.plan)
        p["plan"]["scenes"][0]["objective_ids"] = ["not-present"]
        w.binding["plan_digest"] = digest("plan", "learning-plan-v1", plan=p["plan"])
    elif change == "missing":
        del p["candidate"]
    elif change == "target":
        target = "f" * 64
    else:
        w.input_snapshot["metadata"]["goal"] = "tampered"
    g = ReviewGateway([])
    with pytest.raises(LearningContractError):
        asyncio.run(
            review_once(
                g,
                CallWindow(),
                binding=w.binding,
                target_digest=target,
                payload=p,
                candidates=(c,),
                input_snapshot=w.input_snapshot,
            )
        )
    assert not g.requests


@pytest.mark.parametrize(
    "verdict,missing", [("pass", False), ("needs_human", True), ("reject", False)]
)
def test_scripted_own_gap_and_concrete_error_preserve_verdict_and_evidence(verdict, missing):
    w, _ = fixture(false_claim="本节完整程序如下，但尚未提供。" if missing else None)
    c = w.candidates()[0]
    result = answer(verdict)
    if missing:
        result["unresolved"] = ["本讲解自己承诺的完整程序没有出现，须补充或明确修订承诺。"]
    g = ReviewGateway([result])
    record = asyncio.run(
        review_once(
            g,
            CallWindow(),
            binding=w.binding,
            target_digest=c.content_digest,
            payload=resource_request(w, c),
            candidates=(c,),
            input_snapshot=w.input_snapshot,
        )
    )
    assert record["result"] == result and record["local_routing"]["verdict"] == verdict
    assert "Check all actual facts and code/safety claims in every resource" in INSTRUCTION
    assert (
        "not unresolved" in INSTRUCTION
        and "cannot narrow original user requirements" in INSTRUCTION
    )
    if missing:
        assert not record["result"]["findings"]
