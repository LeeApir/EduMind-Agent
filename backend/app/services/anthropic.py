"""Native bounded Messages protocol behind the approved single-attempt send authority."""

import json
from collections.abc import AsyncIterator
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError, ValidationError  # type: ignore[import-untyped]

from app.services.deepseek_responses import _check_status, _reject_external_schema_refs, _sse_data
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
    strict_json,
    validated_model,
)

TOOL_NAME = "edumind_result"
ERROR_CODES = {
    "authentication_error": ProviderErrorCode.AUTHENTICATION_FAILED,
    "permission_error": ProviderErrorCode.AUTHENTICATION_FAILED,
    "rate_limit_error": ProviderErrorCode.RATE_LIMITED,
    "timeout_error": ProviderErrorCode.TIMEOUT,
    "overloaded_error": ProviderErrorCode.TEMPORARILY_UNAVAILABLE,
    "api_error": ProviderErrorCode.TEMPORARILY_UNAVAILABLE,
    "invalid_request_error": ProviderErrorCode.CAPABILITY_UNAVAILABLE,
    "not_found_error": ProviderErrorCode.CAPABILITY_UNAVAILABLE,
    "request_too_large": ProviderErrorCode.CAPABILITY_UNAVAILABLE,
}


def usage(raw: object) -> TokenUsage | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise invalid_output()
    counts = [raw.get(name) for name in ("input_tokens", "output_tokens")]
    if any(value is not None and (type(value) is not int or value < 0) for value in counts):
        raise invalid_output()
    if all(value is None for value in counts):
        return None
    return TokenUsage(counts[0], counts[1])


def finish(reason: object, *, tool: bool = False) -> None:
    if reason == "max_tokens":
        raise ProviderError(
            ProviderErrorCode.INVALID_OUTPUT,
            output_failure_reason=OutputFailureReason.OUTPUT_TOKEN_LIMIT,
        )
    if reason != ("tool_use" if tool else "end_turn"):
        raise invalid_output()


