"""Actual production adapter and bounded error transport; no Provider requests."""
# ruff: noqa: E402

import asyncio
import gzip
import json
import sys
import zlib
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
    str(ROOT / "backend/tests"),
    str(ROOT / "scripts/tests"),
]
from app.services.qwen_schema import QWEN_SCHEMA_PROFILE, qwen_wire_schema
from app.services.openai_compatible import OpenAICompatibleAdapter
from app.services.provider_gateway import ProviderError, StructuredRequest
from acceptance_support.provider_error_decode import (
    RAW_LIMIT,
    DECODED_LIMIT,
    read_error,
)
from acceptance_support.qwen_compatibility_transport import QwenCompatibilityTransport
from test_provider_connection_gateway import (
    Harness,
    request_for,
    PROMPT,
    result,
    Chunks,
)
from test_evidence_v45 import answer

CASES = json.loads(
    (ROOT / "docs/acceptance/phase-1-review-model-candidate-r01/cases.json").read_text()
)
CASE = next(iter(CASES.values()))
BODY = json.loads(bytes.fromhex(CASE["candidate_wire_hex"]))
FULL = BODY["response_format"]["json_schema"]["schema"]


def test_projection_preserves_full_business_schema_and_prunes_transitive_defs():
    before = deepcopy(FULL)
    wire = qwen_wire_schema(FULL)
    assert FULL == before and wire != FULL
    assert (
        FULL["properties"]["coverage"]["properties"]["checked"]["uniqueItems"] is True
    )
    assert "uniqueItems" not in wire["properties"]["coverage"]["properties"]["checked"]
    assert set(wire["$defs"]) < set(FULL["$defs"])
    Draft202012Validator.check_schema(wire)
    # A property named uniqueItems is data, not a Schema keyword.
    projected = qwen_wire_schema(
        {
            "type": "object",
            "properties": {"uniqueItems": {"type": "array", "uniqueItems": True}},
        }
    )
    assert projected["properties"]["uniqueItems"] == {"type": "array"}
    source = {
        "$ref": "#/$defs/a",
        "$defs": {
            "a": {"$ref": "#/$defs/b"},
            "b": {"type": "object", "properties": {"next": {"$ref": "#/$defs/a"}}},
            "unused": {"multipleOf": 3},
        },
    }
    assert set(qwen_wire_schema(source)["$defs"]) == {"a", "b"}


def test_unknown_keyword_and_ref_rejected_before_send():
    for schema in (
        {"type": "integer", "multipleOf": 2},
        {"$ref": "https://example.com/schema"},
        {"$ref": "#/$defs/missing"},
    ):
        with pytest.raises(ValueError):
            qwen_wire_schema(schema)


@pytest.mark.parametrize("duplicate", [False, True])
def test_actual_adapter_wire_and_original_local_validation(duplicate):
    value = answer(CASE)
    if duplicate:
        value["coverage"]["checked"][-1] = value["coverage"]["checked"][0]
    request = request_for()
    request = replace(
        request,
        capabilities=replace(request.capabilities, schema_profile=QWEN_SCHEMA_PROFILE),
    )
    harness = Harness(
        lambda _: httpx.Response(200, json=result(json.dumps(value))), request
    )

    async def run():
        if duplicate:
            with pytest.raises(ProviderError):
                await OpenAICompatibleAdapter(harness).generate_structured(
                    StructuredRequest(PROMPT, FULL)
                )
        else:
            response = await OpenAICompatibleAdapter(harness).generate_structured(
                StructuredRequest(PROMPT, FULL)
            )
            assert response.value == value

    asyncio.run(run())
    sent = harness.calls[0]["response_format"]["json_schema"]["schema"]
    assert sent == qwen_wire_schema(FULL)
    if duplicate:
        Draft202012Validator(sent).validate(value)
        with pytest.raises(ValidationError):
            Draft202012Validator(FULL).validate(value)


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate"])
def test_json_error_decode_and_unique_items(encoding):
    payload = json.dumps(
        {
            "error": {
                "code": "InvalidParameter",
                "message": "uniqueItems is not supported; sk-SECRET_DO_NOT_LOG https://private.example",
                "private-field": "secret",
            }
        }
    ).encode()
    raw = (
        payload
        if encoding == "identity"
        else gzip.compress(payload)
        if encoding == "gzip"
        else zlib.compress(payload)
    )
    response = httpx.Response(
        400,
        headers={
            "content-encoding": encoding,
            "content-type": "application/json; charset=utf-8",
        },
        stream=Chunks([raw[:5], raw[5:]]),
    )
    observation = asyncio.run(read_error(response, json.dumps(BODY).encode()))
    assert observation["parse"] == "JSON_ERROR_OBJECT" and observation["raw_complete"]
    assert (
        observation["code"] == "InvalidParameter"
        and "uniqueItems" in observation["technical_message_tokens"]
    )
    assert observation["raw_bytes"] == len(raw) and observation["decoded_bytes"] == len(
        payload
    )
    assert observation["fields"] == {"code": "str", "message": "str"}
    assert "SECRET" not in json.dumps(observation) and "private" not in json.dumps(
        observation
    )


