"""Native bounded Gemini GenerateContent protocol, with no implicit uploads/tools."""

import base64
import json
import re
from collections.abc import AsyncIterator, Mapping
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
from app.services.provider_inline_images import check_image_consent
from app.services.provider_protocol import (
    MAX_RESPONSE_BYTES,
    bounded_json,
    invalid_output,
    message_parameters,
    strict_json,
    validated_model,
)

ERROR_CODES = {
    "UNAUTHENTICATED": ProviderErrorCode.AUTHENTICATION_FAILED,
    "PERMISSION_DENIED": ProviderErrorCode.AUTHENTICATION_FAILED,
    "RESOURCE_EXHAUSTED": ProviderErrorCode.RATE_LIMITED,
    "DEADLINE_EXCEEDED": ProviderErrorCode.TIMEOUT,
    "UNAVAILABLE": ProviderErrorCode.TEMPORARILY_UNAVAILABLE,
    "INTERNAL": ProviderErrorCode.TEMPORARILY_UNAVAILABLE,
    "INVALID_ARGUMENT": ProviderErrorCode.CAPABILITY_UNAVAILABLE,
    "NOT_FOUND": ProviderErrorCode.CAPABILITY_UNAVAILABLE,
    "FAILED_PRECONDITION": ProviderErrorCode.CAPABILITY_UNAVAILABLE,
}


def model_resource(value: str) -> str:
    """No user-provided slash, query or encoded path may select a different endpoint."""
    name = value.removeprefix("models/")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,152}", name):
        raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
    return "models/" + name


def usage(raw: object) -> TokenUsage | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise invalid_output()
    names = (
        "promptTokenCount",
        "candidatesTokenCount",
        "thoughtsTokenCount",
        "totalTokenCount",
        "cachedContentTokenCount",
        "toolUsePromptTokenCount",
    )
    if any(raw.get(n) is not None and (type(raw[n]) is not int or raw[n] < 0) for n in names):
        raise invalid_output()
    output = raw.get("candidatesTokenCount")
    if output is not None and raw.get("thoughtsTokenCount") is not None:
        output += raw["thoughtsTokenCount"]
    if raw.get("promptTokenCount") is None and output is None:
        return None
    return TokenUsage(raw.get("promptTokenCount"), output)


def finish(reason: object) -> None:
    if reason == "MAX_TOKENS":
        raise ProviderError(
            ProviderErrorCode.INVALID_OUTPUT,
            output_failure_reason=OutputFailureReason.OUTPUT_TOKEN_LIMIT,
        )
    if reason != "STOP":
        raise invalid_output()


def unpack(
    raw: object, *, streaming: bool = False
) -> tuple[str, str | None, object, TokenUsage | None]:
    if not isinstance(raw, dict):
        raise invalid_output()
    if "error" in raw:
        error = raw["error"]
        if not isinstance(error, dict) or error.get("status") not in ERROR_CODES:
            raise invalid_output()
        raise ProviderError(ERROR_CODES[error["status"]])
    model = raw.get("modelVersion")
    if model is not None:
        validated_model(model)
    if not streaming and model is None:
        raise invalid_output()
    feedback = raw.get("promptFeedback")
    if feedback is not None and (not isinstance(feedback, dict) or feedback.get("blockReason")):
        raise invalid_output()
    counts = usage(raw.get("usageMetadata"))
    candidates = raw.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) != 1:
        if streaming and candidates == [] and counts is not None:
            return "", model, None, counts
        raise invalid_output()
    candidate = candidates[0]
    if not isinstance(candidate, dict) or (
        "index" in candidate and (type(candidate["index"]) is not int or candidate["index"] != 0)
    ):
        raise invalid_output()
    content = candidate.get("content")
    if content is None and streaming and candidate.get("finishReason") is not None:
        return "", model, candidate["finishReason"], counts
    if not isinstance(content, dict) or content.get("role") != "model":
        raise invalid_output()
    parts = content.get("parts")
    if not isinstance(parts, list) or len(parts) > 128:
        raise invalid_output()
    visible = []
    for part in parts:
        if (
            not isinstance(part, dict)
            or set(part) - {"text", "thought", "thoughtSignature"}
            or "thought" in part
            and type(part["thought"]) is not bool
            or "thoughtSignature" in part
            and not isinstance(part["thoughtSignature"], str)
            or "text" in part
            and not isinstance(part["text"], str)
            or "text" not in part
            and "thoughtSignature" not in part
        ):
            # Function calls, executable code and binary outputs are never interpreted as text.
            raise invalid_output()
        if part.get("thought") is not True:
            visible.append(part.get("text", ""))
    return "".join(visible), model, candidate.get("finishReason"), counts


