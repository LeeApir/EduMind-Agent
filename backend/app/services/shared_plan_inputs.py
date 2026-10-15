"""Build truthful source context from the versioned graph and existing profile only."""

import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.shared_learning_plan import PlanInputs
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.learning_contract import LearningContractError, digest
from app.services.owned_learning import latest_profile


async def shared_plan_inputs(
    db: AsyncSession,
    *,
    owner_id: UUID,
    node_id: str,
    goal: str,
    language: str,
    graph: KnowledgeGraphRepository,
) -> PlanInputs:
    node = graph.get_node(node_id)
    code_language = {"c": "C", "C": "C", "python": "Python", "Python": "Python"}.get(language)
    if node is None or code_language is None:
        raise LearningContractError("PLAN_INPUT_INVALID")
    profile = await latest_profile(db, owner_id)
    evidence: dict[str, Any] = (
        {}
        if profile is None
        else {
            "knowledge_base": profile.knowledge_base,
            "error_preferences": profile.error_preferences,
            "evidence": profile.evidence,
        }
    )
    # Legacy profile evidence uses numeric confidence. Preserve it losslessly as JSON text
    # inside the integer/string-only minimum contract rather than guessing missing fields.
    evidence = {
        "snapshot_json": json.dumps(evidence, ensure_ascii=False, sort_keys=True, allow_nan=False)
    }
    source = asdict(node)
    rid = f"graph-node:{graph.graph_version}:{node.id}"
    reference = {
        "reference_id": rid,
        "version": graph.graph_version,
        "digest": digest("graph-node", "graph-reference-v1", node=source),
    }
    context: dict[str, Any] = {
        "source": reference,
        "node": source,
        "learner_evidence": evidence,
        "scope": (
            "Partial versioned graph reference; not proof of arbitrary code or unsupported facts."
        ),
    }
    return PlanInputs(
        metadata={
            "node_id": node.id,
            "graph_version": graph.graph_version,
            "graph_digest": digest(
                "graph", "graph-snapshot-v1", nodes=[asdict(n) for n in graph.all_nodes()]
            ),
            "profile_version": profile.version if profile else None,
            "profile_evidence_digest": digest(
                "profile-evidence", "profile-evidence-v1", evidence=evidence
            ),
            "goal": goal,
            "code_language": code_language,
        },
        references={rid: reference},
        node_ids=frozenset(n.id for n in graph.all_nodes()),
        learner_evidence=evidence,
        reference_context=context,
    )