@pytest.mark.parametrize(
    "raw,encoding,expected",
    [
        (b"<html>secret gateway</html>", "identity", "NON_JSON"),
        (b"[]", "identity", "JSON_NON_OBJECT"),
        (b'{"error":"secret"}', "identity", "JSON_NON_OBJECT_ERROR"),
        (gzip.compress(b"{}")[:-3], "gzip", "TRUNCATED_COMPRESSION"),
        (b"bad-gzip", "gzip", "INVALID_COMPRESSION"),
        (b"data", "br", "UNSUPPORTED_ENCODING"),
        (b"data", "gzip, br", "UNSUPPORTED_ENCODING"),
        (b"x" * (RAW_LIMIT + 1), "identity", "RAW_LIMIT"),
        (gzip.compress(b"x" * (DECODED_LIMIT + 1)), "gzip", "DECODED_LIMIT"),
        (
            gzip.compress(b"{}") + gzip.compress(b"{}"),
            "gzip",
            "TRAILING_OR_EXCESS_DATA",
        ),
    ],
)
def test_bad_responses_are_bounded_and_classified(raw, encoding, expected):
    response = httpx.Response(
        400,
        headers={"content-encoding": encoding, "content-type": "text/html; secret=abc"},
        stream=Chunks([raw]),
    )
    observation = asyncio.run(read_error(response, b"{}"))
    assert observation["parse"] == expected
    assert observation["decoded_bytes"] <= DECODED_LIMIT
    assert response.is_closed and "secret" not in json.dumps(observation)


def test_real_raw_transport_error_consumes_compressed_body_once():
    raw = gzip.compress(
        b'{"error":{"code":"InvalidParameter","message":"uniqueItems is not supported"}}'
    )
    seen = []

    def handler(req):
        seen.append(req.content)
        return httpx.Response(
            400,
            headers={"content-encoding": "gzip", "content-type": "application/json"},
            stream=Chunks([raw]),
        )

    async def run():
        transport = QwenCompatibilityTransport(
            b"{}", "https://chosen.test/v1", httpx.MockTransport(handler)
        )
        request = httpx.Request(
            "POST",
            "https://8.8.8.8/v1/chat/completions",
            headers={"host": "chosen.test"},
            extensions={"sni_hostname": "chosen.test"},
            content=b"{}",
        )
        response = await transport.handle_async_request(request)
        assert response.status_code == 400
        assert transport.error_diagnosis["parse"] == "JSON_ERROR_OBJECT"
        assert transport.error_diagnosis["content_encoding"] == "gzip"
        assert transport.error_diagnosis["raw_bytes"] == len(raw)
        await transport.aclose()

    asyncio.run(run())
    assert seen == [b"{}"]


@pytest.mark.skipif(
    not __import__("os").getenv("EDUMIND_TEST_DATABASE_URL"),
    reason="dedicated PostgreSQL required",
)
@pytest.mark.parametrize(
    "variant", ["valid", "duplicate", "json-error", "gzip-error", "html-error"]
)
def test_complete_review_once_real_dispatch_and_cleanup(variant):
    import os
    from acceptance_support.qwen_review_attempt import perform, AttemptFailure

    body = deepcopy(BODY)
    body["response_format"]["json_schema"]["schema"] = qwen_wire_schema(FULL)
    wire = httpx.Request(
        "POST", "https://chosen.test/v1/chat/completions", json=body
    ).content
    value = answer(CASE)
    if variant == "duplicate":
        value["coverage"]["checked"][-1] = value["coverage"]["checked"][0]
    seen = []

    def handler(req):
        seen.append(req.content)
        assert req.content == wire
        assert json.loads(req.content)["response_format"]["json_schema"][
            "schema"
        ] == qwen_wire_schema(FULL)
        if variant.endswith("error"):
            raw = (
                b"<html>private secret</html>"
                if variant == "html-error"
                else b'{"error":{"code":"InvalidParameter","message":"uniqueItems is not supported"}}'
            )
            if variant == "gzip-error":
                raw = gzip.compress(raw)
            return httpx.Response(
                400,
                headers={
                    "content-type": "text/html"
                    if variant == "html-error"
                    else "application/json",
                    "content-encoding": "gzip"
                    if variant == "gzip-error"
                    else "identity",
                },
                stream=Chunks([raw]),
            )
        payload = result(json.dumps(value), model="qwen3.8-max-0902")
        return httpx.Response(200, stream=Chunks([json.dumps(payload).encode()]))

    async def authorize(request):
        assert request.capabilities.schema_profile == QWEN_SCHEMA_PROFILE
        assert request.route.model_id == "qwen3.8-max-0902"
        assert request.purpose == "connection_test"

    async def run():
        kwargs = dict(
            endpoint="https://chosen.test/v1",
            key="SYNTHETIC_COMPATIBILITY_KEY",
            database_url=os.environ["EDUMIND_TEST_DATABASE_URL"],
            authorize=authorize,
            transport=httpx.MockTransport(handler),
            resolver=lambda *_: ["8.8.8.8"],
            schema_profile=QWEN_SCHEMA_PROFILE,
            audit_factory=QwenCompatibilityTransport,
        )
        if variant == "valid":
            outcome = await perform(CASE, wire, **kwargs)
            assert outcome["review_record"]["result"] == value
            assert (
                outcome["review_record"]["request_digest"]
                == __import__("hashlib").sha256(wire).hexdigest()
            )
            assert all(outcome["cleanup"].values())
        else:
            with pytest.raises(AttemptFailure) as caught:
                await perform(CASE, wire, **kwargs)
            obs = caught.value.observation
            assert all(obs["cleanup"].values())
            if variant == "duplicate":
                assert obs["normalized_error"] == "INVALID_OUTPUT"
            else:
                assert obs["http_status"] == 400
                assert obs["provider_error"]["parse"] == (
                    "NON_JSON" if variant == "html-error" else "JSON_ERROR_OBJECT"
                )
                if variant == "gzip-error":
                    assert obs["provider_error"]["content_encoding"] == "gzip"

    asyncio.run(run())
    assert len(seen) == 1
