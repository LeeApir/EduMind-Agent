"""Offline guard tests: no provider credentials or remote connections."""

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from run_phase1_provider_connection import (  # noqa: E402
    MODEL,
    AuditedTransport,
    canonical,
    public_bodies,
    verify_tool,
)


def test_fixed_slots_are_bounded_public_and_stream_is_last():
    bodies = public_bodies()
    assert list(bodies) == ["text", "structured", "tool", "stream"]
    for body in bodies.values():
        assert body["model"] == MODEL
        assert body["enable_thinking"] is False
        assert body["max_completion_tokens"] == 64
        assert "max_tokens" not in body
        assert len(canonical(body)) < 4096
        assert len(body["messages"]) == 1
    assert bodies["stream"]["stream"] is True


def test_transport_refuses_changed_body_and_duplicate_send():
    async def run():
        body = public_bodies()["text"]
        audit = AuditedTransport(body)
        await audit.inner.aclose()
        calls = []
        audit.inner = httpx.MockTransport(
            lambda request: calls.append(1) or httpx.Response(200, json={})
        )
        with pytest.raises(ValueError, match="TARGET_CHANGED"):
            await audit.handle_async_request(httpx.Request("POST", "https://example.org", json={}))
        assert audit.sent == 0 and not calls
        async with httpx.AsyncClient(transport=audit) as client:
            await client.post("https://example.org", json=body)
            with pytest.raises(ValueError, match="TARGET_CHANGED"):
                await client.post("https://example.org", json=body)
        assert len(calls) == audit.sent == 1
        assert audit.usage() == (None, None)

    asyncio.run(run())


@pytest.mark.parametrize(
    "arguments,valid",
    [
        ('{"ok":true}', True),
        ('{"ok":1}', False),
        ('{"ok":false}', False),
        ('{"ok":true,"extra":1}', False),
    ],
)
def test_tool_probe_validates_only_literal_boolean_and_never_executes(arguments, valid):
    raw = {
        "model": MODEL,
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "emit_probe", "arguments": arguments},
                        }
                    ]
                },
            }
        ],
    }
    if valid:
        verify_tool(raw)
    else:
        with pytest.raises(ValueError):
            verify_tool(raw)
