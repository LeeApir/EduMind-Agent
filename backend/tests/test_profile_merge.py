"""Manual corrections override inference deterministically, without mutating history."""

import pytest

from app.agents.profile_schema import (
    EDITABLE_PROFILE_FIELDS,
    EVIDENCE_SOURCE_PRECEDENCE,
    ProfileSchemaError,
    apply_manual_correction,
    evidence_source_rank,
    merge_explicit_profile_values,
    strongest_evidence_source,
)

OBSERVED_AT = "2026-09-23T15:05:25+08:00"


def evidence(source: str, *, version: int = 1) -> dict[str, object]:
    return {
        "source": source,
        "confidence": 0.7,
        "observed_at": "2026-09-17T14:20:00+08:00",
        "profile_version": version,
    }


def build_profile() -> dict[str, object]:
    return merge_explicit_profile_values(
        "想理解链表",
        {
            "learning_goals": {"current_topic": "链表"},
            "engineering_preference": {"code_first": True},
        },
        {
            "learning_goals": [evidence("initial_query")],
            "engineering_preference": [evidence("initial_query")],
        },
    )


def test_editable_fields_are_a_subset_of_profile_dimensions() -> None:
    assert set(EDITABLE_PROFILE_FIELDS) == {
        "professional_background",
        "learning_goals",
        "error_preferences",
        "engineering_preference",
    }


def test_source_precedence_ranks_manual_correction_first() -> None:
    assert EVIDENCE_SOURCE_PRECEDENCE[0] == "manual_correction"
    assert evidence_source_rank("manual_correction") < evidence_source_rank("initial_query")
    with pytest.raises(ProfileSchemaError):
        evidence_source_rank("model_guess")


def test_strongest_source_wins_when_evidence_is_mixed() -> None:
    records = [
        evidence("initial_query"),
        evidence("explicit_feedback"),
        evidence("manual_correction"),
    ]
    assert strongest_evidence_source(records) == "manual_correction"
    assert (
        strongest_evidence_source([evidence("learning_behavior"), evidence("initial_query")])
        == "learning_behavior"
    )
    with pytest.raises(ProfileSchemaError):
        strongest_evidence_source([])


def test_correction_overrides_inferred_value_and_bumps_version() -> None:
    profile = build_profile()
    corrected = apply_manual_correction(
        profile,
        {"learning_goals": {"current_topic": "数组"}},
        observed_at=OBSERVED_AT,
    )
    assert profile["profile_version"] == 1
    assert corrected["profile_version"] == 2
    assert corrected["learning_goals"] == {"current_topic": "数组"}
    # Untouched field and its evidence survive unchanged.
    assert corrected["engineering_preference"] == {"code_first": True}
    assert profile["learning_goals"] == {"current_topic": "链表"}


def test_correction_evidence_is_manual_with_full_confidence_and_new_version() -> None:
    corrected = apply_manual_correction(
        build_profile(),
        {"learning_goals": {"current_topic": "数组"}},
        observed_at=OBSERVED_AT,
    )
    records = corrected["evidence"]["learning_goals"]
    assert records[-1] == {
        "source": "manual_correction",
        "confidence": 1.0,
        "observed_at": OBSERVED_AT,
        "profile_version": 2,
    }
    # Older inferred evidence is carried forward, not dropped.
    assert records[0]["source"] == "initial_query"


def test_correction_can_fill_a_previously_unknown_field() -> None:
    profile = build_profile()
    assert profile["professional_background"] is None
    corrected = apply_manual_correction(
        profile,
        {"professional_background": {"major": "计算机"}},
        observed_at=OBSERVED_AT,
    )
    assert corrected["professional_background"] == {"major": "计算机"}
    assert corrected["evidence"]["professional_background"] == [
        {
            "source": "manual_correction",
            "confidence": 1.0,
            "observed_at": OBSERVED_AT,
            "profile_version": 2,
        }
    ]


@pytest.mark.parametrize(
    "corrections",
    [
        {"knowledge_base": {"topic": "链表"}},
        {"cognitive_style": {"visual": True}},
        {"nickname": "小李"},
    ],
)
def test_non_editable_or_unknown_fields_are_rejected(corrections: object) -> None:
    assert isinstance(corrections, dict)
    with pytest.raises(ProfileSchemaError):
        apply_manual_correction(build_profile(), corrections, observed_at=OBSERVED_AT)


def test_empty_corrections_are_rejected() -> None:
    with pytest.raises(ProfileSchemaError):
        apply_manual_correction(build_profile(), {}, observed_at=OBSERVED_AT)


def test_older_evidence_carries_into_newer_snapshot_version() -> None:
    profile = merge_explicit_profile_values(
        "看代码",
        {"engineering_preference": {"code_first": True}},
        {"engineering_preference": [evidence("initial_query", version=1)]},
        profile_version=2,
    )
    assert profile["profile_version"] == 2
