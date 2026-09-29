"""Versioned, fixed classroom role personas and deterministic speaker eligibility.

Classroom roles are stable product personas (tutor/beginner/advanced); debate
perspectives (performance/engineering/academic/moderator) are separate temporary
reasoning duties handled elsewhere. Personas shape expression and interaction only,
never knowledge facts. Selection here decides which roles are ELIGIBLE to speak for
one turn; the single Tutor orchestration decides the actual per-turn subset and never
requires every companion to speak.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

ROLE_PERSONA_VERSION: Final = "classroom-roles-v1"


class ClassroomRole(StrEnum):
    TUTOR = "tutor"
    BEGINNER = "beginner"
    ADVANCED = "advanced"


class ClassroomMode(StrEnum):
    FOCUS = "focus"
    INTERACTIVE = "interactive"


COMPANION_ROLES: Final = frozenset({ClassroomRole.BEGINNER, ClassroomRole.ADVANCED})


@dataclass(frozen=True, slots=True)
class RolePersona:
    """A fixed persona: identity, teaching responsibility, and on-demand trigger."""

    role: ClassroomRole
    name: str
    responsibility: str
    speaking_style: str
    trigger: str


_PERSONAS: dict[ClassroomRole, RolePersona] = {
    ClassroomRole.TUTOR: RolePersona(
        role=ClassroomRole.TUTOR,
        name="启智导师",
        responsibility="主讲、提问、反馈和资源切换。",
        speaking_style="短句、分步、每轮只追问一个问题；工程案例优先，必要时补充理论。",
        trigger="始终发言，是唯一的主讲角色。",
    ),
    ClassroomRole.BEGINNER: RolePersona(
        role=ClassroomRole.BEGINNER,
        name="基础同学",
        responsibility="呈现与当前知识点相关的典型误区。",
        speaking_style="以初学同侪口吻提出常见困惑，不重复导师已讲内容。",
        trigger="仅当存在与当前目标相关的典型误区时按需发言。",
    ),
    ClassroomRole.ADVANCED: RolePersona(
        role=ClassroomRole.ADVANCED,
        name="进阶同学",
        responsibility="补充边界条件、代码细节与性能权衡。",
        speaking_style="精炼指出边界或代码细节，不重复导师与其他角色已讲内容。",
        trigger="仅当存在值得补充的边界/代码细节时按需发言。",
    ),
}


def role_persona(role: ClassroomRole | str) -> RolePersona:
    """Return one fixed persona; unknown roles are a programming error, not data."""
    try:
        normalized = ClassroomRole(role)
    except ValueError:
        raise ValueError("Unsupported classroom role.") from None
    return _PERSONAS[normalized]


def classroom_role_personas() -> tuple[RolePersona, ...]:
    """Return all classroom personas in stable role order (tutor first)."""
    return tuple(_PERSONAS[role] for role in ClassroomRole)


def select_speaker_roles(
    mode: ClassroomMode | str, enabled_roles: Sequence[str] = ()
) -> tuple[ClassroomRole, ...]:
    """Return the roles eligible to speak for one turn.

    Focus mode always yields the tutor alone. Interactive mode yields the tutor
    followed by the deduplicated companion roles the student enabled, in stable
    product order (beginner before advanced). Companions are candidates only: the
    single Tutor decides the actual per-turn subset and is never required to make
    all of them speak.
    """
    try:
        normalized_mode = ClassroomMode(mode)
    except ValueError:
        raise ValueError("Unsupported classroom mode.") from None
    if normalized_mode is ClassroomMode.FOCUS:
        return (ClassroomRole.TUTOR,)
    enabled = {ClassroomRole(raw) for raw in enabled_roles if raw in COMPANION_ROLES}
    companions = tuple(
        role for role in (ClassroomRole.BEGINNER, ClassroomRole.ADVANCED) if role in enabled
    )
    return (ClassroomRole.TUTOR, *companions)
