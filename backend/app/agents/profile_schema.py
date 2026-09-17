"""Strict, evidence-backed transient student profile schema for MVP P0."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import Final, Literal, TypeAlias

ProfileValue: TypeAlias = object
EvidenceSource: TypeAlias = Literal[
    "initial_query",
    "learner_statement",
    "learning_behavior",
    "explicit_feedback",
    "manual_correction",
]

PROFILE_VERSION: Final = 1
PROFILE_FIELDS: Final = (
    "professional_background",
    "knowledge_base",
    "cognitive_style",
    "learning_goals",
    "error_preferences",
    "engineering_preference",
)
EVIDENCE_SOURCES: Final = frozenset(
    {
        "initial_query",
        "learner_statement",
        "learning_behavior",
        "explicit_feedback",
        "manual_correction",
    }
)


class ProfileSchemaError(ValueError):
    """Raised for invalid or unsupported profile data without echoing its contents."""

    def __init__(self) -> None:
        super().__init__("Profile data did not satisfy the supported schema.")


def empty_transient_profile(initial_query: str) -> dict[str, ProfileValue]:
    """Create a non-speculative initial snapshot from a student's raw request."""
    if not isinstance(initial_query, str) or not initial_query.strip():
        raise ProfileSchemaError
    return {
        "profile_version": PROFILE_VERSION,
        "initial_query": initial_query.strip(),
        **{field: None for field in PROFILE_FIELDS},
        "evidence": {},
    }


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int, float)):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False


def _require_condition(condition: bool) -> None:
    if not condition:
        raise ProfileSchemaError


def _validate_evidence(
    value: object, *, profile_version: int, field: str
) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        raise ProfileSchemaError
    validated: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ProfileSchemaError
        _require_condition(set(item) == {"source", "confidence", "observed_at", "profile_version"})
        source = item["source"]
        confidence = item["confidence"]
        observed_at = item["observed_at"]
        version = item["profile_version"]
        _require_condition(isinstance(source, str) and source in EVIDENCE_SOURCES)
        _require_condition(
            isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and 0 <= confidence <= 1
        )
        _require_condition(isinstance(observed_at, str))
        try:
            parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError:
            raise ProfileSchemaError from None
        _require_condition(parsed.tzinfo is not None)
        _require_condition(isinstance(version, int) and not isinstance(version, bool))
        _require_condition(version == profile_version)
        validated.append(deepcopy(item))
    return validated


def validate_transient_profile(value: object) -> dict[str, ProfileValue]:
    """Validate fields, null unknowns, and versioned evidence before persistence."""
    if not isinstance(value, dict):
        raise ProfileSchemaError
    expected = {"profile_version", "initial_query", *PROFILE_FIELDS, "evidence"}
    _require_condition(set(value.keys()) == expected)
    profile_version = value["profile_version"]
    initial_query = value["initial_query"]
    _require_condition(isinstance(profile_version, int) and not isinstance(profile_version, bool))
    _require_condition(profile_version >= PROFILE_VERSION)
    _require_condition(isinstance(initial_query, str) and bool(initial_query.strip()))

    profile: dict[str, ProfileValue] = {
        "profile_version": profile_version,
        "initial_query": initial_query.strip(),
    }
    for field in PROFILE_FIELDS:
        field_value = value[field]
        if field == "error_preferences":
            _require_condition(field_value is None or isinstance(field_value, list))
        else:
            _require_condition(field_value is None or isinstance(field_value, dict))
        _require_condition(_is_json_value(field_value))
        profile[field] = deepcopy(field_value)

    evidence = value["evidence"]
    if not isinstance(evidence, dict):
        raise ProfileSchemaError
    _require_condition(all(isinstance(key, str) and key in PROFILE_FIELDS for key in evidence))
    validated_evidence: dict[str, list[dict[str, object]]] = {}
    for field in PROFILE_FIELDS:
        field_value = profile[field]
        records = evidence.get(field)
        if field_value is None:
            _require_condition(records is None)
            continue
        _require_condition(records is not None)
        validated_evidence[field] = _validate_evidence(
            records, profile_version=profile_version, field=field
        )
    profile["evidence"] = validated_evidence
    return profile


def profile_output_schema() -> Mapping[str, object]:
    """JSON Schema supplied to the Provider structured-output request in T019."""
    nullable_object: dict[str, object] = {"type": ["object", "null"]}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["profile_version", "initial_query", *PROFILE_FIELDS, "evidence"],
        "properties": {
            "profile_version": {"type": "integer", "minimum": PROFILE_VERSION},
            "initial_query": {"type": "string", "minLength": 1},
            "professional_background": nullable_object,
            "knowledge_base": nullable_object,
            "cognitive_style": nullable_object,
            "learning_goals": nullable_object,
            "error_preferences": {"type": ["array", "null"]},
            "engineering_preference": nullable_object,
            "evidence": {"type": "object", "additionalProperties": {"type": "array"}},
        },
    }


def merge_explicit_profile_values(
    initial_query: str,
    values: Mapping[str, object],
    evidence: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    profile_version: int = PROFILE_VERSION,
) -> dict[str, ProfileValue]:
    """Build a validated snapshot; callers cannot smuggle untracked dimensions."""
    profile = empty_transient_profile(initial_query)
    profile["profile_version"] = profile_version
    for field, field_value in values.items():
        if field not in PROFILE_FIELDS:
            raise ProfileSchemaError
        profile[field] = deepcopy(field_value)
    profile["evidence"] = deepcopy(dict(evidence))
    return validate_transient_profile(profile)
