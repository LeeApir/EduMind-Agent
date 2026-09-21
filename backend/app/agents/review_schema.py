"""Versioned ReviewAgent contracts and deterministic severe-code gate."""

import re
from collections.abc import Mapping
from copy import deepcopy
from enum import StrEnum
from typing import Final, cast

from app.agents.learning_resource_schema import LearningResourceType

REVIEW_PROMPT_VERSION: Final = "resource-review-v1"
MAX_TARGETED_CORRECTIONS: Final = 2


class ReviewVerdict(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    REJECT = "reject"


class ReviewSchemaError(ValueError):
    def __init__(self) -> None:
        super().__init__("Review data did not satisfy the supported schema.")


def _strict_object(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ReviewSchemaError
    return cast(dict[str, object], value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewSchemaError
    return value.strip()


def validate_review(value: object) -> dict[str, object]:
    """Validate a concise, actionable independent review decision."""
    envelope = _strict_object(value, {"review_version", "verdict", "issues"})
    if envelope["review_version"] != REVIEW_PROMPT_VERSION:
        raise ReviewSchemaError
    raw_verdict = envelope["verdict"]
    if not isinstance(raw_verdict, str):
        raise ReviewSchemaError
    try:
        verdict = ReviewVerdict(raw_verdict)
    except ValueError:
        raise ReviewSchemaError from None
    issues = envelope["issues"]
    if not isinstance(issues, list):
        raise ReviewSchemaError
    validated_issues: list[dict[str, str]] = []
    for issue in issues:
        record = _strict_object(issue, {"area", "severity", "message"})
        area = _text(record["area"])
        severity = _text(record["severity"])
        if area not in {"fact", "difficulty", "misconception", "code_safety"}:
            raise ReviewSchemaError
        if severity not in {"minor", "major", "severe"}:
            raise ReviewSchemaError
        validated_issues.append(
            {"area": area, "severity": severity, "message": _text(record["message"])}
        )
    if verdict is ReviewVerdict.PASS and validated_issues:
        raise ReviewSchemaError
    if verdict is not ReviewVerdict.PASS and not validated_issues:
        raise ReviewSchemaError
    return {
        "review_version": REVIEW_PROMPT_VERSION,
        "verdict": verdict.value,
        "issues": deepcopy(validated_issues),
    }


def review_output_schema() -> Mapping[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["review_version", "verdict", "issues"],
        "properties": {
            "review_version": {"const": REVIEW_PROMPT_VERSION},
            "verdict": {"enum": [member.value for member in ReviewVerdict]},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["area", "severity", "message"],
                    "properties": {
                        "area": {"enum": ["fact", "difficulty", "misconception", "code_safety"]},
                        "severity": {"enum": ["minor", "major", "severe"]},
                        "message": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }


_DANGEROUS_CODE = re.compile(
    r"\b(?:__import__|eval|exec|open|os\.system|subprocess(?:\.|\b)|socket(?:\.|\b)|requests(?:\.|\b))\b"
)


def severe_code_issues(
    resource_type: LearningResourceType, content: Mapping[str, object]
) -> list[dict[str, str]]:
    """Reject untrusted display code containing prohibited execution or I/O primitives."""
    if resource_type is not LearningResourceType.CODE:
        return []
    source = content.get("source")
    if not isinstance(source, str):
        return [{"area": "code_safety", "severity": "severe", "message": "Code source is missing."}]
    if _DANGEROUS_CODE.search(source):
        return [
            {
                "area": "code_safety",
                "severity": "severe",
                "message": "Code uses a prohibited execution, file, or network primitive.",
            }
        ]
    return []
