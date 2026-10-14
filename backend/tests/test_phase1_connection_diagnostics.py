"""Synthetic compressed/uncompressed responses; no real Provider or credentials."""

import asyncio
import gzip
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acceptance_support.connection_diagnostics import RecordingOperation  # noqa: E402
from run_phase1_provider_connection import AuditedTransport, public_bodies  # noqa: E402
from test_provider_connection_gateway import PROMPT, Harness, result  # noqa: E402

from app.services.openai_compatible import OpenAICompatibleAdapter


class Bytes(httpx.AsyncByteStream):
    def __init__(self, body):
        self.body = body

    async def __aiter__(self):
        yield self.body


@pytest.mark.parametrize("compressed", [True, False])
def test_decoder_observer_keeps_real_usage_without_persisting_content(compressed):
    async def run():
        body = json.dumps(result("OK")).encode()
        wire = gzip.compress(body) if compressed else body
        headers = {"content-encoding": "gzip"} if compressed else {}
        harness = Harness(lambda request: httpx.Response(200, headers=headers, stream=Bytes(wire)))
        recording = RecordingOperation(harness)
        answer = await OpenAICompatibleAdapter(recording).generate_text(PROMPT)
        assert answer.text == "OK"
        summary = recording.summary()
        assert summary["json_object"] and not summary["has_error"]
        assert summary["choices_count"] == 1
        assert (summary["input_tokens"], summary["output_tokens"]) == (4, 2)
        assert summary["content_encoding"] == ("gzip" if compressed else "identity")
        assert "content" not in summary and "model" not in summary

    asyncio.run(run())


def test_healthy_model_punctuation_can_trigger_old_runner_generic_error():
    async def run():
        answer = await OpenAICompatibleAdapter(
            Harness(lambda request: httpx.Response(200, json=result("OK.")))
        ).generate_text(PROMPT)
        assert answer.text == "OK." and answer.usage.input_tokens == 4
        with pytest.raises(ValueError, match="INVALID_OUTPUT"):
            # Frozen r01 classifies this local check as TEMPORARILY_UNAVAILABLE.
            if answer.text.strip() != "OK":
                raise ValueError("INVALID_OUTPUT")

    asyncio.run(run())


def test_frozen_wire_observer_cannot_parse_gzip_usage():
    audit = AuditedTransport(public_bodies()["text"])
    audit.payload.extend(gzip.compress(json.dumps(result("OK")).encode()))
    with pytest.raises(Exception):
        audit.usage()
    asyncio.run(audit.aclose())
