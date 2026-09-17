"""Provider-neutral generation contract for P0 business services."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

MessageRole = Literal["system", "user", "assistant"]


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


class ProviderError(RuntimeError):
    """Stable safe error; adapters must never include raw vendor messages or keys."""

    def __init__(
        self, code: ProviderErrorCode, *, retry_after_seconds: float | None = None
    ) -> None:
        super().__init__(_SAFE_MESSAGES[code])
        self.code = code
        self.retry_after_seconds = retry_after_seconds

    @property
    def retryable(self) -> bool:
        return self.code in _RETRYABLE_CODES


class ProviderAdapter(Protocol):
    """Single-attempt adapter boundary implemented by the configured P0 provider."""

    async def generate_text(self, request: TextRequest) -> TextResult: ...

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult: ...

    def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]: ...


class ProviderGateway:
    """Business-facing facade; delegates once and never silently switches providers."""

    def __init__(self, adapter: ProviderAdapter) -> None:
        self._adapter = adapter

    async def generate_text(self, request: TextRequest) -> TextResult:
        return await self._adapter.generate_text(request)

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        return await self._adapter.generate_structured(request)

    async def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]:
        async for delta in self._adapter.stream_text(request):
            yield delta