def message(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("type") != "message" or raw.get("role") != "assistant":
        raise invalid_output()
    validated_model(raw.get("model"))
    if (
        not isinstance(raw.get("content"), list)
        or len(raw["content"]) > 128
        or raw.get("stop_sequence") is not None
    ):
        raise invalid_output()
    usage(raw.get("usage"))
    return raw


class AnthropicAdapter:
    def __init__(self, operation: ConnectionOperation) -> None:
        self._operation = operation

    def __repr__(self) -> str:
        return "AnthropicAdapter(<redacted>)"

    def _body(self, request: TextRequest) -> dict[str, object]:
        self._operation._check()
        messages, tokens, temperature = message_parameters(request)
        system = []
        dialogue: list[dict[str, str]] = []
        for item in messages:
            if item["role"] == "system":
                if dialogue:
                    # Never hoist a later instruction across conversation turns.
                    raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
                system.append({"type": "text", "text": item["content"]})
            else:
                dialogue.append(item)
        if (
            not dialogue
            or dialogue[0]["role"] != "user"
            or dialogue[-1]["role"] != "user"
            or temperature is not None
            and temperature > 1
        ):
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        body: dict[str, object] = {
            "model": self._operation.request.route.model_id,
            "messages": dialogue,
            "max_tokens": tokens,
            "stream": False,
        }
        if system:
            body["system"] = system
        if temperature is not None:
            # Explicit caller setting; an unsupported newer model fails without replay.
            body["temperature"] = temperature
        bounded_json(body)
        return body

    async def _raw(self, body: dict[str, object]) -> dict[str, Any]:
        bounded_json(body)
        async with self._operation.send(body) as response:
            _check_status(response)
            data = bytearray()
            async for chunk in response.aiter_bytes():
                self._operation._check()
                if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise invalid_output()
                data.extend(chunk)
            raw = message(strict_json(bytes(data)))
            self._operation.check_public_metadata(str(raw["model"]))
            # Includes text/tool input and hidden blocks; credential echo is never public.
            self._operation.check_public_metadata(json.dumps(raw["content"], ensure_ascii=False))
            self._operation._check()
            return raw

    def _text(self, raw: dict[str, Any]) -> TextResult:
        finish(raw.get("stop_reason"))
        texts = []
        for block in raw["content"]:
            if not isinstance(block, dict):
                raise invalid_output()
            kind = block.get("type")
            if kind == "text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
            elif kind not in {"thinking", "redacted_thinking"}:
                raise invalid_output()
        text = "".join(texts)
        if not text.strip():
            raise invalid_output()
        return TextResult(text, raw["model"], usage(raw.get("usage")))

    async def generate_text(self, request: TextRequest) -> TextResult:
        return self._text(await self._raw(self._body(request)))

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        caps = self._operation.request.capabilities
        mode = caps.structured_transport
        if (
            caps.structured_output is not True
            or mode not in {"json_schema", "text_json", "tool_schema"}
            or mode == "tool_schema"
            and caps.tool_calling is not True
        ):
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
        if mode == "json_schema":
            body["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        elif mode == "tool_schema":
            body["tools"] = [{"name": TOOL_NAME, "strict": True, "input_schema": schema}]
            body["tool_choice"] = {
                "type": "tool",
                "name": TOOL_NAME,
                "disable_parallel_tool_use": True,
            }
        else:
            system = body.setdefault("system", [])
            assert isinstance(system, list)
            system.append(
                {
                    "type": "text",
                    "text": "Return exactly one JSON object conforming to this schema, "
                    "with no prose: "
                    + json.dumps(schema, ensure_ascii=False),
                }
            )
        raw = await self._raw(body)
        if mode == "tool_schema":
            finish(raw.get("stop_reason"), tool=True)
            blocks = raw["content"]
            if (
                len(blocks) != 1
                or not isinstance(blocks[0], dict)
                or blocks[0].get("type") != "tool_use"
                or blocks[0].get("name") != TOOL_NAME
                or not isinstance(blocks[0].get("id"), str)
                or not blocks[0]["id"]
            ):
                raise invalid_output()
            value = blocks[0].get("input")
            model, counts = raw["model"], usage(raw.get("usage"))
        else:
            result = self._text(raw)
            value, model, counts = strict_json(result.text), result.model_id, result.usage
        if not isinstance(value, dict):
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.STRUCTURED_NOT_OBJECT,
                usage=counts,
            )
        try:
            Draft202012Validator(schema).validate(value)
        except (ValidationError, SchemaError, RecursionError):
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.STRUCTURED_SCHEMA_MISMATCH,
                schema_keyword="other",
                usage=counts,
            ) from None
        return StructuredResult(value, model, counts)

    async def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]:
        if self._operation.request.capabilities.streaming is not True:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        body = self._body(request)
        body["stream"] = True
        async with self._operation.send(body, stream=True) as response:
            _check_status(response)
            started = finished = saw_text = False
            block: tuple[int, str] | None = None
            next_index = 0

            async def chunks() -> AsyncIterator[bytes]:
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise invalid_output()
                    yield chunk

            async for data in _sse_data(chunks()):
                self._operation._check()
                raw = strict_json(data)
                if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
                    raise invalid_output()
                self._operation.check_public_metadata(data)
                kind = raw["type"]
                if kind == "error":
                    error = raw.get("error")
                    if not isinstance(error, dict) or error.get("type") not in ERROR_CODES:
                        raise invalid_output()
                    raise ProviderError(ERROR_CODES[error["type"]])
                if kind == "ping":
                    continue
                if kind == "message_start":
                    if started:
                        raise invalid_output()
                    initial = message(raw.get("message"))
                    if initial["content"] or initial.get("stop_reason") is not None:
                        raise invalid_output()
                    started = True
                elif kind == "content_block_start":
                    content = raw.get("content_block")
                    if (
                        not started
                        or finished
                        or block is not None
                        or type(raw.get("index")) is not int
                        or raw["index"] != next_index
                        or next_index >= 128
                        or not isinstance(content, dict)
                        or content.get("type") not in {"text", "thinking", "redacted_thinking"}
                    ):
                        raise invalid_output()
                    block = (next_index, content["type"])
                    if block[1] == "text":
                        if not isinstance(content.get("text"), str):
                            raise invalid_output()
                        if content["text"]:
                            saw_text = True
                            yield TextDelta(content["text"])
                elif kind == "content_block_delta":
                    delta = raw.get("delta")
                    if (
                        block is None
                        or type(raw.get("index")) is not int
                        or raw["index"] != block[0]
                        or not isinstance(delta, dict)
                    ):
                        raise invalid_output()
                    if block[1] == "text":
                        if delta.get("type") != "text_delta" or not isinstance(
                            delta.get("text"), str
                        ):
                            raise invalid_output()
                        if delta["text"]:
                            saw_text = True
                            yield TextDelta(delta["text"])
                    elif delta.get("type") not in {"thinking_delta", "signature_delta"}:
                        raise invalid_output()
                elif kind == "content_block_stop":
                    if (
                        block is None
                        or type(raw.get("index")) is not int
                        or raw["index"] != block[0]
                    ):
                        raise invalid_output()
                    block = None
                    next_index += 1
                elif kind == "message_delta":
                    delta = raw.get("delta")
                    if (
                        not started
                        or finished
                        or block is not None
                        or not isinstance(delta, dict)
                        or delta.get("stop_sequence") is not None
                    ):
                        raise invalid_output()
                    usage(raw.get("usage"))
                    if delta.get("stop_reason") is not None:
                        finish(delta["stop_reason"])
                        finished = True
                elif kind == "message_stop":
                    if not started or not finished or block is not None or not saw_text:
                        raise invalid_output()
                    return
                # Unknown additive event types are ignored within the bounded stream.
            raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
