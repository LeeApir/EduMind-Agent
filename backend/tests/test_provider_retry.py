"""Stable error mapping and explicitly bounded same-provider retries."""

import asyncio
from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from app.core.config import ProviderSettings
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.openai_compatible import OpenAICompatibleAdapter
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
    RetryPolicy,
    StructuredRequest,
    StructuredResult,
    TextDelta,
    TextRequest,
    TextResult,
)


def prompt() -> TextRequest:
    return TextRequest(messages=(ChatMessage(role="user", content="hello"),))


def network_adapter(handler: Callable[[httpx.Request], httpx.Response]) -> OpenAICompatibleAdapter:
    settings = ProviderSettings(
        base_url="https://provider.test/v1", api_key="test-secret", model="server-model"
    )
    guard = ProviderTargetGuard(
        settings.base_url, TargetPolicy(), resolver=lambda _host, _port: ("8.8.8.8",)
    )
    return OpenAICompatibleAdapter(settings, guard, transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, ProviderErrorCode.CAPABILITY_UNAVAILABLE),
        (401, ProviderErrorCode.AUTHENTICATION_FAILED),
        (403, ProviderErrorCode.AUTHENTICATION_FAILED),
        (408, ProviderErrorCode.TIMEOUT),
        (429, ProviderErrorCode.RATE_LIMITED),
        (500, ProviderErrorCode.TEMPORARILY_UNAVAILABLE),
        (501, ProviderErrorCode.CAPABILITY_UNAVAILABLE),
        (503, ProviderErrorCode.TEMPORARILY_UNAVAILABLE),
        (504, ProviderErrorCode.TIMEOUT),
    ],
)
def test_http_errors_are_mapped_without_vendor_body(status: int, code: ProviderErrorCode) -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers={"Retry-After": "2"} if status == 429 else {},
            text="test-secret upstream private detail",
        )

    with pytest.raises(ProviderError) as raised:
        asyncio.run(network_adapter(respond).generate_text(prompt()))
    assert raised.value.code == code
    assert raised.value.retry_after_seconds == (2.0 if status == 429 else None)
    assert "test-secret" not in str(raised.value)
    assert "private detail" not in str(raised.value)


class ScriptedAdapter:
    def __init__(self, failures: int, code: ProviderErrorCode) -> None:
        self.failures = failures
        self.code = code
        self.text_calls = 0
        self.structured_calls = 0
        self.stream_calls = 0

    async def generate_text(self, _request: TextRequest) -> TextResult:
        self.text_calls += 1
        if self.text_calls <= self.failures:
            raise ProviderError(self.code)
        return TextResult(text="success", model_id="one-provider")

    async def generate_structured(self, _request: StructuredRequest) -> StructuredResult:
        self.structured_calls += 1
        if self.structured_calls <= self.failures:
            raise ProviderError(self.code)
        return StructuredResult(value={"ok": True}, model_id="one-provider")

    async def stream_text(self, _request: TextRequest) -> AsyncIterator[TextDelta]:
        self.stream_calls += 1
        yield TextDelta(text="partial")
        raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)


def test_retry_requires_explicit_safety_and_uses_same_adapter_only() -> None:
    adapter = ScriptedAdapter(failures=2, code=ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
    delays: list[float] = []

    async def no_sleep(delay: float) -> None:
        delays.append(delay)

    gateway = ProviderGateway(adapter, sleep=no_sleep)
    with pytest.raises(ProviderError):
        asyncio.run(gateway.generate_text(prompt()))
    assert adapter.text_calls == 1
    assert delays == []

    result = asyncio.run(gateway.generate_text(prompt(), retry_safe=True))
    assert result.model_id == "one-provider"
    assert adapter.text_calls == 3
    assert delays == [0.25]


def test_retry_budget_is_capped_and_nonretryable_errors_are_not_replayed() -> None:
    adapter = ScriptedAdapter(failures=10, code=ProviderErrorCode.TIMEOUT)
    delays: list[float] = []

    async def no_sleep(delay: float) -> None:
        delays.append(delay)

    gateway = ProviderGateway(adapter, sleep=no_sleep)
    with pytest.raises(ProviderError) as raised:
        asyncio.run(gateway.generate_text(prompt(), retry_safe=True))
    assert raised.value.code == ProviderErrorCode.TIMEOUT
    assert adapter.text_calls == 3
    assert delays == [0.25, 0.5]

    invalid = ScriptedAdapter(failures=10, code=ProviderErrorCode.INVALID_OUTPUT)
    with pytest.raises(ProviderError):
        asyncio.run(
            ProviderGateway(invalid, sleep=no_sleep).generate_text(prompt(), retry_safe=True)
        )
    assert invalid.text_calls == 1


def test_structured_retry_is_explicit_and_no_stream_retry_after_partial_output() -> None:
    adapter = ScriptedAdapter(failures=1, code=ProviderErrorCode.RATE_LIMITED)

    async def no_sleep(_delay: float) -> None:
        return None

    gateway = ProviderGateway(adapter, sleep=no_sleep)
    structured = StructuredRequest(prompt=prompt(), json_schema={"type": "object"})
    assert asyncio.run(gateway.generate_structured(structured, retry_safe=True)).value == {
        "ok": True
    }
    assert adapter.structured_calls == 2

    async def collect() -> list[str]:
        seen: list[str] = []
        async for delta in gateway.stream_text(prompt()):
            seen.append(delta.text)
        return seen

    with pytest.raises(ProviderError):
        asyncio.run(collect())
    assert adapter.stream_calls == 1


def test_retry_after_above_budget_does_not_violate_provider_delay() -> None:
    class SlowRetryAdapter(ScriptedAdapter):
        async def generate_text(self, _request: TextRequest) -> TextResult:
            self.text_calls += 1
            raise ProviderError(ProviderErrorCode.RATE_LIMITED, retry_after_seconds=10)

    adapter = SlowRetryAdapter(failures=10, code=ProviderErrorCode.RATE_LIMITED)
    slept = False

    async def forbidden_sleep(_delay: float) -> None:
        nonlocal slept
        slept = True

    with pytest.raises(ProviderError) as raised:
        asyncio.run(
            ProviderGateway(adapter, sleep=forbidden_sleep).generate_text(
                prompt(), retry_safe=True
            )
        )
    assert raised.value.code == ProviderErrorCode.RATE_LIMITED
    assert adapter.text_calls == 1
    assert not slept

    def long_retry(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "Fri, 01 Jan 2100 00:00:00 GMT"})

    with pytest.raises(ProviderError) as raised:
        asyncio.run(network_adapter(long_retry).generate_text(prompt()))
    assert raised.value.retry_after_seconds is not None
    assert raised.value.retry_after_seconds > 5


def test_retry_policy_cannot_exceed_three_attempts() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=4)
    with pytest.raises(ValueError):
        RetryPolicy(max_delay_seconds=float("inf"))
