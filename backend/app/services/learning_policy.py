"""Versioned local publication policy; changing its semantics invalidates pending cases."""

from app.agents.learner_review import LEARNER_REVIEW_VERSION
from app.agents.learning_resource_prompt import RESOURCE_INSTRUCTION_VERSION
from app.agents.plan_check import PLAN_CHECK_VERSION
from app.agents.planned_scene_generation import SCENE_PROMPT_VERSION
from app.agents.review_evidence import REVIEW_PROMPT_VERSION
from app.agents.review_input import REVIEW_INPUT_VERSION
from app.agents.review_program_context import PROGRAM_CONTEXT_VERSION
from app.agents.review_responsibilities import RESPONSIBILITY_VERSION, REVIEW_SCOPE_VERSION
from app.services.learning_contract import digest
from app.services.teaching_binding import TEACHING_BINDING_VERSION

POLICY_VERSION = "hybrid-review-v1"
POLICY = {
    "resource_review": "resource-review-v4",
    "resource_review_prompt": REVIEW_PROMPT_VERSION,
    "review_input": REVIEW_INPUT_VERSION,
    "review_program_context": PROGRAM_CONTEXT_VERSION,
    "objective_coverage": "student-visible-goal-coverage-v1",
    "review_coverage": "fixed-check-ids-v2",
    "review_scope": REVIEW_SCOPE_VERSION,
    "review_responsibilities": RESPONSIBILITY_VERSION,
    "learner_review": LEARNER_REVIEW_VERSION,
    "teaching_scope": TEACHING_BINDING_VERSION,
    "teaching_binding": TEACHING_BINDING_VERSION,
    "scene_generation_prompt": SCENE_PROMPT_VERSION,
    "exercise_generation_instructions": RESOURCE_INSTRUCTION_VERSION,
    "plan": "learning-plan-v1",
    "plan_check": PLAN_CHECK_VERSION,
    "plan_rebuild_prompt": "plan-rebuild-prompt-v1",
    "approved_plan_verifiers": [],
    "approved_plan_verifier_versions": {},
    "plan_evidence": "plan-check-record-v1",
    "learning_stage_routing": "learning-stage-v1",
    "actions": "teaching-actions-v1",
    "max_corrections": 2,
    "shared_budget": "learning-budget-v1",
    "shared_correction_pairs": {"without_rebuild": 5, "with_rebuild": 4},
    "structured_output_caps": {"mapping": 512, "plan": 2048, "resource": 4096, "review": 8192},
    "max_formal_calls": 20,
    "max_with_temporary_calls": 22,
    "model_deadline_seconds": 180,
    "human_requires_complete_unit": True,
    "hard_gate_override": False,
}


def active_policy_digest() -> str:
    return digest("policy", POLICY_VERSION, policy=POLICY)
