"""Versioned metadata and reference provenance, without fabricated lesson evidence."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.knowledge_graph import (
    KnowledgeGraphRepository,
    KnowledgeGraphValidationError,
    default_knowledge_graph_repository,
)

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "data/knowledge/phase-1.1.0.json"
SIDECAR = GRAPH.with_name("phase-1.1.0.sources.json")


def documents():
    return json.loads(GRAPH.read_text()), json.loads(SIDECAR.read_text())


def bind(graph, sources):
    graph["references"]["sha256"] = hashlib.sha256(
        json.dumps(sources, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_exact_approved_structure_and_sources_preserve_legacy_metadata():
    graph, sources = documents()
    plan = json.loads((ROOT / "data/knowledge/expansion-v1/plan.json").read_text())
    original = json.loads((ROOT / "data/knowledge_graph.yaml").read_text())
    assert len(graph["nodes"]) == 30
    assert graph["relations"] == plan["relations"]
    definitions = {n["id"]: n for n in graph["nodes"]}
    for old in original["nodes"]:
        assert definitions[old["id"]] == old
    for planned in plan["nodes"]:
        n = definitions[planned["id"]]
        assert n["name"] == planned["name"]
        assert n["prerequisites"] == planned["prerequisites"]
        assert n["learning_objectives"] and n["common_misconceptions"] and n["ai_context"]
        assert sources["node_references"][n["id"]] == planned["references"]
    assert graph["review"]["status"] == "reference_checked"
    assert sources["qualification"].startswith("metadata_only;")
    assert hashlib.sha256((ROOT / "data/knowledge_graph.yaml").read_bytes()).hexdigest() == (
        "84ac4c08297623a3a6e167ef9775b67ab195c43048e23be1e2874b26a6f63dc7"
    )


def test_expanded_read_is_explicit_and_default_catalog_stays_v1():
    expanded = KnowledgeGraphRepository.from_file(GRAPH)
    default = default_knowledge_graph_repository()
    assert (expanded.schema_version, expanded.graph_version) == (2, "phase-1.1.0")
    assert len(expanded.all_nodes()) == 30
    assert len(expanded.all_relations()) == 69
    assert (default.schema_version, default.graph_version) == (1, "mvp-0.2.0")
    assert len(default.all_nodes()) == 10
    assert default.get_node("breadth-first-search") is None
    assert expanded.reference_ids_for("breadth-first-search") == ("ods-graph",)
    assert "queue" in [n.id for n in expanded.prerequisites_for("breadth-first-search")]
    assert "stack" in [n.id for n in expanded.prerequisites_for("depth-first-search")]
    assert expanded.reference_digest
    with pytest.raises(TypeError):
        expanded._reference_ids["array"] = ("forged",)


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "missing_prerequisite",
        "cycle",
        "reverse_similarity",
        "wrong_extension",
        "direction",
        "fake_manual_review",
        "empty_objectives",
        "empty_misconceptions",
        "unknown_field",
    ],
)
def test_rejects_invalid_graph_without_altering_signed_seed(change):
    graph, sources = documents()
    if change == "duplicate":
        graph["nodes"].append(deepcopy(graph["nodes"][0]))
    elif change == "missing_prerequisite":
        graph["nodes"][0]["prerequisites"].append("unknown-node")
        graph["relations"].append({"from": "array", "to": "unknown-node", "type": "DEPENDS_ON"})
    elif change == "cycle":
        graph["nodes"][0]["prerequisites"].append("breadth-first-search")
        graph["relations"].append(
            {"from": "array", "to": "breadth-first-search", "type": "DEPENDS_ON"}
        )
    elif change == "reverse_similarity":
        graph["relations"].remove({"from": "quick-sort", "to": "merge-sort", "type": "SIMILAR_TO"})
    elif change == "wrong_extension":
        graph["relations"].append({"from": "array", "to": "binary-tree", "type": "EXTENDS"})
    elif change == "direction":
        graph["relationship_direction"] = "prerequisite points to dependent"
    elif change == "fake_manual_review":
        graph["review"]["status"] = "manual_fact_checked"
    elif change == "empty_objectives":
        graph["nodes"][0]["learning_objectives"] = []
    elif change == "empty_misconceptions":
        graph["nodes"][0]["common_misconceptions"] = []
    else:
        graph["nodes"][0]["course_approved"] = True
    with pytest.raises(KnowledgeGraphValidationError):
        KnowledgeGraphRepository.from_payload(graph, reference_payload=sources)


@pytest.mark.parametrize(
    "change",
    [
        "missing_binding",
        "unknown_source",
        "duplicate_binding",
        "version",
        "date",
        "grant_course",
        "unsafe_url",
        "unexpected_field",
        "content_tamper",
        "graph_digest",
        "no_sidecar",
    ],
)
def test_rejects_reference_corruption_or_fabricated_qualification(change):
    graph, sources = documents()
    if change == "missing_binding":
        sources["node_references"].pop("array")
    elif change == "unknown_source":
        sources["node_references"]["array"] = ["unknown-source"]
    elif change == "duplicate_binding":
        sources["node_references"]["array"] *= 2
    elif change == "version":
        sources["graph_version"] = "other-version"
    elif change == "date":
        sources["checked_at"] = "2026-02-30"
    elif change == "grant_course":
        sources["qualification"] = "all_courses_approved"
    elif change == "unsafe_url":
        sources["sources"]["ods-array"]["url"] = "javascript:alert(1)"
    elif change == "unexpected_field":
        sources["sources"]["ods-array"]["api_key"] = "forbidden"
    elif change == "content_tamper":
        sources["sources"]["ods-array"]["sections"] = "wrong section"
    elif change == "graph_digest":
        graph["references"]["sha256"] = "0" * 64
    elif change == "no_sidecar":
        sources = None
    if change not in ["content_tamper", "graph_digest", "no_sidecar"]:
        bind(graph, sources)
    with pytest.raises(KnowledgeGraphValidationError):
        KnowledgeGraphRepository.from_payload(graph, reference_payload=sources)


@pytest.mark.parametrize(
    "path",
    [
        "../phase-1.1.0.sources.json",
        "/tmp/other.sources.json",
        "https://example.com/refs.sources.json",
    ],
)
def test_no_arbitrary_reference_file_access(tmp_path, path):
    graph, _ = documents()
    graph["references"]["file"] = path
    file = tmp_path / "graph.json"
    file.write_text(json.dumps(graph))
    with pytest.raises(KnowledgeGraphValidationError):
        KnowledgeGraphRepository.from_file(file)


def test_missing_corrupt_or_symlink_reference_file_fails_closed(tmp_path):
    graph, sources = documents()
    file = tmp_path / "graph.json"
    file.write_text(json.dumps(graph))
    reference = tmp_path / graph["references"]["file"]
    with pytest.raises(KnowledgeGraphValidationError, match="unavailable"):
        KnowledgeGraphRepository.from_file(file)
    reference.write_text("not JSON")
    with pytest.raises(KnowledgeGraphValidationError, match="unavailable"):
        KnowledgeGraphRepository.from_file(file)
    reference.unlink()
    reference.symlink_to(SIDECAR)
    with pytest.raises(KnowledgeGraphValidationError, match="local sibling"):
        KnowledgeGraphRepository.from_file(file)
    reference.unlink()
    reference.write_text(json.dumps(sources))
    assert len(KnowledgeGraphRepository.from_file(file).all_nodes()) == 30
