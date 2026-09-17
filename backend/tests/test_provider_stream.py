"""Chunked SSE, Unicode, interruption and connection-lifetime regressions."""

import asyncio
import json
from collections.abc import AsyncIterator

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


def frame(content: str | None = None, *, finish: str | None = None) -> bytes:
    chunk = {"choices": [{"delta": {"content": content}, "finish_reason": finish}]}
    return b"data: " + json.dumps(chunk, ensure_ascii=False).encode("utf-8") + b"\r\n\r\n"


def create_adapter(stream: FragmentedStream) -> OpenAICompatibleAdapter:
    settings = ProviderSettings(
        base_url="https://stream.provider.test/v1", api_key="test-secret", model="server-model"
    )
    guard = ProviderTargetGuard(
        settings.base_url, TargetPolicy(), resolver=lambda _host, _port: ("8.8.8.8",)
    )

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://8.8.8.8/v1/chat/completions"
        assert request.headers["Host"] == "stream.provider.test"
        assert request.extensions["sni_hostname"] == "stream.provider.test"
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert request.headers["Accept"] == "text/event-stream"
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["model"] == "server-model"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    return OpenAICompatibleAdapter(settings, guard, transport=httpx.MockTransport(respond))


def request() -> TextRequest:
    return TextRequest(messages=(ChatMessage(role="user", content="讲链表"),))


def test_unicode_and_sse_frames_split_at_every_byte() -> None:
    wire = (
        b": heartbeat\r\n\r\n"
        + frame(None)
        + frame("链")
        + frame("表🙂")
        + frame(None, finish="stop")
        + b"data: [DONE]\r\n\r\n"
    )
    stream = FragmentedStream([bytes([byte]) for byte in wire])

    async def collect() -> list[str]:
        return [delta.text async for delta in create_adapter(stream).stream_text(request())]

    assert asyncio.run(collect()) == ["链", "表🙂"]
    assert stream.closed


def test_usage_only_chunk_before_done_is_ignored() -> None:
    usage = b'data: {"choices":[],"usage":{"prompt_tokens":1}}\n\n'
    stream = FragmentedStream(
        [frame("ok", finish="stop"), usage, b"data: [DONE]\n\n"]
    )

    async def collect() -> list[str]:
        return [delta.text async for delta in create_adapter(stream).stream_text(request())]

    assert asyncio.run(collect()) == ["ok"]
    assert stream.closed


@pytest.mark.parametrize(
    "wire",
    [
        b"data: not-json\n\n",
        b"data: {\"choices\":{}}\n\n",
        b"data: \xff\n\n",
        frame("cut", finish="length"),
        b"data: [DONE]\n\n",
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
    stream = FragmentedStream([frame("partial"), frame(None, finish="stop")])

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
    stream = FragmentedStream([frame("partial"), b"data: [DONE]\n\n"], fail_after=1)

    async def collect() -> None:
        async for _delta in create_adapter(stream).stream_text(request()):
            pass

    with pytest.raises(ProviderError) as raised:
        asyncio.run(collect())
    assert raised.value.code == ProviderErrorCode.TEMPORARILY_UNAVAILABLE
    assert "private upstream detail" not in str(raised.value)
    assert stream.closed


def test_consumer_cancellation_closes_adapter_and_gateway_stream() -> None:
    async def stop_after_first(use_gateway: bool) -> bool:
        stream = FragmentedStream(
            [frame("first"), frame("second"), frame(None, finish="stop"), b"data: [DONE]\n\n"]
        )
        adapter = create_adapter(stream)
        source = ProviderGateway(adapter) if use_gateway else adapter
        iterator = source.stream_text(request())
        assert (await anext(iterator)).text == "first"
        await iterator.aclose()
        return stream.closed

    assert asyncio.run(stop_after_first(False))
    assert asyncio.run(stop_after_first(True))
