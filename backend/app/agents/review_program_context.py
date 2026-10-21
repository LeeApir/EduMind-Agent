"""Locate supplied program evidence; never infer a snippet's function or caller scope."""

from typing import Any

from app.agents.planned_scene_generation import SceneCandidate
from app.agents.review_delivery import delivery_manifest
from app.services.learning_contract import LearningContractError

PROGRAM_CONTEXT_VERSION = "review-program-context-v1"
PROGRAM_CONTEXT_INSTRUCTION = """
For a claim about whether a pointer assignment updates the caller, first resolve the
program_context source locations. Read the actual function parameter declaration and call
site, and the assignment inside that function; cite the anchors supplying those premises.
A standalone explanation fragment does not establish a by-value function parameter or any
caller. Co-supplied code can clarify its implementation but is not proof that a separate
fragment has the same scope. If the needed function/caller boundary is absent or cannot be
related, name that missing premise in unresolved rather than asserting a caller is left
dangling. This does not excuse a separately demonstrated unsafe operation. The index only
locates supplied fields; it neither parses C nor certifies completeness, safety or coverage.
"""


def program_context(
    payload: dict[str, Any], candidates: tuple[SceneCandidate, ...], catalog: list[dict[str, Any]]
) -> dict[str, Any]:
    located = delivery_manifest(payload, candidates)
    if located["unindexed_candidate_ids"]:
        raise LearningContractError("REVIEW_PROGRAM_CONTEXT_UNBOUND")
    paths = {item["resource_id"]: item["content_pointer"] for item in located["resources"]}
    by_id = {candidate.id: candidate for candidate in candidates}
    sources: list[dict[str, Any]] = []
    other_claims: list[dict[str, Any]] = []
    for anchor in catalog:
        candidate = by_id.get(anchor["resource_id"])
        if candidate is None or anchor["resource_digest"] != candidate.content_digest:
            raise LearningContractError("REVIEW_PROGRAM_CONTEXT_UNBOUND")
        pointer = anchor["json_pointer"]
        if candidate.role == "code" and pointer == "/source":
            target = sources
        elif (
            candidate.role == "explanation"
            and pointer == "/markdown"
            or (candidate.role == "exercise" and pointer.endswith(("/question", "/explanation")))
        ):
            target = other_claims
        else:
            continue
        target.append(
            {
                "resource_id": candidate.id,
                "resource_digest": candidate.content_digest,
                "anchor_id": anchor["anchor_id"],
                "content_pointer": paths[candidate.id] + pointer,
                "anchor_pointer": pointer,
            }
        )
    return {
        "version": PROGRAM_CONTEXT_VERSION,
        "availability": "whole_unit_supplied" if "unit" in payload else "selected_resource_only",
        "code_source_fields": sources,
        "other_claim_fields": other_claims,
        "scope_or_call_relationship_inferred": False,
        "source_completeness_or_safety_certified": False,
    }
