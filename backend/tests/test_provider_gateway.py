"""Provider-neutral gateway contract using replaceable in-memory adapters."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
    StructuredRequest,
    StructuredResult,
    TaskProfile,
    TextDelta,
    TextRequest,
    TextResult,
    TokenUsage,
)


class FakeAdapter:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[str] = []

    async def generate_text(self, request: TextRequest) -> TextResult:
        self.calls.append("text")
        assert request.task_profile == TaskProfile.QUALITY
        return TextResult(
            text=f"{self.label}: {request.messages[-1].content}",
            model_id=f"{self.label}-model",
            usage=TokenUsage(input_tokens=5, output_tokens=6),
        )

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        self.calls.append("structured")
        assert request.json_schema["type"] == "object"
        return StructuredResult(value={"answer": self.label}, model_id=f"{self.label}-model")

    async def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]:
        self.calls.append("stream")
        assert request.messages[-1].content == "Explain linked lists"
        yield TextDelta(text=self.label)
        yield TextDelta(text=" done")


def test_business_consumer_can_swap_adapters_without_vendor_types() -> None:
    prompt = TextRequest(
        messages=(ChatMessage(role="user", content="Explain linked lists"),),
        task_profile=TaskProfile.QUALITY,
    )
    structured = StructuredRequest(
        prompt=prompt,
        json_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
    )

    async def business_consumer(gateway: ProviderGateway) -> tuple[str, object, str]:
        text = await gateway.generate_text(prompt)
        data = await gateway.generate_structured(structured)
        streamed = "".join([delta.text async for delta in gateway.stream_text(prompt)])
        assert text.usage == TokenUsage(input_tokens=5, output_tokens=6)
        return text.text, data.value["answer"], streamed

    first = FakeAdapter("alpha")
    second = FakeAdapter("beta")
    assert asyncio.run(business_consumer(ProviderGateway(first))) == (
        "alpha: Explain linked lists",
        "alpha",
        "alpha done",
    )
    assert asyncio.run(business_consumer(ProviderGateway(second))) == (
        "beta: Explain linked lists",
        "beta",
        "beta done",
    )
    assert first.calls == second.calls == ["text", "structured", "stream"]


def test_gateway_does_not_retry_or_switch_a_failing_adapter() -> None:
    class FailingAdapter(FakeAdapter):
        async def generate_text(self, request: TextRequest) -> TextResult:
            self.calls.append("text")
            raise ProviderError(ProviderErrorCode.RATE_LIMITED, retry_after_seconds=3)

    adapter = FailingAdapter("primary")
    gateway = ProviderGateway(adapter)
    request = TextRequest(messages=(ChatMessage(role="user", content="hello"),))

    with pytest.raises(ProviderError) as raised:
        asyncio.run(gateway.generate_text(request))

    assert raised.value.code == ProviderErrorCode.RATE_LIMITED
    assert raised.value.retryable is True
    assert raised.value.retry_after_seconds == 3
    assert adapter.calls == ["text"]


def test_error_codes_have_safe_fixed_messages_and_explicit_retryability() -> None:
    retryable = {
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.TEMPORARILY_UNAVAILABLE,
        ProviderErrorCode.TIMEOUT,
    }
    for code in ProviderErrorCode:
        error = ProviderError(code)
        assert error.code == code
        assert error.retryable is (code in retryable)
        assert code.value not in str(error)
        assert "secret-key" not in str(error)
