"""Single server-configured OpenAI-compatible Chat Completions adapter."""

import ipaddress
import json
import math
from collections.abc import AsyncIterator, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError, ValidationError  # type: ignore[import-untyped]

from app.core.config import ProviderSettings
from app.core.provider_target import ApprovedTarget, ProviderTargetGuard, TargetValidationError
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

_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_SSE_FRAME_BYTES = 1024 * 1024
_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)


def _retry_after_seconds(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        try:
            date = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        seconds = max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _check_status(response: httpx.Response) -> None:
    status = response.status_code
    if status in {401, 403}:
        raise ProviderError(ProviderErrorCode.AUTHENTICATION_FAILED)
    if response.is_redirect:
        raise ProviderError(ProviderErrorCode.INVALID_TARGET)
    if status == 429:
        retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
        raise ProviderError(ProviderErrorCode.RATE_LIMITED, retry_after_seconds=retry_after)
    if status in {408, 504}:
        raise ProviderError(ProviderErrorCode.TIMEOUT)
    if 400 <= status < 500 or status == 501:
        raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
    if not response.is_success:
        raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)


def _wire_target(target: ApprovedTarget) -> tuple[str, str]:
    parsed = urlsplit(target.url)
    address = ipaddress.ip_address(target.connect_ip)
    ip_host = f"[{address}]" if address.version == 6 else str(address)
    endpoint = urlunsplit(
        (
            parsed.scheme,
            f"{ip_host}:{target.port}",
            parsed.path.rstrip("/") + "/chat/completions",
            "",
            "",
        )
    )
    original = ipaddress.ip_address(target.hostname) if ":" in target.hostname else None
    host = f"[{original}]" if original is not None else target.hostname
    default_port = 443 if parsed.scheme == "https" else 80
    host_header = host if target.port == default_port else f"{host}:{target.port}"
    return endpoint, host_header


def _request_body(request: TextRequest) -> dict[str, object]:
    body: dict[str, object] = {
        "messages": [{"role": item.role, "content": item.content} for item in request.messages],
        "stream": False,
    }
    if request.max_output_tokens is not None:
        body["max_completion_tokens"] = request.max_output_tokens
    if request.temperature is not None:
        body["temperature"] = request.temperature
    return body


