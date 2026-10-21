"""Pure bounded JSON and text parameter validation shared by connection adapters."""

import json
import math
from collections.abc import Mapping
from typing import Any

from app.services.provider_gateway import (
    P0_DEFAULT_MAX_OUTPUT_TOKENS,
    OutputFailureReason,
    ProviderError,
    ProviderErrorCode,
    TextRequest,
)

MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def invalid_output() -> ProviderError:
    return ProviderError(ProviderErrorCode.INVALID_OUTPUT)


def strict_json(raw: str | bytes) -> Any:
    def reject(value: str) -> None:
        raise ValueError

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw, parse_constant=reject, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        raise invalid_output() from None


def bounded_json(body: Mapping[str, object]) -> None:
    try:
        encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        if len(encoded) > MAX_REQUEST_BYTES:
            raise ValueError
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE) from None


def validated_model(raw: object) -> str:
    if (
        not isinstance(raw, str)
        or not 1 <= len(raw) <= 160
        or not raw.strip()
        or any(ord(c) < 32 or ord(c) == 127 for c in raw)
    ):
        raise invalid_output()
    return raw


def normal_finish(reason: object) -> None:
    if reason == "length":
        raise ProviderError(
            ProviderErrorCode.INVALID_OUTPUT,
            output_failure_reason=OutputFailureReason.OUTPUT_TOKEN_LIMIT,
        )
    if reason != "stop":
        raise invalid_output()


def message_parameters(
    request: TextRequest, *, allow_images: bool = False
) -> tuple[list[dict[str, str]], int, float | None]:
    if (
        not request.messages
        or not allow_images
        and (request.images or request.image_consent is not None)
        or len(request.messages) > 64
        or any(
            m.role not in {"system", "user", "assistant"} or not isinstance(m.content, str)
            for m in request.messages
        )
        or (
            request.max_output_tokens is not None
            and (
                type(request.max_output_tokens) is not int
                or not 1 <= request.max_output_tokens <= 32768
            )
        )
        or (
            request.temperature is not None
            and (
                isinstance(request.temperature, bool)
                or not isinstance(request.temperature, (int, float))
                or not math.isfinite(request.temperature)
                or not 0 <= request.temperature <= 2
            )
        )
    ):
        raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
    return (
        [{"role": m.role, "content": m.content} for m in request.messages],
        request.max_output_tokens or P0_DEFAULT_MAX_OUTPUT_TOKENS,
        request.temperature,
    )
