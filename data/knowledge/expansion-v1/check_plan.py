"""Validate and microbenchmark a proposed curriculum, without publishing resources."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from dataclasses import replace
from graphlib import TopologicalSorter
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[3]
PLAN = Path(__file__).with_name("plan.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.services.knowledge_graph import (
        KnowledgeGraphRepository,
        KnowledgeRelation,
        RelationType,
    )

    seed = KnowledgeGraphRepository.from_file(ROOT / "data/knowledge_graph.yaml")
    plan = json.loads(PLAN.read_text())
    nodes = {n["id"]: n for n in plan["nodes"]}
    require(len(nodes) == len(plan["nodes"]) == 30, "Exactly 30 unique nodes required")
    require(
        all(re.fullmatch(r"[a-z][a-z0-9-]{1,63}", i) for i in nodes),
        "Invalid stable ID",
    )
    require(
        all(
            n["references"] and set(n["references"]) <= plan["references"].keys()
            for n in nodes.values()
        ),
        "Missing reference",
    )
    for old in seed.all_nodes():
        n = nodes[old.id]
        require(
            n["origin"] == "legacy"
            and n["name"] == old.name
            and sorted(n["prerequisites"]) == list(old.prerequisites),
            "Legacy identity/prerequisites changed",
        )
    require(
        sum(
            n["origin"] == "new"
            and n["initial_course_qualification"] == "metadata_only"
            for n in nodes.values()
        )
        == 20,
        "New nodes must remain metadata only",
    )
    edges = {(r["from"], r["to"], r["type"]) for r in plan["relations"]}
    require(len(edges) == len(plan["relations"]), "Duplicate edge")
    for a, b, kind in edges:
        require(a in nodes and b in nodes and a != b, "Unknown endpoint/self edge")
        RelationType(kind)
        if kind == "SIMILAR_TO":
            require((b, a, kind) in edges, "Similarity requires explicit reverse edge")
    for n in nodes.values():
        require(
            len(n["prerequisites"]) == len(set(n["prerequisites"])),
            "Duplicate prerequisite",
        )
        require(
            set(n["prerequisites"])
            == {b for a, b, k in edges if a == n["id"] and k == "DEPENDS_ON"},
            "Prerequisite/edge mismatch",
        )
    require(
        all(
            (r.from_node_id, r.to_node_id, r.relation_type.value) in edges
            for r in seed.all_relations()
        ),
        "Legacy relation removed",
    )
    order = tuple(
        TopologicalSorter(
            {i: n["prerequisites"] for i, n in nodes.items()}
        ).static_order()
    )
    # Structural objects only. No from_payload with invented manual review stamps,
    # no course creation, no mastery DB writes and no default repository replacement.
    example = seed.all_nodes()[0]
    repository = KnowledgeGraphRepository(
        1,
        plan["proposed_graph_version"],
        MappingProxyType(
            {
                i: replace(
                    example,
                    id=i,
                    name=n["name"],
                    prerequisites=tuple(sorted(n["prerequisites"])),
                )
                for i, n in nodes.items()
            }
        ),
        tuple(KnowledgeRelation(a, b, RelationType(k)) for a, b, k in sorted(edges)),
    )

    def similar(i):
        return tuple(
            r.to_node_id
            for r in repository.outgoing_relations(i)
            if r.relation_type is RelationType.SIMILAR_TO
        )

    def closure(i):
        seen = set()
        pending = [i]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            pending.extend(n.id for n in repository.prerequisites_for(current))
        return tuple(sorted(seen))

    require(
        "queue" in closure("breadth-first-search"), "BFS queue prerequisite missing"
    )
    require("stack" in closure("depth-first-search"), "DFS stack prerequisite missing")
    results = {}
    for label, query in {
        "current": repository.get_node,
        "prerequisites": repository.prerequisites_for,
        "successors": repository.successors_for,
        "similar": similar,
        "transitive_prerequisites": closure,
    }.items():
        for i in order:
            query(i)
        samples = []
        for _ in range(500):
            start = perf_counter_ns()
            for i in order:
                query(i)
            samples.append((perf_counter_ns() - start) / len(order) / 1_000_000)
        samples.sort()
        results[label] = {
            "queries": 500 * len(order),
            "median_ms_per_query": round(median(samples), 6),
            "p95_batch_amortized_ms_per_query": round(samples[474], 6),
        }
    print(
        json.dumps(
            {
                "passed": True,
                "nodes": len(nodes),
                "relations": len(edges),
                "topological_order": order,
                "measurement": "in-process structural query microbenchmark; NOT HTTP/DB/Neo4j comparison or release SLA",
                "python": platform.python_version(),
                "machine": platform.machine(),
                "platform": platform.system(),
                "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
                "repository_sha256": hashlib.sha256(
                    (ROOT / "backend/app/services/knowledge_graph.py").read_bytes()
                ).hexdigest(),
                "results": results,
                "provider_requests": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
