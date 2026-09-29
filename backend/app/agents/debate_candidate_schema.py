"""Versioned candidate contract for the P0 array versus linked-list demonstration."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Final, cast

DEBATE_CANDIDATE_SCHEMA_VERSION: Final = "array-vs-linked-list-candidate-v1"
DEBATE_NODE_IDS: Final = ("array", "single-linked-list")
DEBATE_PERSPECTIVES: Final = ("performance", "engineering", "academic")


class DebateCandidateSchemaError(ValueError):
    """A safe format error that never includes generated text."""

    def __init__(self) -> None:
        super().__init__("Debate candidate did not satisfy the supported schema.")


def _object(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise DebateCandidateSchemaError
    return cast(dict[str, object], value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise DebateCandidateSchemaError
    return value.strip()


def _items(value: object, *, minimum: int = 0, maximum: int = 6) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise DebateCandidateSchemaError
    items = [_text(item) for item in value]
    if len(set(items)) != len(items):
        raise DebateCandidateSchemaError
    return items


def validate_debate_candidate(value: object) -> dict[str, object]:
    """Require all roles and keep algorithm conclusions separate from learner advice."""
    root = _object(value, {
        "schema_version", "question_conditions", "graph_refs", "perspectives", "moderator",
    })
    if root["schema_version"] != DEBATE_CANDIDATE_SCHEMA_VERSION:
        raise DebateCandidateSchemaError
    conditions = _object(root["question_conditions"], {"stated", "unknown"})
    stated = _items(conditions["stated"])
    unknown = _items(conditions["unknown"])
    refs = _items(root["graph_refs"], minimum=2, maximum=2)
    if set(refs) != set(DEBATE_NODE_IDS):
        raise DebateCandidateSchemaError
    perspectives = _object(root["perspectives"], set(DEBATE_PERSPECTIVES))
    validated_perspectives = {role: _text(perspectives[role]) for role in DEBATE_PERSPECTIVES}
    moderator = _object(root["moderator"], {"objective_conclusion", "tradeoffs", "learner_advice"})
    return deepcopy({
        "schema_version": DEBATE_CANDIDATE_SCHEMA_VERSION,
        "question_conditions": {"stated": stated, "unknown": unknown},
        "graph_refs": list(DEBATE_NODE_IDS),
        "perspectives": validated_perspectives,
        "moderator": {
            "objective_conclusion": _text(moderator["objective_conclusion"]),
            "tradeoffs": _text(moderator["tradeoffs"]),
            "learner_advice": _text(moderator["learner_advice"]),
        },
    })


def _string_list(*, minimum: int = 0, maximum: int = 6) -> dict[str, object]:
    return {"type": "array", "minItems": minimum, "maxItems": maximum,
            "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 4000}}


def debate_candidate_output_schema() -> Mapping[str, object]:
    """Strict provider-facing JSON schema for one complete candidate."""
    return {
        "type": "object", "additionalProperties": False,
        "required": [
            "schema_version", "question_conditions", "graph_refs", "perspectives", "moderator",
        ],
        "properties": {
            "schema_version": {"const": DEBATE_CANDIDATE_SCHEMA_VERSION},
            "question_conditions": {
                "type": "object", "additionalProperties": False,
                "required": ["stated", "unknown"],
                "properties": {"stated": _string_list(), "unknown": _string_list()},
            },
            "graph_refs": {
                "type": "array", "minItems": 2, "maxItems": 2, "uniqueItems": True,
                "items": {"type": "string", "enum": list(DEBATE_NODE_IDS)},
            },
            "perspectives": {
                "type": "object", "additionalProperties": False,
                "required": list(DEBATE_PERSPECTIVES),
                "properties": {role: {"type": "string", "minLength": 1, "maxLength": 4000}
                               for role in DEBATE_PERSPECTIVES},
            },
            "moderator": {
                "type": "object", "additionalProperties": False,
                "required": ["objective_conclusion", "tradeoffs", "learner_advice"],
                "properties": {
                    field: {"type": "string", "minLength": 1, "maxLength": 4000}
                    for field in ("objective_conclusion", "tradeoffs", "learner_advice")
                },
            },
        },
    }