class GeminiAdapter:
    supports_inline_images = True

    def __init__(self, operation: ConnectionOperation) -> None:
        self._operation = operation
        self._media_used = False

    def __repr__(self) -> str:
        return "GeminiAdapter(<redacted>)"

    def _check_values(self, value: object) -> None:
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, str):
                self._operation.check_public_metadata(item)
            elif isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)

    def _body(
        self, request: TextRequest, schema: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        self._operation._check()
        model_resource(self._operation.request.route.model_id)
        messages, tokens, temperature = message_parameters(request, allow_images=True)
        system: list[dict[str, object]] = []
        dialogue: list[dict[str, Any]] = []
        for item in messages:
            if item["role"] == "system":
                if dialogue:
                    raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
                system.append({"text": item["content"]})
            else:
                dialogue.append(
                    {
                        "role": "model" if item["role"] == "assistant" else "user",
                        "parts": [{"text": item["content"]}],
                    }
                )
        if not dialogue or dialogue[0]["role"] != "user" or dialogue[-1]["role"] != "user":
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        if request.images:
            if self._media_used:
                raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
            check_image_consent(self._operation, request, schema)
            dialogue[-1]["parts"].extend(
                {
                    "inlineData": {
                        "mimeType": image.mime_type,
                        "data": base64.b64encode(image.data).decode("ascii"),
                    }
                }
                for image in request.images
            )
        elif request.image_consent is not None:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        config: dict[str, object] = {
            "maxOutputTokens": tokens,
            "candidateCount": 1,
            "responseModalities": ["TEXT"],
        }
        if temperature is not None:
            config["temperature"] = temperature
        body: dict[str, object] = {"contents": dialogue, "generationConfig": config}
        if system:
            body["systemInstruction"] = {"parts": system}
        bounded_json(body)
        return body

    def _consume_images(self, request: TextRequest) -> None:
        if request.images:
            self._media_used = True

    async def _raw(self, body: dict[str, object]) -> object:
        bounded_json(body)
        async with self._operation.send(body) as response:
            _check_status(response)
            data = bytearray()
            async for chunk in response.aiter_bytes():
                self._operation._check()
                if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise invalid_output()
                data.extend(chunk)
            raw = strict_json(bytes(data))
            self._check_values(raw)
            text, _, _, _ = unpack(raw)
            # A structured JSON string can escape a Key a second time. Validate
            # decoded values before leaving the context that still has the header.
            try:
                value = strict_json(text)
            except ProviderError:
                pass
            else:
                self._check_values(value)
            self._operation._check()
            return raw

    def _text(self, raw: object) -> TextResult:
        text, model, reason, counts = unpack(raw)
        finish(reason)
        if not text.strip() or model is None:
            raise invalid_output()
        return TextResult(text, model, counts)

    async def generate_text(self, request: TextRequest) -> TextResult:
        body = self._body(request)
        self._consume_images(request)
        return self._text(await self._raw(body))

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        caps = self._operation.request.capabilities
        mode = caps.structured_transport
        if caps.structured_output is not True or mode not in {"json_schema", "text_json"}:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        try:
            schema = dict(request.json_schema)
            bounded_json(schema)
            # Snapshot nested schema values before any async budget/store work.
            schema = strict_json(json.dumps(schema, ensure_ascii=False, allow_nan=False))
            _reject_external_schema_refs(schema)
            Draft202012Validator.check_schema(schema)
        except (TypeError, ValueError, RecursionError, SchemaError):
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.REQUEST_SCHEMA_INVALID,
            ) from None
        body = self._body(request.prompt, schema)
        if mode == "json_schema":
            config = body["generationConfig"]
            assert isinstance(config, dict)
            config["responseFormat"] = {"text": {"mimeType": "application/json", "schema": schema}}
        else:
            system = body.setdefault("systemInstruction", {"parts": []})
            assert isinstance(system, dict)
            system["parts"].append(
                {
                    "text": "Return exactly one JSON object conforming to this schema, "
                    "with no prose: " + json.dumps(schema, ensure_ascii=False)
                }
            )
        bounded_json(body)
        self._consume_images(request.prompt)
        result = self._text(await self._raw(body))
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
        self._consume_images(request)
        async with self._operation.send(body, stream=True) as response:
            _check_status(response)
            finished = False
            saw_visible = False
            version: str | None = None

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
                self._check_values(raw)
                text, model, reason, _ = unpack(raw, streaming=True)
                if model is not None:
                    if version is not None and version != model:
                        raise invalid_output()
                    version = model
                if version is None or finished and (text or reason is not None):
                    raise invalid_output()
                if reason is not None:
                    finish(reason)
                    finished = True
                if text:
                    saw_visible = saw_visible or bool(text.strip())
                    yield TextDelta(text)
            if not finished:
                raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
            if not saw_visible:
                raise invalid_output()
