"""Release selection, fail-closed integrity and actual thirty-node queries."""

import json
from pathlib import Path
from statistics import quantiles
from time import perf_counter_ns

import pytest
from catalog_fixtures import package_fixture
from fastapi.testclient import TestClient
from test_knowledge_graph_api import openapi_validator

from app.main import app
from app.services import knowledge_graph_versions as versions
from app.services.catalog_package import validate_package
from app.services.knowledge_graph import KnowledgeGraphValidationError, RelationType


@pytest.fixture(autouse=True)
def isolated_releases(monkeypatch):
    monkeypatch.delenv("EDUMIND_KNOWLEDGE_GRAPH_PATH", raising=False)
    monkeypatch.delenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", raising=False)
    versions.graph_repository_for_version.cache_clear()
    yield
    versions.graph_repository_for_version.cache_clear()


def test_selection_rollback_and_catalog_isolation(monkeypatch):
    old = versions.configured_graph_repository()
    package = package_fixture()
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "phase-1.1.0")
    new = versions.configured_graph_repository()
    assert (len(old.all_nodes()), len(new.all_nodes())) == (10, 30)
    assert versions.catalog_knowledge_graph_repository() is old
    assert validate_package(package.payload()).digest == package.digest
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "unknown")
    with pytest.raises(KnowledgeGraphValidationError):
        versions.configured_graph_repository()
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "mvp-0.2.0")
    assert versions.configured_graph_repository() is old
    assert versions.graph_repository_for_version("phase-1.1.0", None) is new


def test_queries_and_measurement():
    graph = versions.graph_repository_for_version("phase-1.1.0")
    timings = {name: [] for name in ("current", "prerequisite", "successor", "similar")}
    for node in graph.all_nodes():
        assert {n.id for n in graph.prerequisites_for(node.id)} == set(node.prerequisites)
        assert {n.id for n in graph.successors_for(node.id)} == {
            r.from_node_id
            for r in graph.incoming_relations(node.id)
            if r.relation_type is RelationType.DEPENDS_ON
        }
        assert {n.id for n in graph.similar_for(node.id)} == {
            r.to_node_id
            for r in graph.outgoing_relations(node.id)
            if r.relation_type is RelationType.SIMILAR_TO
        }
    for name, query in zip(
        timings,
        (graph.get_node, graph.prerequisites_for, graph.successors_for, graph.similar_for),
        strict=True,
    ):
        for _ in range(500):
            started = perf_counter_ns()
            for node in graph.all_nodes():
                query(node.id)
            timings[name].append((perf_counter_ns() - started) / 30 / 1e6)
    report = {
        "graph_version": graph.graph_version,
        "nodes": 30,
        "edges": 69,
        "queries_per_kind": 15000,
        "unit": "batch-amortized milliseconds",
        "p95": {name: quantiles(samples, n=100)[94] for name, samples in timings.items()},
        "qualification": "in-memory query evidence only; no HTTP/PG/Neo4j comparison",
    }
    evidence = Path(__file__).resolve().parents[2] / "local-materials/phase-1-t032/measurement.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(report, indent=2) + "\n")
    assert len(graph.all_relations()) == 69


@pytest.mark.parametrize(
    "artifact",
    [
        "knowledge_graph.yaml",
        "knowledge/phase-1.1.0.json",
        "knowledge/phase-1.1.0.sources.json",
        "knowledge/phase-1.1.0.manifest.json",
    ],
)
@pytest.mark.parametrize("damage", ["missing", "tampered", "symlink"])
def test_release_corruption_rejected(tmp_path, monkeypatch, artifact, damage):
    import shutil

    shutil.copytree(versions._DATA, tmp_path / "data", ignore=shutil.ignore_patterns("videos"))
    monkeypatch.setattr(versions, "_DATA", tmp_path / "data")
    target = versions._DATA / artifact
    original = target.read_bytes()
    target.unlink()
    if damage == "tampered":
        target.write_bytes(original + b" ")
    elif damage == "symlink":
        other = tmp_path / "other"
        other.write_bytes(original)
        target.symlink_to(other)
    version = "mvp-0.2.0" if artifact == "knowledge_graph.yaml" else "phase-1.1.0"
    with pytest.raises(KnowledgeGraphValidationError):
        versions.graph_repository_for_version(version)


def test_configuration_conflict_does_not_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_PATH", str(tmp_path / "secret-path"))
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "phase-1.1.0")
    with pytest.raises(KnowledgeGraphValidationError):
        versions.configured_graph_repository()


def test_public_expansion_and_fixed_unavailable_response(monkeypatch):
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "phase-1.1.0")
    with TestClient(app) as client:
        result = client.get("/api/graph")
        assert result.status_code == 200
        openapi_validator("KnowledgeGraph").validate(result.json())
        assert result.json()["schema_version"] == 2
        assert len(result.json()["nodes"]) == 30
        assert client.get("/api/graph/node/not-a-node").status_code == 404
        monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "secret-invalid-version")
        for url in ("/api/graph", "/api/graph/node/array"):
            result = client.get(url)
            assert result.status_code == 503
            assert result.headers["cache-control"] == "no-store"
            assert result.json() == {
                "code": "GRAPH_UNAVAILABLE",
                "message": "Knowledge graph unavailable.",
                "retryable": False,
            }


def test_corrupt_selected_release_returns_503(tmp_path, monkeypatch):
    monkeypatch.setattr(versions, "_DATA", tmp_path)
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "phase-1.1.0")
    with TestClient(app) as client:
        result = client.get("/api/graph")
    assert result.status_code == 503
    assert result.json()["code"] == "GRAPH_UNAVAILABLE"
    assert str(tmp_path) not in result.text


def test_legacy_path_and_conflict(monkeypatch, tmp_path):
    source = tmp_path / "historical.yaml"
    source.write_bytes((versions._DATA / "knowledge_graph.yaml").read_bytes())
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_PATH", str(source))
    assert versions.configured_graph_repository().graph_version == "mvp-0.2.0"
    source.write_bytes(b"{}")
    # Already-loaded objects remain immutable; restart/reload validates new bytes.
    assert len(versions.configured_graph_repository().all_nodes()) == 10
    versions.graph_repository_for_version.cache_clear()
    with pytest.raises(KnowledgeGraphValidationError):
        versions.configured_graph_repository()