def _reject_external_schema_refs(value: object) -> None:
    """Do not let local result validation fetch arbitrary remote schemas."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"$id", "$dynamicRef", "$recursiveRef"} or (
                key == "$ref" and (not isinstance(child, str) or not child.startswith("#/"))
            ):
                raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
            _reject_external_schema_refs(child)
    elif isinstance(value, list):
        for child in value:
            _reject_external_schema_refs(child)


def _usage(payload: Mapping[str, object]) -> TokenUsage | None:
    raw = payload.get("usage")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)

    def count(name: str) -> int | None:
        value = raw.get(name)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
        return int(value)

    return TokenUsage(input_tokens=count("prompt_tokens"), output_tokens=count("completion_tokens"))


def _result(payload: object) -> TextResult:
    if not isinstance(payload, dict):
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
    model = payload.get("model")
    choices = payload.get("choices")
    if not isinstance(model, str) or not model or not isinstance(choices, list) or not choices:
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
    return TextResult(text=content, model_id=model, usage=_usage(payload))


async def _sse_data(chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
    """Assemble UTF-8 SSE data frames across arbitrary network byte boundaries."""
    line = bytearray()
    data_lines: list[str] = []
    frame_size = 0
    after_cr = False
    async for chunk in chunks:
        for byte in chunk:
            if byte == 10 and after_cr:
                after_cr = False
                continue
            if byte in (10, 13):
                after_cr = byte == 13
                try:
                    text = line.decode("utf-8")
                except UnicodeError:
                    raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None
                line.clear()
                if not text:
                    if data_lines:
                        yield "\n".join(data_lines)
                        data_lines.clear()
                        frame_size = 0
                elif not text.startswith(":"):
                    field, separator, value = text.partition(":")
                    if field == "data":
                        data_lines.append(
                            value[1:] if separator and value.startswith(" ") else value
                        )
                        frame_size += len(text.encode("utf-8"))
                        if frame_size > _MAX_SSE_FRAME_BYTES:
                            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
                continue
            after_cr = False
            line.append(byte)
            if len(line) + frame_size > _MAX_SSE_FRAME_BYTES:
                raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
    if line or data_lines:
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)


def _stream_chunk(data: str) -> tuple[str | None, bool]:
    try:
        payload = json.loads(data)
    except (UnicodeError, ValueError):
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None
    if not isinstance(payload, dict) or not isinstance(payload.get("choices"), list):
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
    choices = payload["choices"]
    if not choices:  # optional terminal usage-only chunk
        return None, False
    choice = choices[0]
    if not isinstance(choice, dict) or not isinstance(choice.get("delta"), dict):
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
    content = choice["delta"].get("content")
    reason = choice.get("finish_reason")
    if (content is not None and not isinstance(content, str)) or reason not in (None, "stop"):
        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
    return content, reason == "stop"


class OpenAICompatibleAdapter:
    """P0 adapter; one attempt, pinned IP, no proxy or automatic redirects."""

    def __init__(
        self,
        settings: ProviderSettings,
        guard: ProviderTargetGuard,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._guard = guard
        self._transport = transport

    async def _completion(self, body: dict[str, object]) -> TextResult:
        try:
            target = self._guard.approve_base()
        except TargetValidationError:
            raise ProviderError(ProviderErrorCode.INVALID_TARGET) from None
        url, host_header = _wire_target(target)
        body["model"] = self._settings.model
        headers = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Host": host_header,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
                timeout=_TIMEOUT,
            ) as client:
                request = client.build_request("POST", url, headers=headers, json=body)
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
        except ProviderError:
            raise
        except httpx.TimeoutException:
            raise ProviderError(ProviderErrorCode.TIMEOUT) from None
        except httpx.RequestError:
            raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE) from None
        try:
            payload: Any = json.loads(b"".join(chunks))
        except (UnicodeError, ValueError):
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None
        return _result(payload)

    async def generate_text(self, request: TextRequest) -> TextResult:
        return await self._completion(_request_body(request))

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        try:
            schema = dict(request.json_schema)
            _reject_external_schema_refs(schema)
            Draft202012Validator.check_schema(schema)
        except ProviderError:
            raise
        except (TypeError, ValueError, SchemaError):
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None
        body = _request_body(request.prompt)
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "edumind_result", "schema": schema, "strict": True},
        }
        result = await self._completion(body)
        try:
            value = json.loads(result.text)
            if not isinstance(value, dict):
                raise ValueError
            Draft202012Validator(schema).validate(value)
        except (UnicodeError, ValueError, ValidationError, SchemaError):
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None
        return StructuredResult(value=value, model_id=result.model_id, usage=result.usage)

    async def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]:
        try:
            target = self._guard.approve_base()
        except TargetValidationError:
            raise ProviderError(ProviderErrorCode.INVALID_TARGET) from None
        url, host_header = _wire_target(target)
        body = _request_body(request)
        body["model"] = self._settings.model
        body["stream"] = True
        headers = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Host": host_header,
            "Accept": "text/event-stream",
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
                timeout=_TIMEOUT,
            ) as client:
                wire_request = client.build_request("POST", url, headers=headers, json=body)
                wire_request.extensions["sni_hostname"] = target.hostname
                response = await client.send(wire_request, stream=True, follow_redirects=False)
                try:
                    _check_status(response)
                    finished = False
                    done = False
                    async for data in _sse_data(response.aiter_bytes()):
                        if data == "[DONE]":
                            done = True
                            break
                        content, stopped = _stream_chunk(data)
                        if finished and content:
                            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
                        if content:
                            yield TextDelta(text=content)
                        finished = finished or stopped
                    if not done:
                        raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
                    if not finished:
                        raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
                finally:
                    await response.aclose()
        except ProviderError:
            raise
        except httpx.TimeoutException:
            raise ProviderError(ProviderErrorCode.TIMEOUT) from None
        except httpx.RequestError:
            raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE) from None
