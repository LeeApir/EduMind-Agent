"""Unit coverage for the local versioned knowledge graph repository."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.knowledge_graph import (
    KnowledgeGraphRepository,
    KnowledgeGraphValidationError,
    RelationType,
    default_knowledge_graph_path,
)


def seed_payload() -> dict[str, object]:
    return json.loads(default_knowledge_graph_path().read_text(encoding="utf-8"))


def test_repository_loads_seed_and_returns_deterministic_queries() -> None:
    repository = KnowledgeGraphRepository.from_file(default_knowledge_graph_path())

    assert repository.schema_version == 1
    assert repository.graph_version == "mvp-0.2.0"
    assert [node.id for node in repository.all_nodes()] == sorted(
        node.id for node in repository.all_nodes()
    )
    assert [
        (relation.from_node_id, relation.to_node_id, relation.relation_type.value)
        for relation in repository.all_relations()
    ] == sorted(
        (relation.from_node_id, relation.to_node_id, relation.relation_type.value)
        for relation in repository.all_relations()
    )
    assert [node.id for node in repository.prerequisites_for("linked-list-insertion")] == [
        "c-pointer",
        "linked-list-traversal",
    ]
    assert [node.id for node in repository.successors_for("single-linked-list")] == [
        "linked-list-traversal",
    ]
    assert repository.get_node("missing-node") is None
    assert repository.prerequisites_for("missing-node") == ()
    assert repository.successors_for("missing-node") == ()
    assert len(repository.relations_of_type(RelationType.SIMILAR_TO)) == 2


def write_payload(tmp_path: Path, payload: dict[str, object]) -> Path:
    source = tmp_path / "graph.yaml"
    source.write_text(json.dumps(payload), encoding="utf-8")
    return source


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["nodes"].append(deepcopy(payload["nodes"][0])),
        lambda payload: payload["relations"].append(
            {"from": "array", "to": "missing-node", "type": "DEPENDS_ON"}
        ),
        lambda payload: payload["relations"].append(
            {"from": "array", "to": "stack", "type": "UNKNOWN"}
        ),
        lambda payload: payload["relations"].append(
            {"from": "array", "to": "stack", "type": "DEPENDS_ON"}
        ),
        lambda payload: payload["nodes"][0].__setitem__("difficulty", 6),
    ],
)
def test_repository_rejects_invalid_nodes_and_relations(
    tmp_path: Path, mutate: object
) -> None:
    payload = seed_payload()
    assert callable(mutate)
    mutate(payload)

    with pytest.raises(KnowledgeGraphValidationError):
        KnowledgeGraphRepository.from_file(write_payload(tmp_path, payload))


def test_repository_rejects_dependency_cycles_and_prerequisite_drift(tmp_path: Path) -> None:
    cyclic = seed_payload()
    cyclic["relations"].append(
        {"from": "c-pointer", "to": "linked-list-insertion", "type": "DEPENDS_ON"}
    )
    cyclic_node = next(node for node in cyclic["nodes"] if node["id"] == "c-pointer")
    cyclic_node["prerequisites"].append("linked-list-insertion")
    with pytest.raises(KnowledgeGraphValidationError, match="cycle"):
        KnowledgeGraphRepository.from_file(write_payload(tmp_path, cyclic))

    drifted = seed_payload()
    drifted_node = next(node for node in drifted["nodes"] if node["id"] == "stack")
    drifted_node["prerequisites"] = []
    with pytest.raises(KnowledgeGraphValidationError, match="prerequisites"):
        KnowledgeGraphRepository.from_file(write_payload(tmp_path, drifted))
