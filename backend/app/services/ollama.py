"""Native Ollama /api/chat adapter; explicit capabilities, no pulls or probing."""

import json
from collections.abc import AsyncIterator

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError, ValidationError  # type: ignore[import-untyped]

from app.services.deepseek_responses import _check_status, _reject_external_schema_refs
from app.services.provider_connection_dispatch import ConnectionOperation
from app.services.provider_gateway import (
    OutputFailureReason,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
    TextDelta,
    TextRequest,
    TextResult,
    TokenUsage,
)
from app.services.provider_protocol import (
    MAX_RESPONSE_BYTES,
    bounded_json,
    invalid_output,
    message_parameters,
    normal_finish,
    strict_json,
    validated_model,
)

MAX_LINE_BYTES = 1024 * 1024


def _usage(raw: dict[str, object]) -> TokenUsage | None:
    counts = [raw.get(name) for name in ("prompt_eval_count", "eval_count")]
    if any(v is not None and (type(v) is not int or v < 0) for v in counts):
        raise invalid_output()
    if all(v is None for v in counts):
        return None
    return TokenUsage(
        counts[0] if isinstance(counts[0], int) else None,
        counts[1] if isinstance(counts[1], int) else None,
    )


def _chat(raw: object) -> tuple[str, bool, str, TokenUsage | None]:
    if not isinstance(raw, dict):
        raise invalid_output()
    if "error" in raw:
        if isinstance(raw["error"], str) and raw["error"]:
            raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
        raise invalid_output()
    done = raw.get("done")
    if type(done) is not bool:
        raise invalid_output()
    model = validated_model(raw.get("model"))
    message = raw.get("message")
    if (
        not isinstance(message, dict)
        or message.get("role") != "assistant"
        or message.get("tool_calls")
        or message.get("images")
        or message.get("refusal")
        or not isinstance(message.get("content"), str)
    ):
        raise invalid_output()
    if done:
        normal_finish(raw.get("done_reason"))
    elif raw.get("done_reason") is not None:
        raise invalid_output()
    # Only visible content is exposed; separate thinking text stays upstream.
    return message["content"], done, model, _usage(raw)


async def _ndjson(chunks: AsyncIterator[bytes]) -> AsyncIterator[object]:
    buffer = bytearray()
    total = 0
    async for chunk in chunks:
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise invalid_output()
        buffer.extend(chunk)
        # Scan offsets and compact once: avoid quadratic copies and a huge empty-line list.
        start = 0
        while (end := buffer.find(b"\n", start)) >= 0:
            if end - start > MAX_LINE_BYTES:
                raise invalid_output()
            line = buffer[start:end]
            if line.strip():
                yield strict_json(bytes(line))
            start = end + 1
        if start:
            del buffer[:start]
        if len(buffer) > MAX_LINE_BYTES:
            raise invalid_output()
    # Accept a final bounded JSON record without a trailing LF, not an incomplete record.
    if buffer.strip():
        yield strict_json(bytes(buffer))


class OllamaAdapter:
    def __init__(self, operation: ConnectionOperation) -> None:
        self._operation = operation

    def __repr__(self) -> str:
        return "OllamaAdapter(<redacted>)"

    def _body(self, request: TextRequest) -> dict[str, object]:
        self._operation._check()
        messages, tokens, temperature = message_parameters(request)
        options: dict[str, object] = {"num_predict": tokens}
        if temperature is not None:
            options["temperature"] = temperature
        body: dict[str, object] = {
            "model": self._operation.request.route.model_id,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        bounded_json(body)
        return body

    async def _result(self, body: dict[str, object]) -> TextResult:
        bounded_json(body)
        async with self._operation.send(body) as response:
            _check_status(response)
            size = 0
            chunks = []
            async for chunk in response.aiter_bytes():
                self._operation._check()
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise invalid_output()
                chunks.append(chunk)
            text, done, model, usage = _chat(strict_json(b"".join(chunks)))
            if not done or not text.strip():
                raise invalid_output()
            self._operation._check()
            return TextResult(text, model, usage)

    async def generate_text(self, request: TextRequest) -> TextResult:
        return await self._result(self._body(request))

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        if self._operation.request.capabilities.structured_output is not True:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        try:
            schema = dict(request.json_schema)
            bounded_json(schema)
            _reject_external_schema_refs(schema)
            Draft202012Validator.check_schema(schema)
        except (TypeError, ValueError, RecursionError, SchemaError):
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.REQUEST_SCHEMA_INVALID,
            ) from None
        body = self._body(request.prompt)
        mode = self._operation.request.capabilities.structured_transport
        if mode not in {"json_schema", "json_object", "text_json"}:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        if mode == "json_schema":
            body["format"] = schema
        else:
            messages = body["messages"]
            assert isinstance(messages, list)
            body["messages"] = [
                {
                    "role": "system",
                    "content": (
                        "Return exactly one JSON object conforming to this schema, with no prose: "
                        + json.dumps(schema, ensure_ascii=False)
                    ),
                },
                *messages,
            ]
            if mode == "json_object":
                body["format"] = "json"
        result = await self._result(body)
        value = strict_json(result.text)
        if not isinstance(value, dict):
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.STRUCTURED_NOT_OBJECT,
                usage=result.usage,
            )
        try:
            Draft202012Validator(schema).validate(value)
        except (ValidationError, SchemaError, RecursionError):
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.STRUCTURED_SCHEMA_MISMATCH,
                schema_keyword="other",
                usage=result.usage,
            ) from None
        return StructuredResult(value, result.model_id, result.usage)

    async def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]:
        if self._operation.request.capabilities.streaming is not True:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        body = self._body(request)
        body["stream"] = True
        async with self._operation.send(body, stream=True) as response:
            _check_status(response)
            saw_text = False
            async for raw in _ndjson(response.aiter_bytes()):
                self._operation._check()
                text, done, _, _ = _chat(raw)
                if text:
                    saw_text = True
                    yield TextDelta(text)
                if done:
                    if not saw_text:
                        raise invalid_output()
                    return
            raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
