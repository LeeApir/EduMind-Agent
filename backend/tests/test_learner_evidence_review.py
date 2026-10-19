"""Actual request projection and scripted verdict routing; no model accuracy claim."""

import asyncio
import json
from copy import deepcopy

import pytest
from test_hybrid_resource_review import ReviewGateway, answer
from test_resource_review_responsibilities import resource_request
from test_review_input import fixture

from app.agents.hybrid_resource_review import INSTRUCTION, review_once
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import digest
from app.services.learning_policy import POLICY


@pytest.mark.parametrize(
    "goal,text,verdict,gap",
    [
        ("学习求和循环", "正确的一般教学，没有学生个性化判断。", "pass", None),
        (
            "刚学完结构体和指针，学习求和循环",
            "你自述刚学过指针；需要时可复习先修知识。",
            "pass",
            None,
        ),
        (
            "学习求和循环",
            "你经常混淆二级指针。",
            "needs_human",
            "缺少支持该具体困难归因的证据，须改为一般提醒或补证据。",
        ),
        (
            "学习求和循环",
            "你已经熟练掌握指针。",
            "needs_human",
            "学习经历不能证明熟练掌握，须修改无据个性化陈述。",
        ),
        ("没学过指针，学习求和循环", "你说已经学过指针。", "revise", None),
        (
            "学习求和循环",
            "你可保证跳过所有指针基础，已具备后续所需能力。",
            "needs_human",
            "具体跳过结论依赖未知的先修能力，不能保证该学习者已满足条件。",
        ),
    ],
)
def test_bound_original_background_and_personalization_rules(goal, text, verdict, gap):
    w, _ = fixture(user_goal=goal, false_claim=text)
    c = w.candidates()[0]
    expected = answer(verdict)
    if gap:
        expected["unresolved"] = [gap]
    g = ReviewGateway([expected])
    record = asyncio.run(
        review_once(
            g,
            CallWindow(),
            binding=w.binding,
            target_digest=c.content_digest,
            payload=resource_request(w, c, learner_review_context={"self_report_is_mastery": True}),
            candidates=(c,),
            input_snapshot=w.input_snapshot,
        )
    )
    sent = json.loads(g.requests[0].prompt.messages[1].content)
    context = sent["learner_review_context"]
    assert not context["self_report_is_mastery"] and not context["unknown_alone_blocks_publication"]
    assert context["unsupported_personalization_requires_resolution"]
    assert (
        sent["candidate"] == c.payload()
        and text in sent["candidate"]["envelope"]["content"]["markdown"]
    )
    assert sent["authoritative_teaching_goal"]["user_request"] == goal
    assert record["result"] == expected and record["local_routing"]["verdict"] == verdict
    assert "learner_fit" in record["result"]["coverage"]["checked"]
    assert POLICY["learner_review"] == context["version"]
    assert "Unknown does not imply false" in INSTRUCTION
    if gap:
        assert not expected["findings"]


def test_conflicting_bound_sources_are_both_kept_without_silent_merge():
    w, _ = fixture()
    w.input_snapshot["learner_evidence"] = {"self_report": "熟悉指针"}
    w.input_snapshot["reference_context"]["learner_evidence"] = {"quiz": "指针题连续错误"}
    w.reference_context = deepcopy(w.input_snapshot["reference_context"])
    w.binding["input_digest"] = digest("input", "learning-input-v1", snapshot=w.input_snapshot)
    c = w.stage("explanation", w.candidates()[0].envelope)
    g = ReviewGateway([answer("needs_human")])
    asyncio.run(
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
    context = json.loads(g.requests[0].prompt.messages[1].content)["learner_review_context"]
    assert context["evidence"] == {
        "input_snapshot": {"self_report": "熟悉指针"},
        "reference_context": {"quiz": "指针题连续错误"},
    }
    assert set(context["source"]) == set(context["evidence"])


def test_unbound_reference_cannot_mint_learner_authority():
    w, _ = fixture()
    del w.input_snapshot["reference_context"]
    w.reference_context["learner_evidence"] = {"mastery": "expert"}
    w.binding["input_digest"] = digest("input", "learning-input-v1", snapshot=w.input_snapshot)
    c = w.stage("explanation", w.candidates()[0].envelope)
    g = ReviewGateway([answer()])
    asyncio.run(
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
    sent = json.loads(g.requests[0].prompt.messages[1].content)
    assert sent["learner_review_context"]["evidence"] == {}
    assert sent["reference_context"]["learner_evidence"] == {}
