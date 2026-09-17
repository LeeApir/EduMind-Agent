"""LearningUnitGenerator creates pending candidates and preserves safe failures."""

import asyncio

import pytest

from app.agents.learning_resource_schema import (
    RESOURCE_PROMPT_VERSION,
    LearningResourceType,
)
from app.agents.learning_unit_generator import (
    LearningResourceRequest,
    LearningUnitGenerator,
    ResourceGenerationInputError,
)
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
)


def envelope(resource_type: str, content: dict[str, object]) -> dict[str, object]:
    return {
        "resource_type": resource_type,
        "prompt_version": RESOURCE_PROMPT_VERSION,
        "content": content,
    }


def valid_results() -> dict[LearningResourceType, StructuredResult]:
    return {
        LearningResourceType.EXPLANATION: StructuredResult(
            value=envelope("explanation", {"markdown": "链表节点由指针连接。"}), model_id="model-a"
        ),
        LearningResourceType.CODE: StructuredResult(
            value=envelope(
                "code",
                {
                    "language": "C",
                    "source": "printf(\"ok\\n\");",
                    "expected_output": "ok",
                    "key_steps": ["输出结果"],
                    "display_only": True,
                },
            ),
            model_id="model-a",
        ),
        LearningResourceType.EXERCISE: StructuredResult(
            value=envelope(
                "exercise",
                {
                    "items": [
                        {"id": "q1", "question": "Q1", "answer": "A1", "explanation": "E1"},
                        {"id": "q2", "question": "Q2", "answer": "A2", "explanation": "E2"},
                        {"id": "q3", "question": "Q3", "answer": "A3", "explanation": "E3"},
                    ]
                },
            ),
            model_id="model-a",
        ),
    }


class StubGateway:
    def __init__(
        self, results: dict[LearningResourceType, StructuredResult | ProviderError]
    ) -> None:
        self.results = results
        self.requests = []

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult:
        self.requests.append((request, retry_safe))
        properties = request.json_schema["properties"]
        assert isinstance(properties, dict)
        type_schema = properties["resource_type"]
        assert isinstance(type_schema, dict)
        resource_type = LearningResourceType(type_schema["const"])
        result = self.results[resource_type]
        if isinstance(result, ProviderError):
            raise result
        return result


def test_generates_schema_valid_explanation_single_language_code_and_three_exercises() -> None:
    async def exercise() -> None:
        gateway = StubGateway(valid_results())
        result = await LearningUnitGenerator(gateway).generate(
            LearningResourceRequest(
                knowledge_point="单链表插入",
                learner_goal="理解指针变化",
                code_language="C",
            )
        )

        assert [item.resource_type for item in result.resources] == list(LearningResourceType)
        assert result.failures == ()
        assert all(item.review_status == "pending" for item in result.resources)
        assert all(item.prompt_version == RESOURCE_PROMPT_VERSION for item in result.resources)
        code = result.resources[1].content
        assert code["language"] == "C"
        assert code["display_only"] is True
        assert len(result.resources[2].content["items"]) == 3
        assert all(retry_safe for _, retry_safe in gateway.requests)
        assert "Requested code language: C." in gateway.requests[1][0].prompt.messages[-1].content

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "broken_result",
    [
        ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE),
        StructuredResult(
            value=envelope("code", {"language": "C", "source": "missing fields"}),
            model_id="model-a",
        ),
    ],
)
def test_provider_or_missing_fields_become_understandable_per_resource_failure(
    broken_result: StructuredResult | ProviderError,
) -> None:
    async def exercise() -> None:
        results: dict[LearningResourceType, StructuredResult | ProviderError] = valid_results()
        results[LearningResourceType.CODE] = broken_result
        result = await LearningUnitGenerator(StubGateway(results)).generate(
            LearningResourceRequest("单链表插入", "理解指针变化", "C")
        )

        assert [item.resource_type for item in result.resources] == [
            LearningResourceType.EXPLANATION,
            LearningResourceType.EXERCISE,
        ]
        assert len(result.failures) == 1
        failure = result.failures[0]
        assert failure.resource_type is LearningResourceType.CODE
        assert failure.message
        if isinstance(broken_result, ProviderError):
            assert failure.code is ProviderErrorCode.TEMPORARILY_UNAVAILABLE
        else:
            assert failure.code is ProviderErrorCode.INVALID_OUTPUT

    asyncio.run(exercise())


def test_missing_generation_context_fails_before_provider_call() -> None:
    with pytest.raises(ResourceGenerationInputError, match="knowledge point"):
        LearningResourceRequest("", "学习", "C")
