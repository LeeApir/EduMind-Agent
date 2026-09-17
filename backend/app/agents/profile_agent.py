"""Extract one evidence-backed transient profile without asking a questionnaire."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.agents.profile_schema import (
    PROFILE_VERSION,
    ProfileSchemaError,
    ProfileValue,
    empty_transient_profile,
    profile_output_schema,
    validate_transient_profile,
)
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    StructuredRequest,
    StructuredResult,
    TaskProfile,
    TextRequest,
)

PROFILE_PROMPT_VERSION = "profile-v1"
_EXTRACTION_INSTRUCTIONS = """You extract an evidence-backed transient learning profile.
Only use facts explicitly stated in the student's one input. Never infer background,
ability, preferences, or prior knowledge. Keep every unknown dimension null and omit its
evidence. Preserve initial_query exactly. Every non-null dimension needs evidence using
only source initial_query. Return only the requested JSON object."""


class StructuredProfileGateway(Protocol):
    """The narrow provider dependency required for profile extraction."""

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult: ...


class ProfileInputError(ValueError):
    """A safe, actionable error for a missing first learning goal."""

    def __init__(self) -> None:
        super().__init__("A learning goal is required to start learning.")


@dataclass(frozen=True, slots=True)
class ProfileExtraction:
    """Validated data, or a deliberate empty fallback that never blocks learning."""

    profile: dict[str, ProfileValue]
    degraded: bool


class ProfileAgent:
    """Turn a single initial request into a conservative profile snapshot."""

    def __init__(
        self,
        gateway: StructuredProfileGateway,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._gateway = gateway
        self._now = now or (lambda: datetime.now(timezone.utc))

    async def extract(
        self, initial_query: str, *, profile_version: int = PROFILE_VERSION
    ) -> ProfileExtraction:
        if not isinstance(initial_query, str) or not initial_query.strip():
            raise ProfileInputError
        if profile_version < PROFILE_VERSION:
            raise ProfileSchemaError

        query = initial_query.strip()
        request = StructuredRequest(
            prompt=TextRequest(
                messages=(
                    ChatMessage(
                        role="system",
                        content=(
                            f"{_EXTRACTION_INSTRUCTIONS}\n"
                            f"Prompt version: {PROFILE_PROMPT_VERSION}.\n"
                            f"Set profile_version to {profile_version}.\n"
                            "Use this ISO-8601 timestamp with timezone for every "
                            f"observed_at: {self._now().isoformat()}."
                        ),
                    ),
                    ChatMessage(role="user", content=query),
                ),
                task_profile=TaskProfile.FAST,
            ),
            json_schema=profile_output_schema(),
        )
        try:
            result = await self._gateway.generate_structured(request, retry_safe=True)
            profile = validate_transient_profile(result.value)
            if (
                profile["initial_query"] != query
                or profile["profile_version"] != profile_version
            ):
                raise ProfileSchemaError
        except (ProviderError, ProfileSchemaError):
            return ProfileExtraction(profile=empty_transient_profile(query), degraded=True)
        return ProfileExtraction(profile=profile, degraded=False)
