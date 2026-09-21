"""Public, deterministic read APIs for the versioned knowledge graph."""

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse

from app.services.knowledge_graph import (
    KnowledgeGraphRepository,
    KnowledgeNode,
    KnowledgeRelation,
    default_knowledge_graph_repository,
)

router = APIRouter(tags=["Knowledge Graph"])


def knowledge_graph_repository() -> KnowledgeGraphRepository:
    """Expose the process-local, validated public graph through dependency injection."""
    return default_knowledge_graph_repository()


def node_payload(node: KnowledgeNode) -> dict[str, object]:
    """Serialize a graph node without internal review metadata."""
    return {
        "id": node.id,
        "name": node.name,
        "chapter": node.chapter,
        "difficulty": node.difficulty,
        "description": node.description,
        "prerequisites": list(node.prerequisites),
        "learning_objectives": list(node.learning_objectives),
        "common_misconceptions": list(node.common_misconceptions),
        "ai_context": node.ai_context,
        "mastery_rule_key": node.mastery_rule_key,
    }


def relation_payload(relation: KnowledgeRelation) -> dict[str, str]:
    """Serialize one stable directed relation."""
    return {
        "from": relation.from_node_id,
        "to": relation.to_node_id,
        "type": relation.relation_type.value,
    }


def graph_node_not_found() -> JSONResponse:
    """Return the public stable error without leaking a source path or exception."""
    return JSONResponse(
        status_code=404,
        content={
            "code": "GRAPH_NODE_NOT_FOUND",
            "message": "Knowledge node not found.",
            "retryable": False,
        },
    )


@router.get("/api/graph")
def get_knowledge_graph(
    response: Response,
    repository: KnowledgeGraphRepository = Depends(knowledge_graph_repository),
) -> dict[str, object]:
    """Return only public graph data in deterministic order, without authentication."""
    response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "schema_version": repository.schema_version,
        "graph_version": repository.graph_version,
        "nodes": [node_payload(node) for node in repository.all_nodes()],
        "relations": [relation_payload(relation) for relation in repository.all_relations()],
    }


@router.get("/api/graph/node/{node_id}", response_model=None)
def get_knowledge_node(
    node_id: str,
    response: Response,
    repository: KnowledgeGraphRepository = Depends(knowledge_graph_repository),
) -> dict[str, object] | JSONResponse:
    """Return one public node and its stable incoming and outgoing relations."""
    node = repository.get_node(node_id)
    if node is None:
        return graph_node_not_found()
    response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "graph_version": repository.graph_version,
        "node": node_payload(node),
        "incoming_relations": [
            relation_payload(relation) for relation in repository.incoming_relations(node_id)
        ],
        "outgoing_relations": [
            relation_payload(relation) for relation in repository.outgoing_relations(node_id)
        ],
    }
