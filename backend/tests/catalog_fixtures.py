"""Synthetic, explicitly TEST_ONLY approvals; never a production course signature."""

from app.services.animation_templates import load_template
from app.services.catalog_package import CatalogPackage, content_digest, validate_package
from app.services.knowledge_graph import default_knowledge_graph_repository


def package_fixture() -> CatalogPackage:
    graph = default_knowledge_graph_repository()
    nodes = {node.id: {
        "explanation": {"markdown": "Synthetic fixture for " + node.name},
        "code": {"language": "C", "source": "int main(void) { return 0; }",
                 "expected_output": "No output", "key_steps": ["TEST_ONLY"], "display_only": True},
        "exercise": {"items": [{"id": f"q{i}", "question": f"TEST_ONLY {i}?",
                                 "answer": str(i), "explanation": "TEST_ONLY feedback"}
                                for i in range(1, 4)]},
    } for node in graph.all_nodes()}
    demo = {"title": "TEST_ONLY", "perspectives": [
        {"title": str(i), "text": "TEST_ONLY"} for i in range(3)], "summary": "TEST_ONLY"}
    manifest = {"schema_version": "catalog-content-v1", "package_id": "test-only",
                "version": "1.0.0", "graph_version": graph.graph_version,
                "nodes": {key: content_digest(v) for key, v in nodes.items()},
                "demo_digest": content_digest(demo), "templates": {key:
                    load_template(key, require_executable=True).template_version for key in
                    ("linked-list-insertion", "linked-list-deletion")}}
    return validate_package({"manifest": manifest, "nodes": nodes, "demo": demo})


def approval_fixture(package: CatalogPackage) -> dict[str, object]:
    return {"manifest_digest": package.digest, "reviewer": "TEST_ONLY synthetic approval",
            "reviewed_at": "2026-10-02T00:00:00+08:00", "basis": "TEST_ONLY NOT HUMAN REVIEW",
            "resources": {f"{node}:{kind}": content_digest(content)
                          for node, values in package.nodes.items()
                          for kind, content in values.items()},
            "demo_digest": package.manifest["demo_digest"]}
