"""Frozen target/advice/teaching choice and actual input capture, zero Provider."""

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_shared_learning_plan import DRAFT, Gateway, inputs

from app.agents.review_input import review_input
from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.learning_contract import LearningContractError, digest
from app.services.teaching_binding import select_teaching_context


def selection(mode="target", recommended="c-pointer"):
    graph = default_knowledge_graph_repository()
    owner = uuid4()
    path = SimpleNamespace(
        id=uuid4(),
        user_id=owner,
        target_node_id="linked-list-insertion",
        current_node_id=recommended,
        nodes=[{"node_id": n} for n in ["c-pointer", "linked-list-insertion"]],
        version=1,
        graph_version=graph.graph_version,
    )
    context = select_teaching_context(
        owner_id=owner,
        target_node_id="linked-list-insertion",
        original_request="为刚学完指针的初学者讲解单链表头插法，提供完整C程序和三题。",
        mode=mode,
        graph=graph,
        path=path,
    )
    return context, graph, owner, path


@pytest.mark.parametrize(
    "mode,node,scope",
    [
        ("target", "linked-list-insertion", "target_lesson"),
        ("recommended", "c-pointer", "prerequisite_segment"),
    ],
)
def test_choice_is_explicit_and_does_not_rewrite_path(mode, node, scope):
    c, _, _, p = selection(mode)
    assert c["teaching_node_id"] == node and c["segment_scope"] == scope
    assert c["recommended_node_id"] == p.current_node_id == "c-pointer"
    assert c["target_node_id"] == "linked-list-insertion"
    assert c["path_version_id"] == str(p.id)
    assert "刚学完指针" in c["original_request"]
    if mode == "target":
        assert c["segment_goal"] == c["original_request"]
    else:
        assert "原目标尚待后续完成" in c["segment_goal"]
    p.current_node_id = "linked-list-insertion"
    assert c["recommended_node_id"] == "c-pointer"


def test_recommended_target_keeps_full_original_goal():
    c, _, _, _ = selection("recommended", "linked-list-insertion")
    assert (
        c["selection_reason"] == "recommended_target" and c["segment_goal"] == c["original_request"]
    )


@pytest.mark.parametrize(
    "change", ["owner", "target", "graph", "missing", "foreign_node", "no_path"]
)
def test_invalid_recommendation_never_falls_back(change):
    c, g, o, p = selection()
    if change == "owner":
        p.user_id = uuid4()
    elif change == "target":
        p.target_node_id = "stack"
    elif change == "graph":
        p.graph_version = "different"
    elif change == "missing":
        p.current_node_id = None
    elif change == "foreign_node":
        p.current_node_id = "invented"
    else:
        p = None
    with pytest.raises(LearningContractError, match="TEACHING_SELECTION_UNAVAILABLE"):
        select_teaching_context(
            owner_id=o,
            target_node_id=c["target_node_id"],
            original_request=c["original_request"],
            mode="recommended",
            graph=g,
            path=p,
        )


@pytest.mark.parametrize("mode", ["target", "recommended"])
def test_generated_plan_and_review_keep_actual_topic_and_original_request_separate(mode):
    c, g, _, _ = selection(mode)
    i = inputs()
    metadata = {
        **i.metadata,
        "node_id": c["teaching_node_id"],
        "goal": c["segment_goal"],
        "graph_version": c["graph_version"],
        "graph_digest": c["graph_digest"],
    }
    value = PlanInputs(
        metadata,
        i.references,
        frozenset(n.id for n in g.all_nodes()),
        i.learner_evidence,
        teaching_context=c,
    )
    gateway = Gateway(deepcopy(DRAFT))
    plan = asyncio.run(generate_shared_plan(gateway, value, CallWindow()))
    assert plan["node_id"] == c["teaching_node_id"] and plan["goal"] == c["segment_goal"]
    sent = json.loads(gateway.requests[0].prompt.messages[1].content)
    assert sent["teaching_context"] == c
    snapshot = value.snapshot()
    binding = {
        "input_digest": digest("input", "learning-input-v1", snapshot=snapshot),
        "plan_digest": digest("plan", "learning-plan-v1", plan=plan),
    }
    projected, available = review_input({"plan": plan}, binding, snapshot)
    assert (
        available
        and projected["authoritative_teaching_goal"]["user_request"] == c["original_request"]
    )
    assert projected["current_segment_scope"] == c
    bad = deepcopy(value)
    bad.metadata["node_id"] = "array"
    with pytest.raises(LearningContractError, match="TEACHING_BINDING_MISMATCH"):
        bad.snapshot()
