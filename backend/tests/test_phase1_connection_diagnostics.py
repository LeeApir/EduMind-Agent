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


@pytest.mark.parametrize(
    "wire,expected",
    [
        (
            b'data: {"model":"test","choices":[]}\r\n\r\n'
            b'data: {"usage":{"prompt_tokens":3,"completion_tokens":2},"choices":[]}\r\n\r\n'
            b"data: [DONE]\r\n\r\n",
            (3, 2),
        ),
        (b'data: {"choices":[]}\n\ndata: [DONE]\n\n', (None, None)),
        (b'data: {"usage":{"prompt_tokens":true,"completion_tokens":2}}\n\n', (None, 2)),
    ],
)
def test_stream_usage_is_read_from_decoded_complete_sse_frames(wire, expected):
    recorder = RecordingOperation(None)
    recorder.payload.extend(wire)
    summary = recorder.summary(streaming=True)
    assert (summary["input_tokens"], summary["output_tokens"]) == expected


def test_local_probe_failures_and_bugs_are_not_vendor_outages():
    from acceptance_support.connection_diagnostics import ProbeFailure, classify_failure

    from app.services.provider_gateway import ProviderError, ProviderErrorCode

    assert classify_failure(ProbeFailure("fixed_schema")) == ("INVALID_OUTPUT", "probe_validation")
    assert classify_failure(ValueError("private diagnostic message")) == (
        "SAFETY_FAILURE",
        "local_unexpected",
    )
    assert classify_failure(ProviderError(ProviderErrorCode.TIMEOUT)) == (
        "TIMEOUT",
        "provider_protocol",
    )


def test_compressed_stream_passes_production_parser_and_preserves_usage():
    from dataclasses import replace

    from test_provider_connection_gateway import frame, request_for

    async def run():
        req = request_for()
        req = replace(req, capabilities=replace(req.capabilities, include_stream_usage=True))
        usage = (
            'data: {"model":"selected-model","choices":[],"usage":'
            + '{"prompt_tokens":5,"completion_tokens":3}}\n\n'
        )
        wire = gzip.compress(
            (frame({"content": "OK."}) + frame(finish="stop") + usage + "data: [DONE]\n\n").encode()
        )
        harness = Harness(
            lambda request: httpx.Response(
                200, headers={"content-encoding": "gzip"}, stream=Bytes(wire)
            ),
            req,
        )
        recorder = RecordingOperation(harness)
        text = "".join(
            [delta.text async for delta in OpenAICompatibleAdapter(recorder).stream_text(PROMPT)]
        )
        assert text == "OK."
        summary = recorder.summary(streaming=True)
        assert (summary["input_tokens"], summary["output_tokens"]) == (5, 3)
        assert summary["content_encoding"] == "gzip"
        assert harness.calls[0]["stream_options"] == {"include_usage": True}

    asyncio.run(run())
