import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diagnose_qwen_http400 import safe_error


def test_specific_schema_reason_and_no_unknown_values():
    wire = json.dumps(
        {
            "response_format": {
                "json_schema": {
                    "schema": {"properties": {"unresolved": {"type": "array"}}}
                }
            }
        }
    ).encode()
    raw = json.dumps(
        {
            "error": {
                "code": "InvalidParameter",
                "message": "Schema depth exceeded maximum 5 at unresolved. secret-value sk-abcdefgh1234567890 https://example.com",
            }
        }
    ).encode()
    result = safe_error(raw, wire)
    assert result["code"] == "InvalidParameter"
    assert result["technical_message_tokens"][:9] == [
        "Schema",
        "depth",
        "exceeded",
        "maximum",
        "5",
        "at",
        "unresolved",
        ".",
        "[redacted]",
    ]
    for secret in ("secret-value", "sk-abcdefgh1234567890", "example"):
        assert secret not in json.dumps(result)


def test_non_json_and_unknown_code():
    assert safe_error(b"not json", b"{}")["parse"] == "NON_JSON_OR_UNRECOGNIZED"
    assert (
        safe_error(b'{"error":{"code":"secret","message":"credential"}}', b"{}")["code"]
        == "UNRECOGNIZED_REDACTED"
    )


def test_transport_consumes_error_body_once_without_raw_message():
    import asyncio
    import httpx
    from diagnose_qwen_http400 import ErrorTransport

    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": "InvalidParameter",
                        "message": "additionalProperties must be false",
                    }
                },
            )

        wire = b"{}"
        transport = ErrorTransport(
            wire, "https://example.com/v1", httpx.MockTransport(handler)
        )
        req = httpx.Request(
            "POST",
            "https://8.8.8.8/v1/chat/completions",
            headers={"host": "example.com"},
            content=wire,
            extensions={"sni_hostname": "example.com"},
        )
        response = await transport.handle_async_request(req)
        assert response.status_code == 400 and response.content == b""
        assert len(calls) == 1 and transport.raw_complete
        assert ErrorTransport.diagnosis["technical_message_tokens"] == [
            "additionalProperties",
            "must",
            "be",
            "false",
        ]
        await transport.aclose()

    asyncio.run(run())
