"""Trusted teaching actions contain references only, never generated speech or code."""

from copy import deepcopy
from typing import Any

from app.agents.learning_resource_schema import validate_learning_resource
from app.agents.planned_scene_generation import SceneCandidate
from app.services.learning_contract import ROLES, LearningContractError, canonical, digest

ACTION_VERSION = "teaching-actions-v1"


def anchor_catalog(candidates: tuple[SceneCandidate, ...]) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []

    def visit(value: object, pointer: str, candidate: SceneCandidate) -> None:
        if isinstance(value, str) and value:
            anchors.append(
                {
                    "anchor_id": f"a{len(anchors) + 1}",
                    "resource_id": candidate.id,
                    "resource_digest": candidate.content_digest,
                    "json_pointer": pointer,
                    "start_utf8": 0,
                    "end_utf8": len(value.encode("utf-8")),
                }
            )
        elif isinstance(value, dict):
            for key in sorted(value):
                visit(
                    value[key],
                    pointer + "/" + str(key).replace("~", "~0").replace("/", "~1"),
                    candidate,
                )
        elif isinstance(value, list):
            for i, item in enumerate(value):
                visit(item, pointer + "/" + str(i), candidate)

    for candidate in candidates:
        visit(candidate.envelope["content"], "", candidate)
    if not anchors or len(anchors) > 512:
        raise LearningContractError("ANCHOR_LIMIT_EXCEEDED")
    return anchors


def assemble_actions(candidates: tuple[SceneCandidate, ...]) -> dict[str, Any]:
    if tuple(c.role for c in candidates) != ROLES or len({c.id for c in candidates}) != 3:
        raise LearningContractError("INCOMPLETE_SCENES")
    catalog = anchor_catalog(candidates)
    actions: list[dict[str, Any]] = []
    for c in candidates:
        validate_learning_resource(c.envelope, expected_type=c.role)
        if c.content_digest != digest(
            "resource",
            str(c.envelope["prompt_version"]),
            resource_type=c.role,
            content=c.envelope["content"],
            prompt_version=c.envelope["prompt_version"],
        ):
            raise LearningContractError("RESOURCE_DIGEST_MISMATCH")
        target = {"scene_key": c.role, "resource_id": c.id, "resource_digest": c.content_digest}
        actions.append({"kind": "show_resource", **target})
        if c.role == "code":
            for a in catalog:
                if a["resource_id"] == c.id and a["json_pointer"].startswith("/key_steps/"):
                    actions.append({"kind": "highlight", **target, "anchor_id": a["anchor_id"]})
        if c.role == "exercise":
            for item in c.envelope["content"]["items"]:
                actions.append({"kind": "ask_exercise", **target, "exercise_id": item["id"]})
    payload = {"version": ACTION_VERSION, "actions": actions, "anchor_catalog": catalog}
    return deepcopy({**payload, "digest": digest("actions", ACTION_VERSION, payload=payload)})


def validate_actions(value: object, candidates: tuple[SceneCandidate, ...]) -> dict[str, Any]:
    expected = assemble_actions(candidates)
    if canonical(value) != canonical(expected):
        raise LearningContractError("ACTION_BINDING_INVALID")
    return expected
