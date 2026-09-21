"""Integration coverage for public knowledge graph API responses."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.main import app
from app.services.knowledge_graph import default_knowledge_graph_path


def openapi_validator(schema_name: str) -> Draft202012Validator:
    workspace = Path(__file__).resolve().parents[2]
    specification = json.loads(
        (workspace / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )
    return Draft202012Validator(
        {
            "components": specification["components"],
            "$ref": f"#/components/schemas/{schema_name}",
        }
    )


def test_public_graph_is_stable_and_conforms_to_openapi() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        first = client.get("/api/graph")
        second = client.get("/api/graph")

    assert first.status_code == second.status_code == 200
    assert first.headers["cache-control"] == "public, max-age=300"
    assert first.json() == second.json()
    payload = first.json()
    openapi_validator("KnowledgeGraph").validate(payload)
    assert payload["graph_version"] == "mvp-0.2.0"
    assert [node["id"] for node in payload["nodes"]] == sorted(
        node["id"] for node in payload["nodes"]
    )
    assert [
        (relation["from"], relation["to"], relation["type"])
        for relation in payload["relations"]
    ] == sorted(
        (relation["from"], relation["to"], relation["type"])
        for relation in payload["relations"]
    )


def test_public_node_detail_is_stable_and_unknown_node_does_not_leak_source() -> None:
    with TestClient(app, base_url="https://testserver") as client:
        detail = client.get("/api/graph/node/linked-list-insertion")
        repeated = client.get("/api/graph/node/linked-list-insertion")
        missing = client.get("/api/graph/node/not-a-node")

    assert detail.status_code == repeated.status_code == 200
    assert detail.headers["cache-control"] == "public, max-age=300"
    assert detail.json() == repeated.json()
    openapi_validator("KnowledgeNodeDetail").validate(detail.json())
    assert detail.json()["node"]["prerequisites"] == ["c-pointer", "linked-list-traversal"]
    assert missing.status_code == 404
    assert missing.json() == {
        "code": "GRAPH_NODE_NOT_FOUND",
        "message": "Knowledge node not found.",
        "retryable": False,
    }
    assert str(default_knowledge_graph_path()) not in missing.text
