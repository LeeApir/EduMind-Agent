"""Strict, versioned output contracts for P0 learning resources."""

from collections.abc import Mapping
from copy import deepcopy
from enum import StrEnum
from typing import Final, cast

RESOURCE_PROMPT_VERSION: Final = "learning-resources-v1"


class LearningResourceType(StrEnum):
    EXPLANATION = "explanation"
    CODE = "code"
    EXERCISE = "exercise"


class ResourceSchemaError(ValueError):
    """A stable schema failure that never reflects arbitrary model output."""

    def __init__(self) -> None:
        super().__init__("Learning resource data did not satisfy the supported schema.")


def _require(condition: bool) -> None:
    if not condition:
        raise ResourceSchemaError


def _nonempty_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResourceSchemaError
    return value.strip()


def _strict_object(value: object, expected_keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ResourceSchemaError
    return cast(dict[str, object], value)


def _resource_type(value: LearningResourceType | str) -> LearningResourceType:
    try:
        return LearningResourceType(value)
    except ValueError:
        raise ResourceSchemaError from None


def _validate_explanation(content: object) -> dict[str, object]:
    object_content = _strict_object(content, {"markdown"})
    return {"markdown": _nonempty_string(object_content["markdown"])}


def _validate_code(content: object) -> dict[str, object]:
    expected = {"language", "source", "expected_output", "key_steps", "display_only"}
    object_content = _strict_object(content, expected)
    key_steps = object_content["key_steps"]
    if not isinstance(key_steps, list) or not 1 <= len(key_steps) <= 6:
        raise ResourceSchemaError
    _require(object_content["display_only"] is True)
    return {
        "language": _nonempty_string(object_content["language"]),
        "source": _nonempty_string(object_content["source"]),
        "expected_output": _nonempty_string(object_content["expected_output"]),
        "key_steps": [_nonempty_string(step) for step in key_steps],
        "display_only": True,
    }


def _validate_exercise(content: object) -> dict[str, object]:
    object_content = _strict_object(content, {"items"})
    items = object_content["items"]
    if not isinstance(items, list) or not 2 <= len(items) <= 4:
        raise ResourceSchemaError
    validated_items: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for item in items:
        object_item = _strict_object(item, {"id", "question", "answer", "explanation"})
        item_id = _nonempty_string(object_item["id"])
        _require(item_id not in seen_ids)
        seen_ids.add(item_id)
        validated_items.append(
            {
                "id": item_id,
                "question": _nonempty_string(object_item["question"]),
                "answer": _nonempty_string(object_item["answer"]),
                "explanation": _nonempty_string(object_item["explanation"]),
            }
        )
    return {"items": validated_items}


def validate_learning_resource(
    value: object, *, expected_type: LearningResourceType | str
) -> dict[str, object]:
    """Accept only the specified display resource and its traceable prompt version."""
    resource_type = _resource_type(expected_type)
    envelope = _strict_object(value, {"resource_type", "prompt_version", "content"})
    _require(envelope["resource_type"] == resource_type)
    _require(envelope["prompt_version"] == RESOURCE_PROMPT_VERSION)

    content = envelope["content"]
    if resource_type is LearningResourceType.EXPLANATION:
        validated_content = _validate_explanation(content)
    elif resource_type is LearningResourceType.CODE:
        validated_content = _validate_code(content)
    else:
        validated_content = _validate_exercise(content)
    return {
        "resource_type": resource_type.value,
        "prompt_version": RESOURCE_PROMPT_VERSION,
        "content": deepcopy(validated_content),
    }


def _content_schema(resource_type: LearningResourceType) -> dict[str, object]:
    if resource_type is LearningResourceType.EXPLANATION:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["markdown"],
            "properties": {"markdown": {"type": "string", "minLength": 1}},
        }
    if resource_type is LearningResourceType.CODE:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["language", "source", "expected_output", "key_steps", "display_only"],
            "properties": {
                "language": {"type": "string", "minLength": 1},
                "source": {"type": "string", "minLength": 1},
                "expected_output": {"type": "string", "minLength": 1},
                "key_steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 6,
                    "items": {"type": "string", "minLength": 1},
                },
                "display_only": {"const": True},
            },
        }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "minItems": 2,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "question", "answer", "explanation"],
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "question": {"type": "string", "minLength": 1},
                        "answer": {"type": "string", "minLength": 1},
                        "explanation": {"type": "string", "minLength": 1},
                    },
                },
            }
        },
    }


def resource_output_schema(resource_type: LearningResourceType | str) -> Mapping[str, object]:
    """Return the JSON Schema supplied to the provider for one requested resource type."""
    normalized_type = _resource_type(resource_type)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["resource_type", "prompt_version", "content"],
        "properties": {
            "resource_type": {"const": normalized_type.value},
            "prompt_version": {"const": RESOURCE_PROMPT_VERSION},
            "content": _content_schema(normalized_type),
        },
    }
