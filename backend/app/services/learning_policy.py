"""Versioned local publication policy; changing its semantics invalidates pending cases."""

from app.services.learning_contract import digest

POLICY_VERSION = "hybrid-review-v1"
POLICY = {
    "resource_review": "resource-review-v4",
    "plan": "learning-plan-v1",
    "actions": "teaching-actions-v1",
    "max_corrections": 2,
    "max_formal_calls": 20,
    "max_with_temporary_calls": 22,
    "model_deadline_seconds": 180,
    "human_requires_complete_unit": True,
    "hard_gate_override": False,
}


def active_policy_digest() -> str:
    return digest("policy", POLICY_VERSION, policy=POLICY)
