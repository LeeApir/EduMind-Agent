"""Bounded Chat Completions adapter; no SDK, probing, fallback or credential cache."""

import json
from collections.abc import AsyncIterator

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError, ValidationError  # type: ignore[import-untyped]

from app.services.deepseek_responses import (
    _check_status,
    _reject_external_schema_refs,
    _sse_data,
)
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


def _usage(raw: object) -> TokenUsage | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise invalid_output()
    for key in ("prompt_tokens", "completion_tokens"):
        count = raw.get(key)
        if count is not None and (type(count) is not int or count < 0):
            raise invalid_output()
    return TokenUsage(raw.get("prompt_tokens"), raw.get("completion_tokens"))


class OpenAICompatibleAdapter:
    def __init__(self, operation: ConnectionOperation) -> None:
        self._operation = operation

    def __repr__(self) -> str:
        return "OpenAICompatibleAdapter(<redacted>)"

    def _body(self, request: TextRequest) -> dict[str, object]:
        self._operation._check()
        messages, tokens, temperature = message_parameters(request)
        body: dict[str, object] = {
            "model": self._operation.request.route.model_id,
            "messages": messages,
            "max_tokens": tokens,
            "stream": False,
        }
        if temperature is not None:
            body["temperature"] = temperature
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
            raw = strict_json(b"".join(chunks))
            if not isinstance(raw, dict):
                raise invalid_output()
            model = validated_model(raw.get("model"))
            usage = _usage(raw.get("usage"))
            choices = raw.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise invalid_output()
            choice = choices[0]
            if (
                not isinstance(choice, dict)
                or choice.get("index") != 0
                or type(choice.get("index")) is not int
            ):
                raise invalid_output()
            normal_finish(choice.get("finish_reason"))
            message = choice.get("message")
            if (
                not isinstance(message, dict)
                or message.get("role") != "assistant"
                or message.get("refusal")
                or message.get("tool_calls")
                or message.get("function_call")
            ):
                raise invalid_output()
            text = message.get("content")
            if not isinstance(text, str) or not text.strip():
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
        if mode == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "edumind_result",
                    "strict": True,
                    "schema": schema,
                },
            }
        else:
            # Explicitly selected weaker wire mode; local schema validation is unchanged.
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
                body["response_format"] = {"type": "json_object"}
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
        except (ValidationError, SchemaError):
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
            finished = False

            async def bounded_chunks() -> AsyncIterator[bytes]:
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise invalid_output()
                    yield chunk

            async for data in _sse_data(bounded_chunks()):
                self._operation._check()
                if data == "[DONE]":
                    if not finished or not saw_text:
                        raise invalid_output()
                    return
                raw = strict_json(data)
                if not isinstance(raw, dict):
                    raise invalid_output()
                if raw.get("error"):
                    raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
                validated_model(raw.get("model"))
                choices = raw.get("choices")
                if choices == [] and finished and raw.get("usage") is not None:
                    _usage(raw["usage"])
                    continue
                if not isinstance(choices, list) or len(choices) != 1:
                    raise invalid_output()
                choice = choices[0]
                if (
                    not isinstance(choice, dict)
                    or type(choice.get("index")) is not int
                    or choice["index"] != 0
                    or finished
                ):
                    raise invalid_output()
                delta = choice.get("delta")
                if (
                    not isinstance(delta, dict)
                    or delta.get("tool_calls")
                    or delta.get("function_call")
                    or delta.get("refusal")
                    or delta.get("role", "assistant") != "assistant"
                ):
                    raise invalid_output()
                text = delta.get("content")
                if text is not None and not isinstance(text, str):
                    raise invalid_output()
                if choice.get("finish_reason") is not None:
                    normal_finish(choice["finish_reason"])
                    finished = True
                if text:
                    saw_text = True
                    yield TextDelta(text)
            # Unterminated stream is a recoverable safe error, never auto-retried.
            raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
