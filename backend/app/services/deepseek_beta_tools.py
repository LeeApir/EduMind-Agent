"""Explicit same-origin Beta structured transport; arguments are data, not tools."""

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import ProviderSettings
from app.core.provider_target import ProviderTargetGuard
from app.services.deepseek_responses import (
    _MAX_RESPONSE_BYTES,
    _TIMEOUT,
    DeepSeekResponsesAdapter,
    _check_status,
)
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


def typed_constants(value: Any) -> Any:
    """Project typed constants without weakening the original local schema."""
    if isinstance(value, list):
        return [typed_constants(child) for child in value]
    if not isinstance(value, dict):
        return value
    projected = {key: typed_constants(child) for key, child in value.items()}
    if "const" in projected:
        constant = projected.pop("const")
        if isinstance(constant, bool):
            kind = "boolean"
        elif isinstance(constant, str):
            kind = "string"
        else:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        # Existing incompatible constraints must fail closed, not be overwritten.
        if "type" in projected and projected["type"] != kind:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        if "enum" in projected and constant not in projected["enum"]:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        projected.update(type=kind, enum=[constant])
    elif "enum" in projected and "type" not in projected:
        values = projected["enum"]
        if values and all(isinstance(item, str) for item in values):
            projected["type"] = "string"
        elif values and all(isinstance(item, bool) for item in values):
            projected["type"] = "boolean"
        else:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
    return projected


def _chat_usage(payload: Any) -> TokenUsage | None:
    record = payload.get("usage") if isinstance(payload, dict) else None
    if record is None:
        return None
    try:
        counts = (record["prompt_tokens"], record["completion_tokens"])
        if any(
            isinstance(count, bool) or not isinstance(count, int) or count < 0 for count in counts
        ):
            raise ValueError
        return TokenUsage(input_tokens=counts[0], output_tokens=counts[1])
    except (KeyError, TypeError, ValueError):
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None


def tool_arguments(payload: Any) -> TextResult:
    try:
        choices = payload["choices"]
        if len(choices) != 1:
            raise ValueError
        finish = choices[0]["finish_reason"]
        if finish != "tool_calls":
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=(
                    OutputFailureReason.OUTPUT_TOKEN_LIMIT
                    if finish == "length"
                    else OutputFailureReason.RESPONSE_INCOMPLETE
                ),
                usage=_chat_usage(payload),
            )
        message = choices[0]["message"]
        calls = message["tool_calls"]
        if message["role"] != "assistant" or len(calls) != 1:
            raise ValueError
        call = calls[0]
        function = call["function"]
        if call["type"] != "function" or function["name"] != "edumind_result":
            raise ValueError
        arguments, model = function["arguments"], payload["model"]
        if not isinstance(arguments, str) or not isinstance(model, str) or not model:
            raise ValueError
        return TextResult(arguments, model, _chat_usage(payload))
    except (KeyError, TypeError, ValueError, IndexError):
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None


class _BetaStructuredTransport(DeepSeekResponsesAdapter):
    async def _response(self, body: dict[str, Any]) -> TextResult:
        target, url, headers = self._target()
        url = url.removesuffix("/responses") + "/chat/completions"
        schema = typed_constants(body["text"]["format"]["schema"])
        chat = {
            "model": self._settings.model,
            "messages": body["input"],
            "stream": False,
            "thinking": {"type": "disabled"},
            "max_tokens": body["max_output_tokens"],
            "temperature": body.get("temperature", 0.0),
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "edumind_result",
                        "strict": True,
                        "parameters": schema,
                        "description": "Return structured data only. No function will be executed.",
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "edumind_result"}},
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, trust_env=False, follow_redirects=False, timeout=_TIMEOUT
            ) as client:
                request = client.build_request("POST", url, headers=headers, json=chat)
                request.extensions["sni_hostname"] = target.hostname
                response = await client.send(request, stream=True, follow_redirects=False)
                try:
                    _check_status(response)
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > _MAX_RESPONSE_BYTES:
                            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
                        chunks.append(chunk)
                finally:
                    await response.aclose()
        except httpx.TimeoutException:
            raise ProviderError(ProviderErrorCode.TIMEOUT) from None
        except httpx.RequestError:
            raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE) from None
        try:
            payload = json.loads(b"".join(chunks))
        except (UnicodeError, ValueError):
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None
        return tool_arguments(payload)


class DeepSeekBetaToolsAdapter:
    """Keep ordinary Responses calls unchanged; opt in to Beta only for JSON."""

    def __init__(
        self,
        settings: ProviderSettings,
        guard: ProviderTargetGuard,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(settings.base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.deepseek.com"
            or parsed.port not in (None, 443)
        ):
            raise ProviderError(ProviderErrorCode.INVALID_TARGET)
        beta_settings = replace(settings, base_url="https://api.deepseek.com/beta")
        beta_guard = ProviderTargetGuard(
            beta_settings.base_url,
            guard.policy,
            resolver=guard.resolver,
        )
        self._ordinary = DeepSeekResponsesAdapter(settings, guard, transport=transport)
        self._structured = _BetaStructuredTransport(beta_settings, beta_guard, transport=transport)

    async def generate_text(self, request: TextRequest) -> TextResult:
        return await self._ordinary.generate_text(request)

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        return await self._structured.generate_structured(request)

    def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]:
        return self._ordinary.stream_text(request)
