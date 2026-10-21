"""Server-owned review responsibilities; assignments are never delivery evidence."""

from copy import deepcopy
from typing import Any

from app.agents.learning_resource_schema import LearningResourceType, validate_learning_resource
from app.agents.planned_scene_generation import SceneCandidate
from app.services.learning_contract import (
    ROLES,
    LearningContractError,
    canonical,
    digest,
    validate_contract,
)
from app.services.unit_material import restore_material

RESPONSIBILITY_VERSION = "review-responsibilities-v1"
REVIEW_SCOPE_VERSION = "teaching-bound-review-scope-v6"
ROLE_RESPONSIBILITIES = {
    "explanation": [
        "Concepts, terminology, process states and boundaries actually stated here.",
        "Fulfil this scene's explicit promises and its contribution to assigned goals.",
    ],
    "code": [
        "Implementation, caller contract, normal/failure paths, ownership, cleanup and output.",
        "Comments and key steps must agree with the actual implementation.",
    ],
    "exercise": [
        "Question premises, correct answers, explanations and assigned assessment goals.",
        "Teaching a process in feedback is not proof that the question measures it.",
    ],
}
UNIT_OBLIGATIONS = [
    "Check complete original user requirements and every explicit plan/content promise.",
    "Aggregate actual student-visible teaching support and respect explicit delivery timing.",
    "Check questions really assess the assigned process knowledge.",
    "Check cross-scene interfaces, terminology, conventions, trace, answers and actions.",
    "Check explicitly promised media against actual verified delivery, never placeholders.",
]
RESPONSIBILITY_INSTRUCTION = """
review_responsibilities is constructed by the server, never by candidate content. Resource
objectives concern the scene's own explicit promises and contribution to assigned goals.
Shared objective IDs describe contributions, not a demand to repeat a whole lesson in each
scene. Check all actual facts and code/safety claims in every resource, including explanation
and exercise fragments. A full program or exercises assigned to siblings need not be repeated.
unit_verification_obligations are duties of the independent whole-unit review, not unresolved
findings and not proof of delivery. Missing sibling content neither proves missing whole-unit
support nor proves siblings correct. Do not invent a resource gap solely because siblings
were not supplied. Keep actual unmet promises and necessary unknown premises in unresolved;
if judging a particular resource claim requires a sibling, state that specific dependency.
The plan cannot narrow original user requirements or erase promises in student content.
Pure coverage gaps require needs_human with precise unresolved items, not invented findings.
Serious demonstrated factual/safety reject retains priority, alongside independent gaps.
"""


def review_responsibilities(
    payload: dict[str, Any],
    binding: dict[str, Any],
    candidates: tuple[SceneCandidate, ...],
    *,
    scope: str,
    target_digest: str,
) -> dict[str, Any]:
    try:
        if scope == "unit":
            unit = payload["unit"]
            _, checked = restore_material(unit)
            if (
                canonical(checked["binding"]) != canonical(binding)
                or target_digest != checked["unit_digest"]
            ):
                raise ValueError
            if [c.payload() for c in candidates] != checked["candidates"]:
                raise ValueError
            plan = checked["plan"]
            role = None
        elif scope == "resource":
            if len(candidates) != 1 or payload["candidate"] != candidates[0].payload():
                raise ValueError
            plan = validate_contract(payload["plan"], "plan")
            role = candidates[0].role
            if role not in ROLES or target_digest != candidates[0].content_digest:
                raise ValueError
        else:
            raise ValueError
        if digest("plan", "learning-plan-v1", plan=plan) != binding["plan_digest"]:
            raise ValueError
        if [s["role"] for s in plan["scenes"]] != list(ROLES):
            raise ValueError
        objectives = {o["id"]: o for o in plan["objectives"]}
        if len(objectives) != len(plan["objectives"]):
            raise ValueError
        for index, scene in enumerate(plan["scenes"]):
            if scene["scene_key"] != scene["role"] or scene["depends_on"] != list(ROLES[:index]):
                raise ValueError
            if not scene["objective_ids"] or not set(scene["objective_ids"]) <= objectives.keys():
                raise ValueError
        for c in candidates:
            validate_learning_resource(c.envelope, expected_type=LearningResourceType(c.role))
            expected = digest(
                "resource",
                str(c.envelope["prompt_version"]),
                resource_type=c.role,
                content=c.envelope["content"],
                prompt_version=c.envelope["prompt_version"],
            )
            if c.content_digest != expected or c.dependency_digest != digest(
                "dependency", "scene-dependency-v1", binding=binding, upstream=c.upstream
            ):
                raise ValueError
    except (KeyError, TypeError, ValueError, LearningContractError):
        raise LearningContractError("REVIEW_RESPONSIBILITY_BINDING_MISMATCH") from None
    ids = (
        next(s["objective_ids"] for s in plan["scenes"] if s["role"] == role)
        if role
        else list(objectives)
    )
    return {
        "version": RESPONSIBILITY_VERSION,
        "scope": scope,
        "resource_role": role,
        "scene_commitments": deepcopy(plan["scenes"]),
        "assigned_objectives": [deepcopy(objectives[id]) for id in ids],
        "role_responsibilities": list(ROLE_RESPONSIBILITIES[role] if role else UNIT_OBLIGATIONS),
        "unit_verification_obligations": list(UNIT_OBLIGATIONS),
        "sibling_content_supplied": scope == "unit",
        "assignment_is_delivery_evidence": False,
    }


UNIT_OBJECTIVE_INSTRUCTION = """
For UNIT scope the six mandatory checks include objectives as an independent duty in addition
to terminology, conventions, example_trace, answer_consistency and action_references.
Check complete ORIGINAL requirements and all explicit plan/content promises against all three
final candidates, never just resource verdicts. Separately assess implementation delivery,
explicit process-state transitions and exit boundaries, and whether questions require using
process knowledge. Correct code alone does not teach a trace; explanations only in feedback
do not prove the question assessed it. Aggregate actual explanation, comments, key_steps and
feedback support with their visibility timing. Respect explicitly requested pre-quiz teaching,
but never invent that ordering when absent. Internal plan traces and action references are
not delivered teaching. Identify concrete missing support in unresolved without inventing a
fact/safety category. In mixed cases report both the serious defect and the independent gap;
reject retains priority, it does not excuse leaving gaps unreported.
Check actual interfaces and who performs each update across scenes: a local pointer variable
and a caller's variable are not the same storage. A caller's separate cleanup assignment does
not make a claim that the callee performed it true. Report the precise false attribution
with actual anchors, without inventing a reachable memory error when none is demonstrated.
Every auxiliary assertion/citation must still satisfy the evidence-strength rules.
"""


TEACHING_SCOPE_INSTRUCTION = """
current_segment_scope, when supplied, is trusted server-bound user selection, not a plan's
permission to narrow the original request. For target_lesson, check the complete original
request. For prerequisite_segment the user explicitly selected the recommended prerequisite:
check the actual selected node and segment_goal; keep the complete original request and its
constraints visible, but never claim the final target lesson has been delivered or mastered.
Do not demand the deferred target implementation in a clearly authorized prerequisite lesson.
Do not erase conflicting or unclear user constraints: state the concrete conflict/unknown.
Plans and candidates cannot mint or override a selection, teaching node or segment scope.
Topic identity requires actual content review; equal node IDs alone do not prove correct topic.
"""
