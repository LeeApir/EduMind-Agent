"""ProfileAgent extracts only supported evidence and degrades safely."""

import asyncio
from datetime import datetime, timezone

import pytest

from app.agents.profile_agent import ProfileAgent, ProfileInputError
from app.agents.profile_schema import empty_transient_profile
from app.services.provider_gateway import ProviderError, ProviderErrorCode, StructuredResult


class StubGateway:
    def __init__(self, result: StructuredResult | ProviderError) -> None:
        self.result = result
        self.requests = []

    async def generate_structured(
        self, request: object, *, retry_safe: bool = False
    ) -> StructuredResult:
        self.requests.append((request, retry_safe))
        if isinstance(self.result, ProviderError):
            raise self.result
        return self.result


def valid_profile(query: str, *, version: int = 1) -> dict[str, object]:
    profile = empty_transient_profile(query)
    profile["profile_version"] = version
    profile["learning_goals"] = {"current_topic": "链表", "current_difficulty": "指针"}
    profile["engineering_preference"] = {"code_first": True}
    profile["evidence"] = {
        "learning_goals": [
            {
                "source": "initial_query",
                "confidence": 0.9,
                "observed_at": "2026-09-17T14:30:00+00:00",
                "profile_version": version,
            }
        ],
        "engineering_preference": [
            {
                "source": "initial_query",
                "confidence": 0.8,
                "observed_at": "2026-09-17T14:30:00+00:00",
                "profile_version": version,
            }
        ],
    }
    return profile


def test_one_sentence_extracts_explicit_goal_without_questionnaire() -> None:
    async def exercise() -> None:
        gateway = StubGateway(
            StructuredResult(value=valid_profile("链表插入总搞混，先看 C 代码"), model_id="test")
        )
        agent = ProfileAgent(
            gateway,
            now=lambda: datetime(2026, 9, 17, 14, 30, tzinfo=timezone.utc),
        )

        extraction = await agent.extract("  链表插入总搞混，先看 C 代码  ")

        assert extraction.degraded is False
        assert extraction.profile["learning_goals"] == {
            "current_topic": "链表",
            "current_difficulty": "指针",
        }
        assert extraction.profile["engineering_preference"] == {"code_first": True}
        request, retry_safe = gateway.requests[0]
        assert retry_safe is True
        assert request.prompt.messages[-1].content == "链表插入总搞混，先看 C 代码"
        assert "Prompt version: profile-v1." in request.prompt.messages[0].content
        assert "2026-09-17T14:30:00+00:00" in request.prompt.messages[0].content

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "result",
    [
        StructuredResult(value={"not": "a supported profile"}, model_id="test"),
        ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE),
    ],
)
def test_invalid_or_failed_model_output_becomes_empty_nonblocking_profile(
    result: StructuredResult | ProviderError,
) -> None:
    async def exercise() -> None:
        agent = ProfileAgent(StubGateway(result))
        extraction = await agent.extract("请讲一下栈")
        assert extraction.degraded is True
        assert extraction.profile == empty_transient_profile("请讲一下栈")

    asyncio.run(exercise())


def test_empty_goal_is_actionable_and_does_not_call_provider() -> None:
    async def exercise() -> None:
        gateway = StubGateway(StructuredResult(value=valid_profile("ignored"), model_id="test"))
        with pytest.raises(ProfileInputError, match="learning goal is required"):
            await ProfileAgent(gateway).extract("  ")
        assert gateway.requests == []

    asyncio.run(exercise())
