"""Versioned, whitelisted progressive-profile event schema for MVP P0."""

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Final

PROFILE_EVENT_SCHEMA_VERSION: Final = 1
PROFILE_MERGE_RULE_VERSION: Final = "profile-merge-v1"

PROFILE_EVENT_TYPES: Final = (
    "hint_used",
    "reexplanation_requested",
    "resource_selected",
    "explicit_feedback",
)

PROFILE_EVENT_ACTIONS_BY_TYPE: Final = {
    "hint_used": frozenset({"hint_level_1", "hint_level_2"}),
    "reexplanation_requested": frozenset({"simpler", "deeper", "different_example"}),
    "resource_selected": frozenset({"code", "exercise"}),
    "explicit_feedback": frozenset(
        {"too_easy", "too_hard", "liked_explanation", "skip", "mark_known"}
    ),
}

PROFILE_EVENT_ACTIONS: Final = frozenset(
    action for actions in PROFILE_EVENT_ACTIONS_BY_TYPE.values() for action in actions
)

_KNOWLEDGE_NODE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class ProfileEventSchemaError(ValueError):
    """Raised for invalid or unsupported profile events without echoing their contents."""

    def __init__(self) -> None:
        super().__init__("Profile event did not satisfy the supported schema.")


def validate_profile_event(value: object) -> dict[str, object]:
    """Validate a whitelisted behavior summary before it is persisted or merged."""
    if not isinstance(value, dict):
        raise ProfileEventSchemaError
    allowed = {"event_type", "knowledge_node_id", "learning_unit_id", "scene_id", "action"}
    if not set(value).issubset(allowed):
        raise ProfileEventSchemaError

    event_type = value.get("event_type")
    knowledge_node_id = value.get("knowledge_node_id")
    if not isinstance(event_type, str) or event_type not in PROFILE_EVENT_TYPES:
        raise ProfileEventSchemaError
    if not isinstance(knowledge_node_id, str) or not _KNOWLEDGE_NODE_ID_RE.fullmatch(
        knowledge_node_id
    ):
        raise ProfileEventSchemaError

    learning_unit_id = value.get("learning_unit_id")
    scene_id = value.get("scene_id")
    for identifier in (learning_unit_id, scene_id):
        if identifier is not None:
            if not isinstance(identifier, str) or not _IDENTIFIER_RE.fullmatch(identifier):
                raise ProfileEventSchemaError

    action = value.get("action")
    if action is not None:
        if not isinstance(action, str):
            raise ProfileEventSchemaError
        if action not in PROFILE_EVENT_ACTIONS_BY_TYPE[event_type]:
            raise ProfileEventSchemaError

    return {
        "event_type": event_type,
        "knowledge_node_id": knowledge_node_id,
        "learning_unit_id": learning_unit_id,
        "scene_id": scene_id,
        "action": action,
    }


def event_payload(
    *,
    event_type: str,
    knowledge_node_id: str,
    learning_unit_id: str | None = None,
    scene_id: str | None = None,
    action: str | None = None,
) -> dict[str, object]:
    """Build a canonical event request; callers validate before persisting."""
    payload: dict[str, object] = {
        "event_type": event_type,
        "knowledge_node_id": knowledge_node_id,
    }
    if learning_unit_id is not None:
        payload["learning_unit_id"] = learning_unit_id
    if scene_id is not None:
        payload["scene_id"] = scene_id
    if action is not None:
        payload["action"] = action
    return payload


def event_digest(event: Mapping[str, object]) -> str:
    """Canonical digest so an owner cannot reuse an idempotency key for another event."""
    value = json.dumps(
        dict(event), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(value.encode()).hexdigest()
