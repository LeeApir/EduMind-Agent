"""Deterministic, prerequisite-safe and explainable path rules."""

import json
from pathlib import Path

import pytest

from app.services.knowledge_graph import (
    KnowledgeGraphRepository,
    KnowledgeGraphValidationError,
    default_knowledge_graph_path,
)
from app.services.path_rules import (
    PATH_RULE_CONFIG,
    PATH_RULE_VERSION,
    PathMastery,
    PathRuleError,
    plan_learning_path,
)


def graph() -> KnowledgeGraphRepository:
    return KnowledgeGraphRepository.from_file(default_knowledge_graph_path())


def test_path_respects_all_prerequisites_and_is_stable() -> None:
    repository = graph()
    first = plan_learning_path(repository, target_node_id="linked-list-insertion", mastery={})
    second = plan_learning_path(repository, target_node_id="linked-list-insertion", mastery={})
    assert first == second
    assert first.rule_version == PATH_RULE_VERSION
    ordered = [step.node_id for step in first.steps]
    assert ordered[-1] == "linked-list-insertion"
    for step in first.steps:
        node = repository.get_node(step.node_id)
        assert node is not None
        assert all(
            ordered.index(prerequisite) < ordered.index(node.id)
            for prerequisite in node.prerequisites
        )
    assert first.current_node_id == ordered[0]
    assert first.next_node_id == ordered[1]
    assert first.steps[0].reason["kind"] in {"prerequisite", "mastery_state"}
    assert all(
        step.recommended_resource in {"explanation", "exercise", "review"} for step in first.steps
    )
    assert all(step.estimated_minutes > 0 for step in first.steps)


def test_weak_prerequisite_returns_to_front_with_evidence() -> None:
    result = plan_learning_path(
        graph(),
        target_node_id="single-linked-list",
        mastery={
            "c-pointer": PathMastery(0.2, "weak", ("quiz_score=0.0000;wrong_streak=2",)),
            "linked-list-concept": PathMastery(0.5, "learning"),
        },
    )
    assert result.current_node_id == "c-pointer"
    assert result.steps[0].reason == {
        "kind": "mastery_evidence",
        "node_id": "c-pointer",
        "score": 0.2,
        "status": "weak",
        "evidence_summary": ["quiz_score=0.0000;wrong_streak=2"],
    }
    assert result.steps[0].recommended_resource == "review"


def test_mastered_prerequisites_are_skipped_but_unmastered_goal_remains() -> None:
    result = plan_learning_path(
        graph(),
        target_node_id="single-linked-list",
        mastery={
            "c-pointer": PathMastery(0.9, "mastered"),
            "linked-list-concept": PathMastery(0.85, "mastered"),
        },
    )
    assert [step.node_id for step in result.steps] == ["single-linked-list"]
    assert result.prerequisite_node_ids == ("c-pointer", "linked-list-concept")
    assert result.steps[0].reason["kind"] == "mastery_state"


def test_mastered_target_has_no_remaining_steps() -> None:
    result = plan_learning_path(
        graph(),
        target_node_id="array",
        mastery={"array": PathMastery(0.9, "mastered")},
    )
    assert result.steps == ()
    assert result.current_node_id is None
    assert result.next_node_id is None


def test_explicit_profile_preference_changes_resource_and_explanation() -> None:
    result = plan_learning_path(
        graph(),
        target_node_id="array",
        mastery={},
        profile={"engineering_preference": {"code_first": True}},
    )
    assert result.steps[0].recommended_resource == "code"
    assert result.steps[0].reason == {
        "kind": "profile_field",
        "node_id": "array",
        "field": "engineering_preference.code_first",
    }
    old_rule = plan_learning_path(
        graph(),
        target_node_id="array",
        mastery={},
        profile={"engineering_preference": {"code_first": True}},
        rule_version="path-v1",
    )
    assert old_rule.rule_version == "path-v1"
    assert old_rule.steps[0].recommended_resource == "explanation"


@pytest.mark.parametrize(
    ("target", "available", "code"),
    [
        ("missing-node", None, "UNKNOWN_TARGET"),
        ("single-linked-list", frozenset({"single-linked-list"}), "UNREACHABLE_TARGET"),
    ],
)
def test_unknown_or_excluded_prerequisite_is_unreachable(
    target: str, available: frozenset[str] | None, code: str
) -> None:
    with pytest.raises(PathRuleError) as error:
        plan_learning_path(graph(), target_node_id=target, mastery={}, available_node_ids=available)
    assert error.value.code == code


def test_invalid_mastery_and_graph_structure_are_rejected() -> None:
    with pytest.raises(PathRuleError, match="INVALID_MASTERY"):
        plan_learning_path(
            graph(), target_node_id="array", mastery={"array": PathMastery(float("nan"), "weak")}
        )
    with pytest.raises(PathRuleError, match="INVALID_MASTERY"):
        plan_learning_path(
            graph(),
            target_node_id="array",
            mastery={"array": PathMastery(0.2, "weak", forgetting_risk=2.0)},
        )

    payload = json.loads(Path(default_knowledge_graph_path()).read_text(encoding="utf-8"))
    array_node = next(node for node in payload["nodes"] if node["id"] == "array")
    array_node["prerequisites"] = ["not-in-graph"]
    with pytest.raises(KnowledgeGraphValidationError):
        KnowledgeGraphRepository.from_payload(payload)


def test_rule_weights_are_versioned_and_immutable() -> None:
    assert PATH_RULE_VERSION == "path-v2"
    assert PATH_RULE_CONFIG["mastered_at"] == 0.8
    with pytest.raises(TypeError):
        PATH_RULE_CONFIG["mastered_at"] = 0.1  # type: ignore[index]
