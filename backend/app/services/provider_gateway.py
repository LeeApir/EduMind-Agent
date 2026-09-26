"""Provider-neutral generation contract for P0 business services."""

import asyncio
import math
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable, Literal, Protocol, TypeVar

MessageRole = Literal["system", "user", "assistant"]
_Result = TypeVar("_Result")


class TaskProfile(StrEnum):
    """Internal task tiers; P0 may map every tier to the same server model."""

    FAST = "fast"
    DEFAULT = "default"
    QUALITY = "quality"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class TextRequest:
    messages: tuple[ChatMessage, ...]
    task_profile: TaskProfile = TaskProfile.DEFAULT
    max_output_tokens: int | None = None
    temperature: float | None = None


@dataclass(frozen=True, slots=True)
class StructuredRequest:
    """Request JSON data conforming to json_schema, not vendor-specific modes."""

    prompt: TextRequest
    json_schema: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class TextResult:
    text: str
    model_id: str
    usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class StructuredResult:
    value: Mapping[str, object]
    model_id: str
    usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class TextDelta:
    """A provider-neutral piece of text, not an application SSE event."""

    text: str


class ProviderErrorCode(StrEnum):
    CONFIGURATION_MISSING = "CONFIGURATION_MISSING"
    INVALID_TARGET = "INVALID_TARGET"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    INVALID_OUTPUT = "INVALID_OUTPUT"


_SAFE_MESSAGES: dict[ProviderErrorCode, str] = {
    ProviderErrorCode.CONFIGURATION_MISSING: "Provider configuration is unavailable.",
    ProviderErrorCode.INVALID_TARGET: "Provider target is not permitted.",
    ProviderErrorCode.AUTHENTICATION_FAILED: "Provider authentication failed.",
    ProviderErrorCode.CAPABILITY_UNAVAILABLE: "Requested provider capability is unavailable.",
    ProviderErrorCode.RATE_LIMITED: "Provider rate limit reached.",
    ProviderErrorCode.TEMPORARILY_UNAVAILABLE: "Provider is temporarily unavailable.",
    ProviderErrorCode.TIMEOUT: "Provider request timed out.",
    ProviderErrorCode.INVALID_OUTPUT: "Provider output did not satisfy the requested format.",
}
_RETRYABLE_CODES = frozenset(
    {
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.TEMPORARILY_UNAVAILABLE,
        ProviderErrorCode.TIMEOUT,
    }
)


class OutputFailureReason(StrEnum):
    """Content-free diagnostics; never carry vendor text or schema values."""

    RESPONSE_INCOMPLETE = "RESPONSE_INCOMPLETE"
    OUTPUT_TOKEN_LIMIT = "OUTPUT_TOKEN_LIMIT"
    RESPONSE_JSON_INVALID = "RESPONSE_JSON_INVALID"
    STRUCTURED_JSON_INVALID = "STRUCTURED_JSON_INVALID"
    STRUCTURED_NOT_OBJECT = "STRUCTURED_NOT_OBJECT"
    STRUCTURED_SCHEMA_MISMATCH = "STRUCTURED_SCHEMA_MISMATCH"
    REQUEST_SCHEMA_INVALID = "REQUEST_SCHEMA_INVALID"


class JsonSyntaxReason(StrEnum):
    """Fixed syntax categories; no text, positions, paths, or generated values."""

    INVALID_ESCAPE = "INVALID_ESCAPE"
    UNESCAPED_CONTROL_CHARACTER = "UNESCAPED_CONTROL_CHARACTER"
    UNTERMINATED_STRING = "UNTERMINATED_STRING"
    EXPECTED_DELIMITER = "EXPECTED_DELIMITER"
    EXPECTED_PROPERTY_NAME = "EXPECTED_PROPERTY_NAME"
    EXPECTED_VALUE = "EXPECTED_VALUE"
    EXTRA_DATA = "EXTRA_DATA"
    OTHER = "OTHER"


class ProviderError(RuntimeError):
    """Stable safe error; adapters must never include raw vendor messages or keys."""

    def __init__(
        self, code: ProviderErrorCode, *, retry_after_seconds: float | None = None,
        output_failure_reason: OutputFailureReason | None = None,
        schema_keyword: str | None = None,
        json_syntax_reason: JsonSyntaxReason | None = None,
    ) -> None:
        super().__init__(_SAFE_MESSAGES[code])
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        if output_failure_reason is not None and (
            code is not ProviderErrorCode.INVALID_OUTPUT
            or not isinstance(output_failure_reason, OutputFailureReason)
        ):
            raise ValueError("Invalid output diagnostic.")
        self.output_failure_reason = output_failure_reason
        if schema_keyword is not None and (
            output_failure_reason is not OutputFailureReason.STRUCTURED_SCHEMA_MISMATCH
            or schema_keyword not in {
                "type", "required", "additionalProperties", "const", "enum", "minLength",
                "maxLength", "minItems", "maxItems", "uniqueItems", "pattern", "other",
            }
        ):
            raise ValueError("Invalid schema diagnostic.")
        self.schema_keyword = schema_keyword
        if json_syntax_reason is not None and (
            output_failure_reason is not OutputFailureReason.STRUCTURED_JSON_INVALID
            or not isinstance(json_syntax_reason, JsonSyntaxReason)
        ):
            raise ValueError("Invalid JSON syntax diagnostic.")
        self.json_syntax_reason = json_syntax_reason

    @property
    def retryable(self) -> bool:
        return self.code in _RETRYABLE_CODES


class ProviderAdapter(Protocol):
    """Single-attempt adapter boundary implemented by the configured P0 provider."""

    async def generate_text(self, request: TextRequest) -> TextResult: ...

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult: ...

    def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]: ...


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded retry budget; explicit caller safety opt-in is still required."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if (
            not 1 <= self.max_attempts <= 3
            or not math.isfinite(self.base_delay_seconds)
            or not math.isfinite(self.max_delay_seconds)
            or self.base_delay_seconds < 0
            or self.max_delay_seconds < self.base_delay_seconds
            or self.max_delay_seconds > 5
        ):
            raise ValueError("Invalid Provider retry policy.")


class ProviderGateway:
    """Business-facing facade; explicit safe retries never switch providers."""

    def __init__(
        self,
        adapter: ProviderAdapter,
        *,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._adapter = adapter
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep

    async def _retry_call(
        self, operation: Callable[[], Awaitable[_Result]], *, retry_safe: bool
    ) -> _Result:
        for attempt in range(self._retry_policy.max_attempts):
            try:
                return await operation()
            except ProviderError as error:
                if (
                    not retry_safe
                    or not error.retryable
                    or attempt + 1 >= self._retry_policy.max_attempts
                ):
                    raise
                delay = error.retry_after_seconds
                if delay is None:
                    delay = min(
                        self._retry_policy.base_delay_seconds * (2**attempt),
                        self._retry_policy.max_delay_seconds,
                    )
                if (
                    not math.isfinite(delay)
                    or delay < 0
                    or delay > self._retry_policy.max_delay_seconds
                ):
                    raise
                await self._sleep(delay)
        raise AssertionError("unreachable retry state")

    async def generate_text(self, request: TextRequest, *, retry_safe: bool = False) -> TextResult:
        return await self._retry_call(
            lambda: self._adapter.generate_text(request), retry_safe=retry_safe
        )

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult:
        return await self._retry_call(
            lambda: self._adapter.generate_structured(request), retry_safe=retry_safe
        )

    async def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]:
        stream = self._adapter.stream_text(request)
        try:
            async for delta in stream:
                yield delta
        finally:
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()
