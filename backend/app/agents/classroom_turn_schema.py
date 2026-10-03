"""Versioned single-Tutor classroom turn contract with deterministic redundancy guards.

A turn is one orchestrated classroom action. The tutor leads exactly once; companion
roles (beginner/advanced) are optional and at most one utterance each. Two roles never
restate the same text, and no role speaks twice, which structurally prevents multiple
roles from rewriting identical content for the same knowledge point.
"""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Final

from app.agents.classroom_roles import ClassroomRole

TURN_PROMPT_VERSION: Final = "classroom-turn-v1"
_MAX_UTTERANCES: Final = 3
_ALLOWED_ROLES: Final = frozenset({role.value for role in ClassroomRole})


class TurnSchemaError(ValueError):
    """A stable schema failure that never reflects arbitrary model output."""

    def __init__(self) -> None:
        super().__init__("Classroom turn data did not satisfy the supported schema.")


def _require(condition: bool) -> None:
    if not condition:
        raise TurnSchemaError


def _nonempty_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TurnSchemaError
    return value.strip()


def _role(value: object) -> str:
    if not isinstance(value, str) or value not in _ALLOWED_ROLES:
        raise TurnSchemaError
    return value


def validate_classroom_turn(
    value: object, *, eligible_roles: Sequence[str]
) -> dict[str, object]:
    """Validate one turn: one tutor lead, unique roles, distinct text, eligible speakers.

    Companion utterances are optional; a tutor-only turn is valid in every mode. Every
    speaker must be within ``eligible_roles`` so focus mode can never emit a companion.
    """
    eligible = {_role(role) for role in eligible_roles}
    if ClassroomRole.TUTOR.value not in eligible:
        raise TurnSchemaError
    if not isinstance(value, dict) or set(value) != {"turn_version", "utterances"}:
        raise TurnSchemaError
    if value["turn_version"] != TURN_PROMPT_VERSION:
        raise TurnSchemaError
    utterances = value["utterances"]
    if not isinstance(utterances, list) or not 1 <= len(utterances) <= _MAX_UTTERANCES:
        raise TurnSchemaError
    validated: list[dict[str, str]] = []
    seen_roles: set[str] = set()
    seen_texts: set[str] = set()
    for item in utterances:
        if not isinstance(item, dict) or set(item) != {"role", "text"}:
            raise TurnSchemaError
        role = _role(item["role"])
        text = _nonempty_string(item["text"])
        if role not in eligible:
            raise TurnSchemaError
        if role in seen_roles:
            raise TurnSchemaError
        if text in seen_texts:
            raise TurnSchemaError
        seen_roles.add(role)
        seen_texts.add(text)
        validated.append({"role": role, "text": text})
    _require(ClassroomRole.TUTOR.value in seen_roles)
    return {"turn_version": TURN_PROMPT_VERSION, "utterances": deepcopy(validated)}


def classroom_turn_output_schema() -> Mapping[str, object]:
    """Return the JSON Schema supplied to the provider for one orchestrated turn."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["turn_version", "utterances"],
        "properties": {
            "turn_version": {"const": TURN_PROMPT_VERSION},
            "utterances": {
                "type": "array",
                "minItems": 1,
                "maxItems": _MAX_UTTERANCES,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["role", "text"],
                    "properties": {
                        "role": {"enum": sorted(_ALLOWED_ROLES)},
                        "text": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }
