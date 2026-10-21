"""Complete immutable publication candidate, independent of review conclusions."""

from copy import deepcopy
from typing import Any

from app.agents.planned_scene_generation import PlannedScenes, SceneCandidate
from app.services.learning_contract import (
    ROLES,
    LearningContractError,
    canonical,
    digest,
    validate_contract,
)
from app.services.teaching_actions import validate_actions


def unit_material(
    workspace: PlannedScenes, scenes: list[dict[str, Any]], actions: object
) -> dict[str, Any]:
    candidates = workspace.candidates()
    action_value = validate_actions(actions, candidates)
    if len(scenes) != 3:
        raise LearningContractError("INCOMPLETE_SCENES")
    for index, (scene, c) in enumerate(zip(scenes, candidates, strict=True)):
        validate_contract(scene, "scene_binding")
        if (
            scene["role"] != ROLES[index]
            or scene["scene_key"] != c.role
            or scene["resource_id"] != c.id
            or scene["resource_digest"] != c.content_digest
            or scene["dependency_digest"] != c.dependency_digest
        ):
            raise LearningContractError("SCENE_BINDING_INVALID")
        expected_upstream = tuple(
            {
                "resource_id": p.id,
                "content_digest": p.content_digest,
                "dependency_digest": p.dependency_digest,
            }
            for p in candidates[:index]
        )
        if c.upstream != expected_upstream or c.dependency_digest != digest(
            "dependency",
            "scene-dependency-v1",
            binding=workspace.binding,
            upstream=expected_upstream,
        ):
            raise LearningContractError("DEPENDENCY_BINDING_INVALID")
    if len({s["scene_id"] for s in scenes}) != 3:
        raise LearningContractError
    frozen = {
        "binding": deepcopy(workspace.binding),
        "plan": deepcopy(workspace.plan),
        "candidates": [c.payload() for c in candidates],
        "scenes": deepcopy(scenes),
        "actions": action_value,
        "reference_context": deepcopy(workspace.reference_context),
    }
    context = workspace.teaching_context
    if context is not None:
        frozen["teaching_context"] = deepcopy(context)
    if len(canonical(frozen)) > 64 * 1024:
        raise LearningContractError("UNIT_INPUT_LIMIT_EXCEEDED")
    frozen["unit_digest"] = digest(
        "unit",
        "learning-publication-v2" if context is not None else "learning-publication-v1",
        binding=workspace.binding,
        scenes=scenes,
        actions_version=action_value["version"],
        actions_digest=action_value["digest"],
        **({"teaching_context": context} if context is not None else {}),
    )
    return frozen


def restore_material(value: dict[str, Any]) -> tuple[PlannedScenes, dict[str, Any]]:
    if "teaching_context" in value:
        from app.services.teaching_binding import validate_teaching_context

        validate_teaching_context(value["teaching_context"])
    workspace = PlannedScenes(
        value["plan"],
        value["binding"],
        reference_context=value["reference_context"],
        teaching_context=value.get("teaching_context"),
    )
    # Restore server-issued immutable candidates; stage() would allocate new identities.
    for item in value["candidates"]:
        c = SceneCandidate(
            item["resource_id"],
            item["role"],
            deepcopy(item["envelope"]),
            item["content_digest"],
            item["dependency_digest"],
            tuple(item["upstream"]),
        )
        workspace._candidates[c.role] = c
    expected = unit_material(workspace, value["scenes"], value["actions"])
    if canonical(value) != canonical(expected):
        raise LearningContractError("UNIT_DIGEST_MISMATCH")
    return workspace, expected
