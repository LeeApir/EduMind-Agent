"""Single-Tutor orchestration: one structured call produces one classroom turn.

The Tutor decides, within a single call, whether any companion role adds distinct value
(a typical misconception, or a boundary/code detail). Focus mode yields the tutor alone;
interactive mode yields the tutor plus at most the enabled companions, and never requires
all of them to speak. Provider failure returns a recoverable result and never disturbs
existing reviewed resources.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.agents.classroom_context import ClassroomTurnContext
from app.agents.classroom_roles import (
    ClassroomMode,
    ClassroomRole,
    classroom_role_personas,
    select_speaker_roles,
)
from app.agents.classroom_turn_schema import (
    TURN_PROMPT_VERSION,
    TurnSchemaError,
    classroom_turn_output_schema,
    validate_classroom_turn,
)
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
    TaskProfile,
    TextRequest,
    TokenUsage,
)

TURN_INSTRUCTION_VERSION = "classroom-turn-instructions-v1"


class StructuredTurnGateway(Protocol):
    """The narrow structured generation capability used by TutorAgent."""

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult: ...


@dataclass(frozen=True, slots=True)
class ClassroomUtterance:
    role: str
    text: str


@dataclass(frozen=True, slots=True)
class ClassroomTurn:
    """A schema-validated single-Tutor turn; companions are optional by design."""

    utterances: tuple[ClassroomUtterance, ...]
    model_id: str
    usage: TokenUsage | None = None

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(utterance.role for utterance in self.utterances)


@dataclass(frozen=True, slots=True)
class TurnOrchestrationFailure:
    """A recoverable, content-free failure; existing reviewed resources stay untouched."""

    code: ProviderErrorCode
    message: str
    recoverable: bool = True


@dataclass(frozen=True, slots=True)
class TurnOrchestration:
    """Exactly one of ``turn`` or ``failure`` is populated after orchestration."""

    turn: ClassroomTurn | None = None
    failure: TurnOrchestrationFailure | None = None

    @property
    def ok(self) -> bool:
        return self.turn is not None


class TutorAgent:
    """Orchestrate every classroom turn through one structured provider call."""

    def __init__(self, gateway: StructuredTurnGateway) -> None:
        self._gateway = gateway

    @staticmethod
    def _system_prompt(eligible_roles: Sequence[ClassroomRole]) -> str:
        eligible_set = set(eligible_roles)
        personas = "\n".join(
            f"- {persona.role.value}（{persona.name}）：{persona.responsibility}"
            f" 说话风格：{persona.speaking_style} 触发条件：{persona.trigger}"
            for persona in classroom_role_personas()
            if persona.role in eligible_set
        )
        has_companions = len(eligible_set) > 1
        companion_rule = (
            "基础/进阶同学只在确有教学价值时按需发言：基础同学呈现典型误区，"
            "进阶同学补充边界/代码细节。同一知识点不得由多个角色重复改写；"
            "没有补充价值时，只输出 tutor 一条发言即可。"
            if has_companions
            else "仅输出 tutor 一条发言。"
        )
        return (
            "你是启智学伴课堂的单 Tutor 编排者，一次课堂动作只输出一个课堂回合。"
            "用中文回复，只返回符合 schema 的 JSON 对象，不输出 Markdown、代码围栏或额外说明。"
            f"Prompt version: {TURN_PROMPT_VERSION}. "
            f"Instruction version: {TURN_INSTRUCTION_VERSION}.\n"
            "仅使用提供的当前目标、已审核资源、必要画像和路径上下文，不得臆测未知画像字段。"
            "tutor 是唯一主讲角色，负责讲解当前知识点、提问、反馈与资源切换，且必须且只能发言一次。"
            + companion_rule
            + "每个角色至多发言一次，text 不得与其他角色重复。"
            + "\n本回合可发言的角色及其画像：\n"
            + personas
            + "\nRequired output schema:\n"
            + json.dumps(classroom_turn_output_schema(), ensure_ascii=False)
        )

    async def orchestrate(
        self,
        *,
        mode: ClassroomMode | str,
        enabled_roles: Sequence[str],
        context: ClassroomTurnContext,
    ) -> TurnOrchestration:
        """Run one orchestrated turn and return a validated turn or a recoverable failure."""
        eligible = select_speaker_roles(mode, enabled_roles)
        provider_request = StructuredRequest(
            prompt=TextRequest(
                messages=(
                    ChatMessage(role="system", content=self._system_prompt(eligible)),
                    ChatMessage(role="user", content=context.serialized),
                ),
                task_profile=TaskProfile.DEFAULT,
            ),
            json_schema=classroom_turn_output_schema(),
        )
        try:
            result = await self._gateway.generate_structured(provider_request, retry_safe=True)
            validated = validate_classroom_turn(
                result.value, eligible_roles=[role.value for role in eligible]
            )
        except ProviderError as error:
            return TurnOrchestration(
                failure=TurnOrchestrationFailure(code=error.code, message=str(error))
            )
        except TurnSchemaError as error:
            return TurnOrchestration(
                failure=TurnOrchestrationFailure(
                    code=ProviderErrorCode.INVALID_OUTPUT, message=str(error)
                )
            )
        raw_utterances = validated["utterances"]
        assert isinstance(raw_utterances, list)
        utterances = tuple(
            ClassroomUtterance(role=item["role"], text=item["text"])
            for item in raw_utterances
        )
        return TurnOrchestration(
            turn=ClassroomTurn(
                utterances=utterances, model_id=result.model_id, usage=result.usage
            )
        )
