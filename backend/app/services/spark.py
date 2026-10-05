"""Optional native Spark HTTP text/SSE protocol, never signed-URL WebSocket auth."""

from collections.abc import AsyncIterator
from typing import Any

from app.services.deepseek_responses import _check_status, _sse_data
from app.services.provider_connection_dispatch import ConnectionOperation
from app.services.provider_gateway import (
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

ERROR_CODES = {
    10007: ProviderErrorCode.RATE_LIMITED,
    11201: ProviderErrorCode.RATE_LIMITED,
    11202: ProviderErrorCode.RATE_LIMITED,
    11203: ProviderErrorCode.RATE_LIMITED,
    11200: ProviderErrorCode.AUTHENTICATION_FAILED,
    10907: ProviderErrorCode.CAPABILITY_UNAVAILABLE,
    10013: ProviderErrorCode.INVALID_OUTPUT,
    10014: ProviderErrorCode.INVALID_OUTPUT,
    10019: ProviderErrorCode.INVALID_OUTPUT,
}


def usage(raw: object) -> TokenUsage | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise invalid_output()
    for name in ("prompt_tokens", "completion_tokens", "total_tokens", "search_prompt_tokens"):
        if raw.get(name) is not None and (type(raw[name]) is not int or raw[name] < 0):
            raise invalid_output()
    if raw.get("search_prompt_tokens", 0):
        # A response that says search happened violates this adapter's text-only authority.
        raise invalid_output()
    if raw.get("prompt_tokens") is None and raw.get("completion_tokens") is None:
        return None
    return TokenUsage(raw.get("prompt_tokens"), raw.get("completion_tokens"))


def envelope(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise invalid_output()
    if "code" in raw:
        if type(raw["code"]) is not int:
            raise invalid_output()
        if raw["code"] != 0:
            raise ProviderError(
                ERROR_CODES.get(raw["code"], ProviderErrorCode.CAPABILITY_UNAVAILABLE)
            )
    if "error" in raw:
        # HTTP status takes precedence; a malformed 200 error is never success.
        raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
    if "model" in raw:
        validated_model(raw["model"])
    usage(raw.get("usage"))
    if raw.get("web_search") or raw.get("search_results") or raw.get("search_prompt"):
        raise invalid_output()
    return raw


def choice(raw: dict[str, Any]) -> dict[str, Any]:
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise invalid_output()
    value = choices[0]
    if not isinstance(value, dict) or type(value.get("index")) is not int or value["index"] != 0:
        raise invalid_output()
    if value.get("finish_reason") is not None:
        normal_finish(value["finish_reason"])
    return value


def content(raw: object, *, streaming: bool) -> str:
    if (
        not isinstance(raw, dict)
        or raw.get("role", "assistant" if streaming else None) != "assistant"
        or any(
            raw.get(name)
            for name in ("tool_calls", "function_call", "refusal", "web_search", "search_results")
        )
        or raw.get("type") not in (None, "text")
    ):
        raise invalid_output()
    hidden = raw.get("security_suggest")
    if hidden is not None:
        if not isinstance(hidden, dict) or hidden.get("action") != "HIDE_CONTINUE":
            raise invalid_output()
        # The vendor's advice can only hide reasoning, never expose flagged answer text.
        if raw.get("content"):
            raise invalid_output()
    if raw.get("reasoning_content") is not None and not isinstance(raw["reasoning_content"], str):
        raise invalid_output()
    text = raw.get("content")
    if text is None and streaming:
        return ""
    if not isinstance(text, str) or not streaming and not text.strip():
        raise invalid_output()
    return text


class SparkAdapter:
    def __init__(self, operation: ConnectionOperation) -> None:
        self._operation = operation

    def __repr__(self) -> str:
        return "SparkAdapter(<redacted>)"

    def _body(self, request: TextRequest) -> dict[str, object]:
        self._operation._check()
        messages, tokens, temperature = message_parameters(request)
        body: dict[str, object] = {
            "model": self._operation.request.route.model_id,
            "messages": messages,
            "max_tokens": tokens,
            "stream": False,
            "tools": [{"type": "web_search", "web_search": {"enable": False}}],
            "tool_choice": "none",
        }
        if temperature is not None:
            body["temperature"] = temperature
        bounded_json(body)
        return body

    def _check_values(self, raw: object) -> None:
        pending = [raw]
        while pending:
            item = pending.pop()
            if isinstance(item, str):
                self._operation.check_public_metadata(item)
            elif isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)

    async def generate_text(self, request: TextRequest) -> TextResult:
        body = self._body(request)
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
            raw = envelope(raw)
            selected = choice(raw)
            text = content(selected.get("message"), streaming=False)
            self._operation._check()
            # Native docs omit model and finish_reason. This identifies the selected
            # route, never a claim that the upstream independently verified its model.
            return TextResult(text, self._operation.request.route.model_id, usage(raw.get("usage")))

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        # T017 only exposes the audited text/stream contract, no speculative schema mode.
        self._operation._check()
        raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)

    async def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]:
        if self._operation.request.capabilities.streaming is not True:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        body = self._body(request)
        body["stream"] = True
        async with self._operation.send(body, stream=True) as response:
            _check_status(response)
            saw_visible = finished = terminal = False
            model: str | None = None

            async def chunks() -> AsyncIterator[bytes]:
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise invalid_output()
                    yield chunk

            async for data in _sse_data(chunks()):
                self._operation._check()
                if terminal:
                    raise invalid_output()
                if data == "[DONE]":
                    if not saw_visible:
                        raise invalid_output()
                    terminal = True
                    continue
                raw = strict_json(data)
                self._check_values(raw)
                raw = envelope(raw)
                if raw.get("model") is not None:
                    if model is not None and model != raw["model"]:
                        raise invalid_output()
                    model = raw["model"]
                if raw.get("choices") == [] and raw.get("usage") is not None:
                    continue
                selected = choice(raw)
                text = content(selected.get("delta"), streaming=True)
                if finished:
                    if text or selected.get("finish_reason") is not None:
                        raise invalid_output()
                if selected.get("finish_reason") is not None:
                    finished = True
                if text:
                    saw_visible = saw_visible or bool(text.strip())
                    yield TextDelta(text)
            if not terminal:
                raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
