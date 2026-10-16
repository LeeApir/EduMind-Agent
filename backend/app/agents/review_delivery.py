"""Index actual candidate content; never treat internal context as delivered teaching."""

from typing import Any

from app.agents.planned_scene_generation import SceneCandidate
from app.services.learning_contract import canonical

COVERAGE_STANDARD_VERSION = "student-visible-goal-coverage-v1"


def delivery_manifest(
    payload: dict[str, Any], candidates: tuple[SceneCandidate, ...]
) -> dict[str, Any]:
    """References only, without duplicating resource text or judging semantic coverage."""
    locations: list[tuple[str, object]] = []
    unit = payload.get("unit")
    if isinstance(unit, dict) and isinstance(unit.get("candidates"), list):
        locations.extend((f"/unit/candidates/{i}", c) for i, c in enumerate(unit["candidates"]))
    if isinstance(payload.get("candidate"), dict):
        locations.append(("/candidate", payload["candidate"]))
    resources = []
    for c in candidates:
        pointer = next(
            (path for path, body in locations if canonical(body) == canonical(c.payload())), None
        )
        if pointer is None:
            continue  # Do not invent a content location from a plan, ID or digest.
        fields = {
            "explanation": ["markdown"],
            "code": ["source", "expected_output", "key_steps"],
            "exercise": ["items/*/question", "items/*/explanation"],
        }[c.role]
        resources.append(
            {
                "resource_id": c.id,
                "role": c.role,
                "resource_digest": c.content_digest,
                "content_pointer": pointer + "/envelope/content",
                "teaching_fields": fields,
                "availability": "questions before submission; explanations in feedback"
                if c.role == "exercise"
                else "formal resource view after publication",
            }
        )
    return {
        "version": COVERAGE_STANDARD_VERSION,
        "meaning": (
            "candidate content intended for the student after publication, not already published"
        ),
        "resources": resources,
        "unindexed_candidate_ids": [
            c.id for c in candidates if c.id not in {r["resource_id"] for r in resources}
        ],
        "internal_only": ["plan", "reference_context", "actions as references without content"],
        "verified_animation_evidence": (
            "not supplied in this three-resource request; never infer from a plan or placeholder"
        ),
        "semantic_coverage_assessed_by_this_index": False,
    }
