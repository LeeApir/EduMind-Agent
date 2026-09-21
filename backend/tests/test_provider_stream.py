"""Chunked SSE, Unicode, interruption and connection-lifetime regressions."""

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from app.core.config import ProviderSettings
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
    TextRequest,
)


class FragmentedStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], *, fail_after: int | None = None) -> None:
        self.chunks = chunks
        self.fail_after = fail_after
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, chunk in enumerate(self.chunks):
            if self.fail_after == index:
                raise httpx.ReadError("private upstream detail")
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


def frame(event_type: str, **payload: object) -> bytes:
    event = {"type": event_type, "sequence_number": 1, **payload}
    return (
        f"event: {event_type}\r\ndata: ".encode()
        + json.dumps(event, ensure_ascii=False).encode("utf-8")
        + b"\r\n\r\n"
    )


def create_adapter(stream: FragmentedStream) -> DeepSeekResponsesAdapter:
    settings = ProviderSettings(
        base_url="https://stream.provider.test/v1", api_key="test-secret", model="server-model"
    )
    guard = ProviderTargetGuard(
        settings.base_url, TargetPolicy(), resolver=lambda _host, _port: ("8.8.8.8",)
    )

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://8.8.8.8/v1/responses"
        assert request.headers["Host"] == "stream.provider.test"
        assert request.extensions["sni_hostname"] == "stream.provider.test"
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert request.headers["Accept"] == "text/event-stream"
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["model"] == "server-model"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    return DeepSeekResponsesAdapter(settings, guard, transport=httpx.MockTransport(respond))


def request() -> TextRequest:
    return TextRequest(messages=(ChatMessage(role="user", content="讲链表"),))


def test_unicode_and_sse_frames_split_at_every_byte() -> None:
    wire = (
        b": heartbeat\r\n\r\n"
        + frame("response.created", response={"status": "in_progress"})
        + frame("response.reasoning_text.delta", delta="private")
        + frame("response.output_text.delta", delta="链")
        + frame("response.output_text.delta", delta="表🙂")
        + frame("response.output_text.done", text="链表🙂")
        + frame("response.completed", response={"status": "completed"})
    )
    stream = FragmentedStream([bytes([byte]) for byte in wire])

    async def collect() -> list[str]:
        return [delta.text async for delta in create_adapter(stream).stream_text(request())]

    assert asyncio.run(collect()) == ["链", "表🙂"]
    assert stream.closed


def test_progress_events_before_completed_are_ignored() -> None:
    stream = FragmentedStream(
        [
            frame("response.in_progress"),
            frame("response.output_text.delta", delta="ok"),
            frame("response.completed", response={"status": "completed"}),
        ]
    )

    async def collect() -> list[str]:
        return [delta.text async for delta in create_adapter(stream).stream_text(request())]

    assert asyncio.run(collect()) == ["ok"]
    assert stream.closed


@pytest.mark.parametrize(
    "wire",
    [
        b"data: not-json\n\n",
        b"data: {\"type\":3}\n\n",
        b"data: \xff\n\n",
        frame("response.incomplete", response={"status": "incomplete"}),
        frame("response.completed", response={"status": "completed"}),
    ],
)
def test_invalid_frames_raise_safe_error_and_close(wire: bytes) -> None:
    stream = FragmentedStream([wire])

    async def collect() -> list[str]:
        return [delta.text async for delta in create_adapter(stream).stream_text(request())]

    with pytest.raises(ProviderError) as raised:
        asyncio.run(collect())
    assert raised.value.code == ProviderErrorCode.INVALID_OUTPUT
    assert "test-secret" not in str(raised.value)
    assert stream.closed


def test_upstream_eof_without_done_reports_interruption_and_closes() -> None:
    stream = FragmentedStream([frame("response.output_text.delta", delta="partial")])

    async def collect() -> list[str]:
        seen: list[str] = []
        async for delta in create_adapter(stream).stream_text(request()):
            seen.append(delta.text)
        return seen

    with pytest.raises(ProviderError) as raised:
        asyncio.run(collect())
    assert raised.value.code == ProviderErrorCode.TEMPORARILY_UNAVAILABLE
    assert stream.closed


def test_upstream_read_error_is_sanitized_and_closes() -> None:
    stream = FragmentedStream(
        [
            frame("response.output_text.delta", delta="partial"),
            frame("response.completed", response={"status": "completed"}),
        ],
        fail_after=1,
    )

    async def collect() -> None:
        async for _delta in create_adapter(stream).stream_text(request()):
            pass

    with pytest.raises(ProviderError) as raised:
        asyncio.run(collect())
    assert raised.value.code == ProviderErrorCode.TEMPORARILY_UNAVAILABLE
    assert "private upstream detail" not in str(raised.value)
    assert stream.closed


def test_response_failed_is_sanitized_temporary_failure_and_closes() -> None:
    stream = FragmentedStream(
        [
            frame("response.output_text.delta", delta="partial"),
            frame(
                "response.failed",
                response={
                    "status": "failed",
                    "error": {"message": "test-secret private upstream detail"},
                },
            ),
        ]
    )

    async def collect() -> None:
        async for _delta in create_adapter(stream).stream_text(request()):
            pass

    with pytest.raises(ProviderError) as raised:
        asyncio.run(collect())
    assert raised.value.code == ProviderErrorCode.TEMPORARILY_UNAVAILABLE
    assert "test-secret" not in str(raised.value)
    assert "private upstream detail" not in str(raised.value)
    assert stream.closed


def test_consumer_cancellation_closes_adapter_and_gateway_stream() -> None:
    async def stop_after_first(use_gateway: bool) -> bool:
        stream = FragmentedStream(
            [
                frame("response.output_text.delta", delta="first"),
                frame("response.output_text.delta", delta="second"),
                frame("response.completed", response={"status": "completed"}),
            ]
        )
        adapter = create_adapter(stream)
        source = ProviderGateway(adapter) if use_gateway else adapter
        iterator = source.stream_text(request())
        assert (await anext(iterator)).text == "first"
        await iterator.aclose()
        return stream.closed

    assert asyncio.run(stop_after_first(False))
    assert asyncio.run(stop_after_first(True))
