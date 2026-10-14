"""Offline Responses probe observers; no actual key, model request or DNS."""

import asyncio
import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from run_deepseek_connection import MODEL, Audit, bodies, observe  # noqa: E402


def response():
    return {
        "model": MODEL,
        "status": "completed",
        "error": None,
        "output": [{"type": "function_call", "name": "emit_probe", "arguments": '{"ok":true}'}],
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }


def test_requests_are_public_bounded_and_thinking_disabled():
    assert list(bodies()) == ["text", "structured", "tool", "stream"]
    for body in bodies().values():
        assert body["model"] == MODEL and body["max_output_tokens"] == 128
        assert body["reasoning"] == {"effort": "none"}
        assert len(json.dumps(body).encode()) < 4096
    assert bodies()["tool"]["tool_choice"] == "auto"
    assert bodies()["structured"]["text"]["format"]["type"] == "json_schema"


@pytest.mark.parametrize("streaming,compressed", [(False, False), (False, True), (True, True)])
def test_gzip_and_responses_terminal_usage_are_observed(streaming, compressed):
    raw = response()
    data = (
        (b"data: " + json.dumps({"type": "response.completed", "response": raw}).encode() + b"\n\n")
        if streaming
        else json.dumps(raw).encode()
    )
    audit = Audit(bodies()["stream" if streaming else "tool"])
    audit.encoding = "gzip" if compressed else "identity"
    audit.payload.extend(gzip.compress(data) if compressed else data)
    summary = audit.observation(streaming)
    assert summary["completed"] and summary["model_matches"]
    assert summary["input_tokens"] == 12 and summary["output_tokens"] == 8
    assert summary["arguments_schema_valid"]
    asyncio.run(audit.aclose())


def test_wrong_tool_boolean_or_model_never_passes():
    raw = response()
    raw["output"][0]["arguments"] = '{"ok":1}'
    raw["model"] = "PRIVATE_CANARY"
    summary = observe(raw)
    assert not summary["arguments_schema_valid"] and not summary["model_matches"]
    assert "PRIVATE_CANARY" not in json.dumps(summary)
    assert observe(None)["input_tokens"] is None
