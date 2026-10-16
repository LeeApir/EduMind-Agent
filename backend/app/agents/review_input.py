"""Project bound server inputs for review without changing the audited publication material."""

from copy import deepcopy
from typing import Any

from app.services.learning_contract import LearningContractError, canonical, digest

REVIEW_INPUT_VERSION = "authoritative-review-input-v1"


def review_input(
    payload: dict[str, Any], binding: dict[str, Any], input_snapshot: dict[str, Any] | None
) -> tuple[dict[str, Any], bool]:
    """No NL goal classifier: exact user words and plan promises remain separate evidence."""
    available = input_snapshot is not None
    if (
        available
        and digest("input", "learning-input-v1", snapshot=input_snapshot) != binding["input_digest"]
    ):
        raise LearningContractError("REVIEW_INPUT_BINDING_MISMATCH")
    snapshot = input_snapshot or {}
    metadata = snapshot.get("metadata", {})
    goal = metadata.get("goal") if isinstance(metadata, dict) else None
    available = available and isinstance(goal, str) and bool(goal.strip())
    original_reference = payload.get("reference_context")
    if "reference_context" in snapshot and canonical(snapshot["reference_context"]) != canonical(
        original_reference
    ):
        raise LearningContractError("REVIEW_REFERENCE_BINDING_MISMATCH")
    # Only known input carriers are forwarded. Candidate data cannot mint server authority.
    data = {k: deepcopy(payload[k]) for k in ("unit", "plan", "candidate") if k in payload}
    unit = data.get("unit")
    plan = unit.get("plan", {}) if isinstance(unit, dict) else data.get("plan", {})
    if not isinstance(plan, dict):
        plan = {}
    if plan and digest("plan", "learning-plan-v1", plan=plan) != binding["plan_digest"]:
        raise LearningContractError("REVIEW_PLAN_BINDING_MISMATCH")
    reference = original_reference if isinstance(original_reference, dict) else {}
    node = reference.get("node", {})
    node = node if isinstance(node, dict) else {}
    # Description is correctness context, not a required lesson. No generic curricular
    # objectives, misconceptions, difficulty, recommendations or ai_context are forwarded.
    source: Any = deepcopy(reference.get("source"))
    if isinstance(source, dict):
        source = {k: source[k] for k in ("reference_id", "version", "digest") if k in source}
    view = {
        "source": source,
        "node": {k: deepcopy(node[k]) for k in ("id", "name", "description") if k in node},
        "learner_evidence": deepcopy(
            snapshot.get("learner_evidence", reference.get("learner_evidence", {}))
        ),
        "explicitly_requested_objective_references": [
            item
            for item in node.get("learning_objectives", [])
            if isinstance(item, str) and available and isinstance(goal, str) and item in goal
        ],
        "scope": (
            "Selected background for correctness, not additional teaching requirements or proof."
        ),
        "complete_node_objective_catalog_supplied": False,
    }
    # Close the duplicate nested route too. Keep all student content/actions/plan promises.
    if isinstance(unit, dict):
        unit["reference_context"] = deepcopy(view)
    data["reference_context"] = view
    data["authoritative_teaching_goal"] = {
        "version": REVIEW_INPUT_VERSION,
        "status": "bound_original_request" if available else "unavailable",
        "source": "LearningPlanVersion.input_snapshot.metadata.goal",
        "input_digest": binding["input_digest"],
        "user_request": goal if available else None,
        "plan_commitments": {
            "goal": plan.get("goal"),
            "objectives": deepcopy(plan.get("objectives", [])),
            "scenes": deepcopy(plan.get("scenes", [])),
        },
        "background_is_not_a_commitment": True,
        "full_node_rule": "If user or unit explicitly promises full-node coverage, "
        "check that promise. "
        "A narrower plan cannot replace it. If this view cannot substantiate "
        "complete coverage, state the gap/uncertainty; never silently pass it.",
    }
    data["media_requirements"] = {
        "rule": "Missing animation is relevant only if this unit explicitly promises animation.",
        "commitment_sources": [
            "bound user_request",
            "plan commitments",
            "actual student-facing promises",
        ],
        "background_suggestions_are_commitments": False,
        "unsolicited_animation_absence_is_unresolved": False,
        "verified_animation_evidence_supplied": False,
        "assessment": "Read explicit promises in the supplied content. "
        "No automatic NL classification "
        "or assertion of media delivery is made by this projection.",
    }
    data["review_input_audit"] = {
        "version": REVIEW_INPUT_VERSION,
        "original_reference_digest": digest(
            "review-reference", REVIEW_INPUT_VERSION, context=original_reference
        ),
        "original_material_digest": digest(
            "review-material", REVIEW_INPUT_VERSION, material=payload
        ),
        "projection_is_publication_material": False,
        "full_reference_retained_server_side": snapshot.get("reference_context") is not None,
        "all_actual_content_requires_fact_and_safety_review": True,
    }
    return data, bool(available)
