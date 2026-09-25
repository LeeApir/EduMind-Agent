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


def test_provider_cannot_forge_manual_correction_evidence() -> None:
    async def exercise() -> None:
        forged = valid_profile("再学习队列", version=2)
        forged["evidence"]["learning_goals"][0]["source"] = "manual_correction"
        agent = ProfileAgent(StubGateway(StructuredResult(value=forged, model_id="test")))

        extraction = await agent.extract("再学习队列", profile_version=2)

        assert extraction.degraded is True
        assert extraction.profile["learning_goals"] is None
        assert extraction.profile["profile_version"] == 2

    asyncio.run(exercise())


def test_behavior_update_sends_only_minimal_summary_and_allowlists_delta() -> None:
    async def exercise() -> None:
        gateway = StubGateway(
            StructuredResult(
                value={"updates": {"error_preferences": [{"topic": "链表"}]}}, model_id="test"
            )
        )
        summary = {"event_type": "quiz_attempt", "knowledge_node_id": "linked-list", "score": 0.5}
        proposal = await ProfileAgent(gateway).update_from_behavior(
            summary, allowed_fields=("error_preferences",)
        )
        assert proposal.degraded is False
        assert proposal.updates == {"error_preferences": [{"topic": "链表"}]}
        request, retry_safe = gateway.requests[0]
        assert retry_safe is True
        assert request.prompt.messages[-1].content == (
            '{"event_type": "quiz_attempt", "knowledge_node_id": "linked-list", "score": 0.5}'
        )
        assert "answers" not in request.prompt.messages[-1].content
        assert "initial_query" not in request.prompt.messages[-1].content
        assert set(request.json_schema["properties"]["updates"]["properties"]) == {
            "error_preferences"
        }

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "value",
    [
        {"updates": {"learning_goals": {"current_topic": "链表"}}},
        {"updates": {"error_preferences": None}},
        {"updates": {}, "source": "manual_correction"},
    ],
)
def test_behavior_update_rejects_forged_or_invalid_output(value: dict[str, object]) -> None:
    async def exercise() -> None:
        gateway = StubGateway(StructuredResult(value=value, model_id="test"))
        proposal = await ProfileAgent(gateway).update_from_behavior(
            {"event_type": "quiz_attempt"}, allowed_fields=("error_preferences",)
        )
        assert proposal.degraded is True
        assert proposal.updates == {}

    asyncio.run(exercise())
