"""Validated, deterministic access to the versioned MVP knowledge graph."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, cast

GRAPH_SCHEMA_VERSION = 1
_NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_DEFAULT_GRAPH_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge_graph.yaml"


class KnowledgeGraphValidationError(ValueError):
    """Raised when a graph source does not satisfy the versioned graph contract."""


class RelationType(StrEnum):
    """The only graph relation types supported by the MVP repository."""

    DEPENDS_ON = "DEPENDS_ON"
    SIMILAR_TO = "SIMILAR_TO"
    EXTENDS = "EXTENDS"


@dataclass(frozen=True, slots=True)
class KnowledgeNode:
    """A public, versioned knowledge node."""

    id: str
    name: str
    chapter: str
    difficulty: int
    description: str
    prerequisites: tuple[str, ...]
    learning_objectives: tuple[str, ...]
    common_misconceptions: tuple[str, ...]
    ai_context: str
    mastery_rule_key: str


@dataclass(frozen=True, slots=True)
class KnowledgeRelation:
    """A directed relation whose direction is defined by the seed graph."""

    from_node_id: str
    to_node_id: str
    relation_type: RelationType


@dataclass(frozen=True, slots=True)
class KnowledgeGraphRepository:
    """An immutable in-memory graph with stable query ordering."""

    schema_version: int
    graph_version: str
    _nodes_by_id: Mapping[str, KnowledgeNode]
    _relations: tuple[KnowledgeRelation, ...]

    @classmethod
    def from_file(cls, source: Path) -> KnowledgeGraphRepository:
        """Load JSON-compatible YAML from a source file without a graph database."""
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise KnowledgeGraphValidationError("Knowledge graph source is invalid.") from error
        return cls.from_payload(payload)

    @classmethod
    def from_payload(cls, payload: object) -> KnowledgeGraphRepository:
        """Validate a decoded seed document and build an immutable repository."""
        root = _mapping(payload, "graph")
        _require_keys(
            root,
            required={"schema_version", "graph_version", "nodes", "relations"},
            optional={"review", "relationship_direction"},
            field="graph",
        )
        schema_version = _integer(root["schema_version"], "schema_version")
        if schema_version != GRAPH_SCHEMA_VERSION:
            raise KnowledgeGraphValidationError("Unsupported graph schema version.")
        graph_version = _nonempty_string(root["graph_version"], "graph_version")
        _validate_metadata(root)
        nodes = _nodes(root["nodes"])
        nodes_by_id = {node.id: node for node in nodes}
        relations = _relations(root["relations"], nodes_by_id)
        _validate_prerequisites(nodes_by_id, relations)
        _validate_dependency_dag(nodes_by_id, relations)
        return cls(
            schema_version=schema_version,
            graph_version=graph_version,
            _nodes_by_id=MappingProxyType(nodes_by_id),
            _relations=tuple(sorted(relations, key=_relation_sort_key)),
        )

    def all_nodes(self) -> tuple[KnowledgeNode, ...]:
        """Return nodes in stable ID order."""
        return tuple(sorted(self._nodes_by_id.values(), key=lambda node: node.id))

    def all_relations(self) -> tuple[KnowledgeRelation, ...]:
        """Return all relations in stable source, target, type order."""
        return self._relations

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        """Return one node, or None when the public ID is unknown."""
        return self._nodes_by_id.get(node_id)

    def relations_of_type(self, relation_type: RelationType) -> tuple[KnowledgeRelation, ...]:
        """Return a stable subset of relations with one type."""
        return tuple(
            relation for relation in self._relations if relation.relation_type is relation_type
        )

    def outgoing_relations(self, node_id: str) -> tuple[KnowledgeRelation, ...]:
        """Return stable edges from a node, including its prerequisites."""
        return tuple(relation for relation in self._relations if relation.from_node_id == node_id)

    def incoming_relations(self, node_id: str) -> tuple[KnowledgeRelation, ...]:
        """Return stable edges into a node."""
        return tuple(relation for relation in self._relations if relation.to_node_id == node_id)

    def prerequisites_for(self, node_id: str) -> tuple[KnowledgeNode, ...]:
        """Return prerequisite nodes in stable ID order for a dependent node."""
        node = self.get_node(node_id)
        if node is None:
            return ()
        return tuple(self._nodes_by_id[prerequisite] for prerequisite in node.prerequisites)

    def successors_for(self, node_id: str) -> tuple[KnowledgeNode, ...]:
        """Return nodes that depend on this node in stable ID order."""
        successors = [
            relation.from_node_id
            for relation in self._relations
            if relation.relation_type is RelationType.DEPENDS_ON and relation.to_node_id == node_id
        ]
        return tuple(self._nodes_by_id[successor] for successor in sorted(successors))


def default_knowledge_graph_path() -> Path:
    """Return the repository-relative MVP seed path for controlled injection in tests."""
    return _DEFAULT_GRAPH_PATH


@lru_cache(maxsize=1)
def default_knowledge_graph_repository() -> KnowledgeGraphRepository:
    """Load the immutable application graph once per process."""
    return KnowledgeGraphRepository.from_file(default_knowledge_graph_path())


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise KnowledgeGraphValidationError(f"{field} must be an object.")
    return cast(Mapping[str, object], value)


def _require_keys(
    value: Mapping[str, object], *, required: set[str], optional: set[str], field: str
) -> None:
    if not required <= value.keys() or not value.keys() <= required | optional:
        raise KnowledgeGraphValidationError(f"{field} has unsupported fields.")


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeGraphValidationError(f"{field} must be a non-empty string.")
    return value


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise KnowledgeGraphValidationError(f"{field} must be an integer.")
    return value


def _string_list(value: object, field: str, *, require_item: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (require_item and not value):
        raise KnowledgeGraphValidationError(f"{field} must be a list.")
    items = tuple(_nonempty_string(item, field) for item in value)
    if len(set(items)) != len(items):
        raise KnowledgeGraphValidationError(f"{field} cannot contain duplicates.")
    return tuple(sorted(items))


def _validate_metadata(root: Mapping[str, object]) -> None:
    review = _mapping(root.get("review"), "review")
    _require_keys(
        review,
        required={"source", "fact_checked_at", "status"},
        optional=set(),
        field="review",
    )
    _nonempty_string(review["source"], "review.source")
    _nonempty_string(review["fact_checked_at"], "review.fact_checked_at")
    if review["status"] != "manual_fact_checked":
        raise KnowledgeGraphValidationError("review.status must be manual_fact_checked.")
    _nonempty_string(root.get("relationship_direction"), "relationship_direction")


def _nodes(value: object) -> tuple[KnowledgeNode, ...]:
    if not isinstance(value, list) or not value:
        raise KnowledgeGraphValidationError("nodes must be a non-empty list.")
    nodes: list[KnowledgeNode] = []
    for index, raw_node in enumerate(value):
        node = _mapping(raw_node, f"nodes[{index}]")
        _require_keys(
            node,
            required={
                "id",
                "name",
                "chapter",
                "difficulty",
                "description",
                "prerequisites",
                "learning_objectives",
                "common_misconceptions",
                "ai_context",
                "mastery_rule_key",
            },
            optional=set(),
            field=f"nodes[{index}]",
        )
        node_id = _nonempty_string(node["id"], f"nodes[{index}].id")
        if _NODE_ID_PATTERN.fullmatch(node_id) is None:
            raise KnowledgeGraphValidationError("Node ID has an unsupported format.")
        difficulty = _integer(node["difficulty"], f"nodes[{index}].difficulty")
        if not 1 <= difficulty <= 5:
            raise KnowledgeGraphValidationError("Node difficulty must be from 1 to 5.")
        nodes.append(
            KnowledgeNode(
                id=node_id,
                name=_nonempty_string(node["name"], f"nodes[{index}].name"),
                chapter=_nonempty_string(node["chapter"], f"nodes[{index}].chapter"),
                difficulty=difficulty,
                description=_nonempty_string(node["description"], f"nodes[{index}].description"),
                prerequisites=_string_list(node["prerequisites"], "prerequisites"),
                learning_objectives=_string_list(
                    node["learning_objectives"], "learning_objectives", require_item=True
                ),
                common_misconceptions=_string_list(
                    node["common_misconceptions"], "common_misconceptions"
                ),
                ai_context=_nonempty_string(node["ai_context"], f"nodes[{index}].ai_context"),
                mastery_rule_key=_nonempty_string(
                    node["mastery_rule_key"], f"nodes[{index}].mastery_rule_key"
                ),
            )
        )
    if len({node.id for node in nodes}) != len(nodes):
        raise KnowledgeGraphValidationError("Knowledge graph contains duplicate node IDs.")
    return tuple(nodes)


def _relations(
    value: object, nodes_by_id: Mapping[str, KnowledgeNode]
) -> tuple[KnowledgeRelation, ...]:
    if not isinstance(value, list):
        raise KnowledgeGraphValidationError("relations must be a list.")
    relations: list[KnowledgeRelation] = []
    for index, raw_relation in enumerate(value):
        relation = _mapping(raw_relation, f"relations[{index}]")
        _require_keys(
            relation,
            required={"from", "to", "type"},
            optional=set(),
            field=f"relations[{index}]",
        )
        from_node_id = _nonempty_string(relation["from"], f"relations[{index}].from")
        to_node_id = _nonempty_string(relation["to"], f"relations[{index}].to")
        if from_node_id not in nodes_by_id or to_node_id not in nodes_by_id:
            raise KnowledgeGraphValidationError("Relation references an unknown node.")
        if from_node_id == to_node_id:
            raise KnowledgeGraphValidationError("Self relations are not supported.")
        try:
            relation_type = RelationType(_nonempty_string(relation["type"], "relation.type"))
        except ValueError as error:
            raise KnowledgeGraphValidationError("Relation type is not supported.") from error
        relations.append(KnowledgeRelation(from_node_id, to_node_id, relation_type))
    if len({(item.from_node_id, item.to_node_id, item.relation_type) for item in relations}) != len(
        relations
    ):
        raise KnowledgeGraphValidationError("Knowledge graph contains duplicate relations.")
    return tuple(relations)


def _validate_prerequisites(
    nodes_by_id: Mapping[str, KnowledgeNode], relations: tuple[KnowledgeRelation, ...]
) -> None:
    prerequisites_by_node: dict[str, set[str]] = {node_id: set() for node_id in nodes_by_id}
    for relation in relations:
        if relation.relation_type is RelationType.DEPENDS_ON:
            prerequisites_by_node[relation.from_node_id].add(relation.to_node_id)
    for node_id, node in nodes_by_id.items():
        if set(node.prerequisites) != prerequisites_by_node[node_id]:
            raise KnowledgeGraphValidationError(
                "Node prerequisites do not match DEPENDS_ON relations."
            )


def _validate_dependency_dag(
    nodes_by_id: Mapping[str, KnowledgeNode], relations: tuple[KnowledgeRelation, ...]
) -> None:
    dependencies = {node_id: set(node.prerequisites) for node_id, node in nodes_by_id.items()}
    try:
        tuple(TopologicalSorter(dependencies).static_order())
    except CycleError as error:
        raise KnowledgeGraphValidationError(
            "DEPENDS_ON relations must not form a cycle."
        ) from error


def _relation_sort_key(relation: KnowledgeRelation) -> tuple[str, str, str]:
    return (relation.from_node_id, relation.to_node_id, relation.relation_type.value)
