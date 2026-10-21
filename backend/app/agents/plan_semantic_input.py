"""Semantic-only plan view; binding metadata remains in the server audit."""

from copy import deepcopy
from typing import Any

from app.agents.review_input import review_input
from app.models.learning_plan import LearningPlanVersion
from app.services.plan_check import anchor_text

PLAN_SEMANTIC_INPUT_VERSION = "plan-semantic-input-v1"
SEMANTIC_PLAN_FIELDS = (
    "goal",
    "code_language",
    "objectives",
    "conventions",
    "shared_example",
    "scenes",
    "terminology",
    "prerequisite_node_ids",
)


def semantic_plan(plan: dict[str, Any]) -> dict[str, Any]:
    # Select structural carriers. Never regex-redact user text, code or example values.
    return {key: deepcopy(plan[key]) for key in SEMANTIC_PLAN_FIELDS if key in plan}


def semantic_input(
    plan: LearningPlanVersion,
    binding: dict[str, Any],
    anchors: list[dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    view, available = review_input(
        {"plan": plan.plan_json, "reference_context": plan.input_snapshot.get("reference_context")},
        binding,
        plan.input_snapshot,
    )
    goal = view["authoritative_teaching_goal"]
    reference = view["reference_context"]
    teaching = view.get("current_segment_scope")
    scoped = (
        None
        if teaching is None
        else {
            k: deepcopy(teaching[k])
            for k in ("teaching_mode", "original_request", "segment_goal", "segment_scope")
            if k in teaching
        }
    )
    projected = semantic_plan(plan.plan_json)
    data = dict(
        input_contract=PLAN_SEMANTIC_INPUT_VERSION,
        authoritative_teaching_goal={
            "source_role": "bound_original_user_request",
            "user_request": goal["user_request"],
            "plan_commitments": {
                k: deepcopy(projected.get(k)) for k in ("goal", "objectives", "scenes")
            },
            "background_is_not_a_commitment": True,
            "full_node_rule": goal["full_node_rule"],
        },
        current_segment_scope=scoped,
        learner_review_context={
            k: deepcopy(v) for k, v in view["learner_review_context"].items() if k != "version"
        },
        unverified_plan=projected,
        relevant_references={
            "source_role": "bound_background_reference",
            "node": deepcopy(reference["node"]),
            "explicitly_requested_objective_references": deepcopy(
                reference["explicitly_requested_objective_references"]
            ),
            "scope": reference["scope"],
            "complete_node_objective_catalog_supplied": reference[
                "complete_node_objective_catalog_supplied"
            ],
        },
        # Complete immutable pointer/digest/range is persisted separately, not put in the prompt.
        anchor_catalog=[
            dict(
                anchor_id=a["anchor_id"],
                source_kind=a["source_kind"],
                source_field=a["json_pointer"],
                source_text=anchor_text(plan, a),
            )
            for a in anchors
        ],
    )
    return data, available
