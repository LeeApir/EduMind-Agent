"""Versioned profile-event schema rejects out-of-contract summaries."""

import pytest

from app.agents.profile_events import (
    PROFILE_EVENT_ACTIONS,
    PROFILE_EVENT_TYPES,
    ProfileEventSchemaError,
    event_digest,
    event_payload,
    validate_profile_event,
)

NODE = "linked-list"
UNIT = "unit_0001"
SCENE = "scene_01"


def test_valid_event_is_normalized_with_all_keys() -> None:
    event = validate_profile_event(
        {"event_type": "hint_used", "knowledge_node_id": NODE, "action": "hint_level_1"}
    )
    assert event == {
        "event_type": "hint_used",
        "knowledge_node_id": NODE,
        "learning_unit_id": None,
        "scene_id": None,
        "action": "hint_level_1",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"event_type": "quiz_answered", "knowledge_node_id": NODE},
        {"knowledge_node_id": NODE},
        {"event_type": "hint_used", "knowledge_node_id": "Arrays"},
        {"event_type": "hint_used", "knowledge_node_id": "1-arrays"},
        {"event_type": "hint_used", "knowledge_node_id": NODE, "action": "code"},
        {"event_type": "explicit_feedback", "knowledge_node_id": NODE, "action": "hint_level_1"},
        {"event_type": "hint_used", "knowledge_node_id": NODE, "learning_unit_id": "bad!"},
        {"event_type": "hint_used", "knowledge_node_id": NODE, "mastery": 0.8},
        {"event_type": "hint_used", "knowledge_node_id": NODE, "action": "hint_level_3"},
        "not-an-event",
    ],
)
def test_invalid_events_are_rejected(payload: object) -> None:
    with pytest.raises(ProfileEventSchemaError):
        validate_profile_event(payload)


def test_event_actions_partition_across_types() -> None:
    assert set(PROFILE_EVENT_TYPES) == {
        "hint_used",
        "reexplanation_requested",
        "resource_selected",
        "explicit_feedback",
    }
    assert PROFILE_EVENT_ACTIONS == {
        "hint_level_1",
        "hint_level_2",
        "simpler",
        "deeper",
        "different_example",
        "code",
        "exercise",
        "too_easy",
        "too_hard",
        "liked_explanation",
        "skip",
        "mark_known",
    }


def test_event_payload_omits_unset_optionals() -> None:
    assert event_payload(event_type="resource_selected", knowledge_node_id=NODE) == {
        "event_type": "resource_selected",
        "knowledge_node_id": NODE,
    }
    assert event_payload(
        event_type="explicit_feedback",
        knowledge_node_id=NODE,
        learning_unit_id=UNIT,
        scene_id=SCENE,
        action="too_easy",
    ) == {
        "event_type": "explicit_feedback",
        "knowledge_node_id": NODE,
        "learning_unit_id": UNIT,
        "scene_id": SCENE,
        "action": "too_easy",
    }


def test_digest_is_stable_and_distinguishes_events() -> None:
    event = validate_profile_event(
        {"event_type": "hint_used", "knowledge_node_id": NODE, "action": "hint_level_2"}
    )
    assert event_digest(event) == event_digest(validate_profile_event(event))
    other = validate_profile_event({"event_type": "hint_used", "knowledge_node_id": "arrays"})
    assert event_digest(event) != event_digest(other)
