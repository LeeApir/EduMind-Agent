"""TutorAgent orchestrates one turn, validates it, and recovers from provider failure."""

import asyncio

import pytest

from app.agents.classroom_context import build_classroom_context
from app.agents.classroom_turn_schema import (
    TURN_PROMPT_VERSION,
    TurnSchemaError,
    validate_classroom_turn,
)
from app.agents.tutor_agent import TutorAgent
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
)


def turn_value(utterances: list[dict[str, str]]) -> dict[str, object]:
    return {"turn_version": TURN_PROMPT_VERSION, "utterances": utterances}


class StubGateway:
    def __init__(self, result: StructuredResult | ProviderError) -> None:
        self.result = result
        self.requests: list[tuple[StructuredRequest, bool]] = []

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult:
        self.requests.append((request, retry_safe))
        if isinstance(self.result, ProviderError):
            raise self.result
        return self.result


def context():
    return build_classroom_context(
        default_knowledge_graph_repository(),
        node_id="linked-list-insertion",
        goal="理解链表的插入操作",
    )


def test_focus_mode_emits_only_tutor_in_one_call() -> None:
    async def exercise() -> None:
        gateway = StubGateway(
            StructuredResult(
                value=turn_value([{"role": "tutor", "text": "链表插入先找位置再改指针。"}]),
                model_id="model-a",
            )
        )
        outcome = await TutorAgent(gateway).orchestrate(
            mode="focus", enabled_roles=[], context=context()
        )
        assert outcome.ok
        assert outcome.turn is not None and outcome.failure is None
        assert outcome.turn.roles == ("tutor",)
        assert outcome.turn.model_id == "model-a"
        assert len(gateway.requests) == 1
        request, retry_safe = gateway.requests[0]
        assert retry_safe is True
        assert request.json_schema["properties"]["utterances"]["maxItems"] == 3
        instructions = request.prompt.messages[0].content
        assert "不得与其他角色重复" in instructions
        assert "基础同学" not in instructions and "进阶同学" not in instructions

    asyncio.run(exercise())


def test_interactive_mode_allows_companions_and_lists_eligible_personas() -> None:
    async def exercise() -> None:
        gateway = StubGateway(
            StructuredResult(
                value=turn_value(
                    [
                        {"role": "tutor", "text": "链表插入的核心是调整前驱节点的 next 指针。"},
                        {"role": "beginner", "text": "为什么不能先断开原来的指针？"},
                    ]
                ),
                model_id="model-a",
            )
        )
        outcome = await TutorAgent(gateway).orchestrate(
            mode="interactive", enabled_roles=["beginner", "advanced"], context=context()
        )
        assert outcome.ok
        assert outcome.turn is not None and outcome.turn.roles == ("tutor", "beginner")
        instructions = gateway.requests[0][0].prompt.messages[0].content
        assert "基础同学" in instructions and "进阶同学" in instructions

    asyncio.run(exercise())


def test_interactive_turn_may_be_tutor_only_without_forcing_companions() -> None:
    async def exercise() -> None:
        gateway = StubGateway(
            StructuredResult(
                value=turn_value(
                    [{"role": "tutor", "text": "这一段没有明显误区，直接进入练习。"}]
                ),
                model_id="model-a",
            )
        )
        outcome = await TutorAgent(gateway).orchestrate(
            mode="interactive", enabled_roles=["beginner", "advanced"], context=context()
        )
        assert outcome.ok and outcome.turn is not None
        assert outcome.turn.roles == ("tutor",)

    asyncio.run(exercise())


def test_focus_turn_rejects_companion_utterance() -> None:
    with pytest.raises(TurnSchemaError):
        validate_classroom_turn(
            turn_value(
                [
                    {"role": "tutor", "text": "讲解。"},
                    {"role": "beginner", "text": "误区。"},
                ]
            ),
            eligible_roles=["tutor"],
        )


def test_duplicate_role_is_rejected() -> None:
    with pytest.raises(TurnSchemaError):
        validate_classroom_turn(
            turn_value(
                [
                    {"role": "tutor", "text": "第一段。"},
                    {"role": "tutor", "text": "第二段。"},
                ]
            ),
            eligible_roles=["tutor"],
        )


def test_identical_text_across_roles_is_rejected() -> None:
    with pytest.raises(TurnSchemaError):
        validate_classroom_turn(
            turn_value(
                [
                    {"role": "tutor", "text": "重复内容。"},
                    {"role": "beginner", "text": "重复内容。"},
                ]
            ),
            eligible_roles=["tutor", "beginner"],
        )


def test_tutor_must_be_present() -> None:
    with pytest.raises(TurnSchemaError):
        validate_classroom_turn(
            turn_value([{"role": "beginner", "text": "只有同学。"}]),
            eligible_roles=["tutor", "beginner"],
        )


@pytest.mark.parametrize(
    "bad",
    [
        {"turn_version": TURN_PROMPT_VERSION, "utterances": []},
        {
            "turn_version": "wrong",
            "utterances": [{"role": "tutor", "text": "x"}],
        },
        {
            "turn_version": TURN_PROMPT_VERSION,
            "utterances": [{"role": "tutor", "text": "x"}],
            "extra": 1,
        },
        {
            "turn_version": TURN_PROMPT_VERSION,
            "utterances": [{"role": "tutor", "text": "   "}],
        },
        {
            "turn_version": TURN_PROMPT_VERSION,
            "utterances": [{"role": "unknown", "text": "x"}],
        },
    ],
)
def test_invalid_turn_shapes_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(TurnSchemaError):
        validate_classroom_turn(bad, eligible_roles=["tutor", "beginner", "advanced"])


@pytest.mark.parametrize(
    "error",
    [
        ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE),
        ProviderError(ProviderErrorCode.RATE_LIMITED),
    ],
)
def test_provider_failure_returns_recoverable_failure(error: ProviderError) -> None:
    async def exercise() -> None:
        gateway = StubGateway(error)
        outcome = await TutorAgent(gateway).orchestrate(
            mode="focus", enabled_roles=[], context=context()
        )
        assert not outcome.ok
        assert outcome.turn is None
        assert outcome.failure is not None
        assert outcome.failure.recoverable is True
        assert outcome.failure.code is error.code
        assert outcome.failure.message

    asyncio.run(exercise())


def test_invalid_model_output_returns_invalid_output_failure() -> None:
    async def exercise() -> None:
        gateway = StubGateway(
            StructuredResult(
                value=turn_value(
                    [
                        {"role": "tutor", "text": "x"},
                        {"role": "tutor", "text": "y"},
                    ]
                ),
                model_id="model-a",
            )
        )
        outcome = await TutorAgent(gateway).orchestrate(
            mode="focus", enabled_roles=[], context=context()
        )
        assert not outcome.ok
        assert outcome.failure is not None
        assert outcome.failure.code is ProviderErrorCode.INVALID_OUTPUT

    asyncio.run(exercise())
