"""Optional, conservative mention suggestions over exact owned course snapshots.

No Provider, single-node resolver, mastery write or persisted path mutation is involved.
"""

import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.free_course_snapshots import SnapshotRepository, WriteFence, digest
from app.services.knowledge_graph import KnowledgeGraphRepository, KnowledgeGraphValidationError
from app.services.knowledge_graph_versions import graph_repository_for_version
from app.services.path_rules import PathRuleError, plan_learning_path

LINK_RULE_VERSION = "free-course-exact-mention-v1"


def _mentions(text: str, graph: KnowledgeGraphRepository) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for node in graph.all_nodes():
        for term in {node.name, node.id}:
            # Latin identifiers must be complete tokens, not array-stack -> array.
            pattern = re.escape(term)
            if term.isascii():
                pattern = r"(?<![A-Za-z0-9_-])" + pattern + r"(?![A-Za-z0-9_-])"
            for match in re.finditer(pattern, text):
                matches.append(
                    dict(node_id=node.id, start=match.start(), end=match.end(), excerpt=term)
                )
    # Do not infer queue from circular-queue/循环队列, or stack from 顺序栈.
    longest = []
    furthest_end = -1
    for item in sorted(matches, key=lambda item: (item["start"], -item["end"], item["node_id"])):
        if item["end"] > furthest_end:
            longest.append(item)
            furthest_end = item["end"]
    return longest


def _links(
    graph: KnowledgeGraphRepository,
    text: str,
    scene_id: str | None,
    reference: dict[str, Any],
    relation: str,
) -> list[dict[str, Any]]:
    by_node: dict[str, dict[str, Any]] = {}
    for mention in _mentions(text, graph):
        node_id = mention["node_id"]
        link = by_node.setdefault(
            node_id,
            dict(
                scene_id=scene_id,
                node_id=node_id,
                graph_version=graph.graph_version,
                relation=relation,
                source="planner_suggestion",
                evidence_refs=[],
            ),
        )
        link["evidence_refs"].append({**reference, **mention, "rule_version": LINK_RULE_VERSION})
    return list(by_node.values())


async def suggest_node_links(
    db: AsyncSession,
    owner_id: UUID,
    course_id: UUID,
    plan_id: UUID,
    *,
    graph_version: str,
) -> dict[str, Any]:
    """Use exact stored text only; absence/unavailable graph is not a learning failure.

    A mention is a suggestion, not semantic proof of a target, user selection or scoring
    eligibility. V1 deliberately leaves synonyms/uncertain paraphrases unmapped.
    """
    repo = SnapshotRepository(db, owner_id)
    course = await repo.get_course(course_id)
    plan = await repo.get_plan(course_id, plan_id)
    try:
        graph = graph_repository_for_version(graph_version)
    except KnowledgeGraphValidationError:
        return {"status": "graph_unavailable", "graph_version": graph_version, "links": []}
    goal = course["original_goal"]
    links = _links(
        graph,
        goal,
        None,
        dict(
            kind="original_goal",
            course_id=str(course_id),
            text_digest=digest("graph-link-text", text=goal),
        ),
        "target",
    )
    for scene in plan["scenes"]:
        combined: dict[str, dict[str, Any]] = {}
        for field in ("title", "purpose"):
            if not isinstance(scene.get(field), str):
                continue  # Historical private plans may omit optional teaching fields.
            for link in _links(
                graph,
                scene[field],
                scene["scene_id"],
                dict(
                    kind="plan_scene",
                    plan_id=str(plan_id),
                    plan_digest=plan["digest"],
                    field=field,
                    scene_id=scene["scene_id"],
                ),
                "supporting",
            ):
                if link["node_id"] in combined:
                    combined[link["node_id"]]["evidence_refs"].extend(link["evidence_refs"])
                else:
                    combined[link["node_id"]] = link
        links.extend(combined.values())
    return {
        "status": "suggested" if links else "no_match",
        "graph_version": graph_version,
        "links": links,
    }


async def commit_linked_manifest(
    db: AsyncSession,
    owner_id: UUID,
    course_id: UUID,
    fence: WriteFence,
    *,
    plan_id: UUID,
    expected_head: int | None,
    bindings: list[UUID | None],
    key: str,
    graph_version: str,
) -> dict[str, Any]:
    """Derive optional links from owned immutable snapshots, then use the existing CAS.

    Caller owns commit/rollback. No links are attached later to an existing manifest.
    """
    suggestions = await suggest_node_links(
        db, owner_id, course_id, plan_id, graph_version=graph_version
    )
    return await SnapshotRepository(db, owner_id).commit_manifest(
        course_id,
        fence,
        plan_id=plan_id,
        expected_head=expected_head,
        bindings=bindings,
        key=key,
        node_links=suggestions["links"],
    )


def _path_suggestions(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for link in links:
        identity = (link["graph_version"], link["node_id"])
        if link["relation"] != "target" or identity in seen:
            continue
        seen.add(identity)
        try:
            graph = graph_repository_for_version(link["graph_version"])
            decision = plan_learning_path(graph, target_node_id=link["node_id"], mastery={})
        except (KnowledgeGraphValidationError, PathRuleError):
            continue
        result.append(
            dict(
                kind="suggestion",
                graph_version=graph.graph_version,
                target_node_id=decision.target_node_id,
                rule_version=decision.rule_version,
                suggested_start_node_id=decision.current_node_id,
                nodes=[
                    dict(
                        node_id=step.node_id,
                        mastery_known=False,
                        reason=dict(
                            kind="suggested_target"
                            if step.node_id == decision.target_node_id
                            else "graph_prerequisite",
                            target_node_id=decision.target_node_id,
                        ),
                    )
                    for step in decision.steps
                ],
            )
        )
    return result


async def read_graph_context(
    db: AsyncSession,
    owner_id: UUID,
    course_id: UUID,
    *,
    version: int,
) -> dict[str, Any]:
    """Read exact historical links and derive suggestions, never replace goal/head/path.

    Internal context only. Future public projection must follow its API schema.
    """
    repo = SnapshotRepository(db, owner_id)
    course = await repo.get_course(course_id)
    manifest = await repo.get_version(course_id, version)
    return dict(
        course_id=str(course_id),
        course_version=manifest["version"],
        original_goal=course["original_goal"],
        node_links=manifest["node_links"],
        scoring_eligible=False,
        recommended_paths=_path_suggestions(manifest["node_links"]),
    )
