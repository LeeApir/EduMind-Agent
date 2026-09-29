"""Classroom role personas are fixed and speaker eligibility is deterministic."""

import pytest

from app.agents.classroom_roles import (
    COMPANION_ROLES,
    ROLE_PERSONA_VERSION,
    ClassroomMode,
    ClassroomRole,
    classroom_role_personas,
    role_persona,
    select_speaker_roles,
)


def test_personas_are_fixed_stable_and_versioned() -> None:
    personas = classroom_role_personas()
    assert [persona.role for persona in personas] == list(ClassroomRole)
    assert [persona.role for persona in personas] == [
        ClassroomRole.TUTOR,
        ClassroomRole.BEGINNER,
        ClassroomRole.ADVANCED,
    ]
    assert all(
        persona.name and persona.responsibility and persona.speaking_style and persona.trigger
        for persona in personas
    )
    assert all(
        persona.role in COMPANION_ROLES
        for persona in personas
        if persona.role is not ClassroomRole.TUTOR
    )
    assert role_persona("tutor").name == "启智导师"
    assert role_persona("tutor") is role_persona(ClassroomRole.TUTOR)
    assert ROLE_PERSONA_VERSION == "classroom-roles-v1"


def test_focus_mode_always_yields_tutor_alone() -> None:
    assert select_speaker_roles("focus") == (ClassroomRole.TUTOR,)
    assert select_speaker_roles(ClassroomMode.FOCUS, ["beginner", "advanced"]) == (
        ClassroomRole.TUTOR,
    )


def test_interactive_mode_yields_tutor_then_sorted_deduped_companions() -> None:
    assert select_speaker_roles("interactive", ["beginner", "advanced"]) == (
        ClassroomRole.TUTOR,
        ClassroomRole.BEGINNER,
        ClassroomRole.ADVANCED,
    )
    assert select_speaker_roles("interactive", ["advanced", "beginner", "advanced"]) == (
        ClassroomRole.TUTOR,
        ClassroomRole.BEGINNER,
        ClassroomRole.ADVANCED,
    )
    assert select_speaker_roles("interactive", ["beginner"]) == (
        ClassroomRole.TUTOR,
        ClassroomRole.BEGINNER,
    )
    assert select_speaker_roles("interactive", []) == (ClassroomRole.TUTOR,)


def test_unknown_or_tutor_roles_are_not_companions() -> None:
    assert select_speaker_roles("interactive", ["tutor", "beginner", "unknown"]) == (
        ClassroomRole.TUTOR,
        ClassroomRole.BEGINNER,
    )


def test_unknown_mode_and_role_are_rejected() -> None:
    with pytest.raises(ValueError):
        select_speaker_roles("debate")
    with pytest.raises(ValueError):
        role_persona("moderator")
