"""Transient profile schema rejects speculation and requires versioned evidence."""

import pytest

from app.agents.profile_schema import (
    PROFILE_VERSION,
    ProfileSchemaError,
    empty_transient_profile,
    merge_explicit_profile_values,
    profile_output_schema,
    validate_transient_profile,
)


def evidence(source: str = "initial_query", *, version: int = 1) -> dict[str, object]:
    return {
        "source": source,
        "confidence": 0.9,
        "observed_at": "2026-09-17T14:20:00+08:00",
        "profile_version": version,
    }


def test_empty_profile_keeps_all_unknown_dimensions_null() -> None:
    profile = empty_transient_profile("我想弄懂链表")
    assert profile == {
        "profile_version": PROFILE_VERSION,
        "initial_query": "我想弄懂链表",
        "professional_background": None,
        "knowledge_base": None,
        "cognitive_style": None,
        "learning_goals": None,
        "error_preferences": None,
        "engineering_preference": None,
        "evidence": {},
    }
    assert validate_transient_profile(profile) == profile


def test_explicit_goal_difficulty_and_preference_need_field_evidence() -> None:
    profile = merge_explicit_profile_values(
        "链表插入的指针总是搞混，想先看 C 代码",
        {
            "learning_goals": {
                "current_topic": "链表插入",
                "current_difficulty": "指针",
            },
            "engineering_preference": {"code_first": True, "preferred_languages": ["C"]},
        },
        {
            "learning_goals": [evidence()],
            "engineering_preference": [evidence()],
        },
    )
    assert profile["professional_background"] is None
    assert profile["learning_goals"] == {
        "current_topic": "链表插入",
        "current_difficulty": "指针",
    }
    assert profile["evidence"] == {
        "learning_goals": [evidence()],
        "engineering_preference": [evidence()],
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda profile: profile.__setitem__("professional_background", {"major": "计算机"}),
        lambda profile: profile.__setitem__("evidence", {"learning_goals": [evidence()]}),
        lambda profile: profile.__setitem__("unapproved_dimension", None),
        lambda profile: profile.__setitem__("error_preferences", {"topic": "指针"}),
    ],
)
def test_speculation_or_wrong_dimension_shape_is_rejected(mutate: object) -> None:
    profile = empty_transient_profile("讲链表")
    assert callable(mutate)
    mutate(profile)
    with pytest.raises(ProfileSchemaError):
        validate_transient_profile(profile)


@pytest.mark.parametrize(
    "record",
    [
        {
            "source": "model_guess",
            "confidence": 0.5,
            "observed_at": "2026-09-17T14:20:00+08:00",
            "profile_version": 1,
        },
        {
            "source": "initial_query",
            "confidence": 1.1,
            "observed_at": "2026-09-17T14:20:00+08:00",
            "profile_version": 1,
        },
        {
            "source": "initial_query",
            "confidence": 0.5,
            "observed_at": "not-a-time",
            "profile_version": 1,
        },
        {
            "source": "initial_query",
            "confidence": 0.5,
            "observed_at": "2026-09-17T14:20:00+08:00",
            "profile_version": 2,
        },
        {"source": "initial_query", "confidence": 0.5, "observed_at": "2026-09-17T14:20:00+08:00"},
    ],
)
def test_evidence_requires_allowed_source_confidence_time_and_matching_version(
    record: dict[str, object],
) -> None:
    profile = empty_transient_profile("链表难")
    profile["learning_goals"] = {"current_difficulty": "链表"}
    profile["evidence"] = {"learning_goals": [record]}
    with pytest.raises(ProfileSchemaError):
        validate_transient_profile(profile)


def test_profile_version_is_carried_by_evidence_and_prompt_schema_is_versioned() -> None:
    profile = merge_explicit_profile_values(
        "看代码",
        {"engineering_preference": {"code_first": True}},
        {"engineering_preference": [evidence(version=2)]},
        profile_version=2,
    )
    assert profile["profile_version"] == 2
    schema = profile_output_schema()
    assert schema["properties"]["profile_version"] == {"type": "integer", "minimum": 1}
    assert set(schema["required"]) >= {"learning_goals", "engineering_preference", "evidence"}


def test_invalid_initial_query_and_untracked_field_cannot_be_built() -> None:
    with pytest.raises(ProfileSchemaError):
        empty_transient_profile("   ")
    with pytest.raises(ProfileSchemaError):
        merge_explicit_profile_values("链表", {"nickname": "小李"}, {})
