"""Classroom-turn context is minimal, evidence-backed and free of private internals."""

import json

import pytest

from app.agents.classroom_context import build_classroom_context
from app.services.knowledge_graph import default_knowledge_graph_repository


def context(profile=None, reviewed_resources=(), path=None):
    return build_classroom_context(
        default_knowledge_graph_repository(),
        node_id="linked-list-insertion",
        goal="理解链表的插入操作",
        reviewed_resources=reviewed_resources,
        profile=profile or {},
        path=path,
    )


def test_context_has_current_facts_prerequisites_goal_and_reviewed_resources() -> None:
    reference = context(
        reviewed_resources=[
            {"resource_type": "explanation", "content": {"markdown": "链表节点由指针连接。"}},
            {"resource_type": "code", "content": {"language": "C", "source": "void f() {}"}},
        ]
    ).payload()
    assert reference["context_version"] == "classroom-turn-context-v1"
    assert reference["graph_version"] == "mvp-0.2.0"
    assert reference["node"]["id"] == "linked-list-insertion"
    assert reference["node"]["difficulty"] == 3
    assert reference["node"]["learning_objectives"]
    assert reference["node"]["common_misconceptions"]
    assert reference["goal"] == "理解链表的插入操作"
    assert {item["id"] for item in reference["prerequisites"]} == {
        "c-pointer",
        "linked-list-traversal",
    }
    assert reference["reviewed_resources"] == [
        {"resource_type": "explanation", "content": {"markdown": "链表节点由指针连接。"}},
        {"resource_type": "code", "content": {"language": "C", "source": "void f() {}"}},
    ]
    # Context is immutable: mutating a returned payload must not change the next build.
    reference["node"]["description"] = "changed"
    assert context().payload()["node"]["description"] != "changed"


def test_only_relevant_known_fields_are_sent_without_evidence_or_private_values() -> None:
    record = {"source": "manual_correction", "confidence": 1, "observed_at": "private-time"}
    reference = context(
        profile={
            "initial_query": "private goal",
            "professional_background": {"school": "private-school"},
            "knowledge_base": {
                "mastered": ["C 指针", "queue"],
                "weak": ["linked-list-traversal"],
                "unknown": ["linked-list-insertion"],
            },
            "error_preferences": [
                {"topic": "链表插入", "issue": "连接顺序", "raw_answer": "private-answer"},
                {"topic": "队列", "issue": "unrelated"},
            ],
            "evidence": {
                "knowledge_base": [record],
                "error_preferences": [record],
            },
        }
    ).payload()
    known = reference["known_profile"]
    assert known["knowledge_base"] == {
        "mastered": ["C 指针"],
        "weak": ["linked-list-traversal"],
    }
    assert known["error_preferences"] == [{"topic": "链表插入", "issue": "连接顺序"}]
    serialized = json.dumps(reference, ensure_ascii=False)
    for excluded in (
        "private",
        "unrelated",
        "queue",
        "unknown",
        "raw_answer",
        "observed_at",
        "confidence",
        "manual_correction",
    ):
        assert excluded not in serialized


@pytest.mark.parametrize(
    "profile",
    [
        {"knowledge_base": None, "error_preferences": None},
        {"knowledge_base": {"weak": ["C 指针"]}},
        {
            "knowledge_base": {"weak": ["C 指针"]},
            "evidence": {
                "knowledge_base": [{"source": "initial_query", "confidence": 0}]
            },
        },
    ],
)
def test_unknown_or_unbacked_fields_are_not_sent(profile) -> None:
    assert context(profile).payload()["known_profile"] == {}


def test_only_evidence_backed_persona_is_available_to_future_tutor_turns() -> None:
    profile = {
        "cognitive_style": {"preference_persona": "engineering"},
        "evidence": {"cognitive_style": [{"source": "explicit_feedback", "confidence": 0.9}]},
    }
    assert context(profile).payload()["known_profile"] == {
        "preference_persona": "engineering",
    }
    profile["evidence"] = {}
    assert context(profile).payload()["known_profile"] == {}


def test_path_context_keeps_only_relevant_signals() -> None:
    path = {
        "version": 3,
        "target_node_id": "linked-list-insertion",
        "graph_version": "mvp-0.2.0",
        "profile_version": 2,
        "mastery_revision_watermark": 9,
        "planner_rule_version": "v1",
        "nodes": [{"node_id": "linked-list-insertion", "reason": "secret"}],
        "node_details": [{"node_id": "linked-list-insertion"}],
        "current_node_id": "linked-list-insertion",
        "prerequisite_node_ids": ["c-pointer", "linked-list-traversal"],
        "next_node_id": "linked-list-deletion",
        "reasons": [
            {
                "kind": "prerequisite",
                "summary": "c-pointer 是前置节点。",
                "knowledge_node_id": "c-pointer",
            }
        ],
        "changes": {"secret": "path-change"},
        "is_stale": False,
    }
    path_context = context(path=path).payload()["path"]
    assert path_context == {
        "current_node_id": "linked-list-insertion",
        "prerequisite_node_ids": ["c-pointer", "linked-list-traversal"],
        "next_node_id": "linked-list-deletion",
        "reasons": [{"kind": "prerequisite", "summary": "c-pointer 是前置节点。"}],
    }


def test_missing_node_or_goal_is_rejected() -> None:
    graph = default_knowledge_graph_repository()
    with pytest.raises(ValueError):
        build_classroom_context(graph, node_id="unknown-node", goal="x")
    with pytest.raises(ValueError):
        build_classroom_context(graph, node_id="linked-list-insertion", goal="   ")
