"""Learner evidence rules: unknown fields are not evidence of difficulty or mastery."""

from copy import deepcopy
from typing import Any

LEARNER_REVIEW_VERSION = "learner-evidence-review-v1"
LEARNER_INSTRUCTION = """
learner_fit checks grounded constraints and claims, not guaranteed suitability or learning
outcomes for a particular student. Use learner_review_context and the bound original request
as evidence carriers. An empty profile, no quiz history, unknown preference/mastery, an
explicit beginner background, or a general prerequisite reminder alone is NOT a reason for
unchecked, unresolved or needs_human. Complete the check for no invented personalization and
no conflict with known constraints; do not skip learner_fit or invent evidence to fill it.
Self-reported prior study is not demonstrated mastery, difficulty or preference. Keep both
conflicting evidence sources; do not silently overwrite one or infer actual mastery from a
statement about having studied. A general warning is not a claim that this student has that
problem. Actual claims such as 'you often confuse pointers' require evidence. Without it,
identify the exact unsupported personalization and required correction/evidence in unresolved
and needs_human, not a fabricated fact/difficulty finding. Unknown does not imply false.
A provably false attribution to the student's exact words is separately reportable as fact.
If a concrete judgment actually relies on missing/conflicting learner facts, state precisely
which premise is needed and how it changes that judgment. Do not turn every unknown learner
field into a publishing blocker. Keep serious rejection and all content/safety checks.
"""


def learner_review_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    evidence = {}
    source = {}
    if "learner_evidence" in snapshot:
        evidence["input_snapshot"] = deepcopy(snapshot["learner_evidence"])
        source["input_snapshot"] = "LearningPlanVersion.input_snapshot.learner_evidence"
    reference = snapshot.get("reference_context")
    if isinstance(reference, dict) and "learner_evidence" in reference:
        evidence["reference_context"] = deepcopy(reference["learner_evidence"])
        source["reference_context"] = (
            "LearningPlanVersion.input_snapshot.reference_context.learner_evidence"
        )
    return {
        "version": LEARNER_REVIEW_VERSION,
        "evidence": evidence,
        "source": source,
        "self_report_is_mastery": False,
        "unknown_alone_blocks_publication": False,
        "unsupported_personalization_requires_resolution": True,
    }
