"""Extract one evidence-backed transient profile without asking a questionnaire."""

import json
from collections.abc import Callable, Mapping
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
PROFILE_BEHAVIOR_PROMPT_VERSION = "profile-behavior-v1"
PROFILE_INSTRUCTION_VERSION = "profile-instructions-v2"
PROFILE_BEHAVIOR_INSTRUCTION_VERSION = "profile-behavior-instructions-v2"
_EXTRACTION_INSTRUCTIONS = """You extract an evidence-backed transient learning profile.
Only use facts explicitly stated in the student's one input. Never infer background,
ability, preferences, or prior knowledge. Keep every unknown dimension null and omit its
evidence. Preserve initial_query exactly. Every non-null dimension needs evidence using
only source initial_query. Return only the requested JSON object."""
_BEHAVIOR_INSTRUCTIONS = """Propose only a conservative profile field update from the
provided whitelisted learning-behavior summary. Never infer demographic background,
stable ability, or preferences from a single ambiguous action. Return an empty updates
object when evidence is insufficient. Do not output versions, evidence records, source,
confidence, raw answers, or fields outside the allowed list."""


def profile_contract(schema: Mapping[str, object], version: str) -> str:
    """Explain the existing wire contract without changing validation or fallback."""
    return (
        f"\nInstruction version: {version}. Emit exactly one JSON object, "
        "no Markdown, trailing text or additional root fields. Use the exact field names "
        "and required fields in this schema; do not rename or flatten fields.\n"
        + json.dumps(schema, ensure_ascii=False)
    )


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


@dataclass(frozen=True, slots=True)
class ProfileBehaviorProposal:
    """A field-only suggestion; provenance is assigned by trusted server code."""

    updates: dict[str, object]
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

    async def update_from_behavior(
        self, summary: dict[str, object], *, allowed_fields: tuple[str, ...]
    ) -> ProfileBehaviorProposal:
        """Ask for an allowlisted delta without sending prior profile or raw answers."""
        if not allowed_fields:
            return ProfileBehaviorProposal({}, False)
        properties = {
            field: {"type": "array" if field == "error_preferences" else "object"}
            for field in allowed_fields
        }
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["updates"],
            "properties": {
                "updates": {
                    "type": "object", "additionalProperties": False,
                    "properties": properties,
                }
            },
        }
        request = StructuredRequest(
            prompt=TextRequest(
                messages=(
                    ChatMessage(
                        role="system",
                        content=(
                            f"{_BEHAVIOR_INSTRUCTIONS}\n"
                            f"Prompt version: {PROFILE_BEHAVIOR_PROMPT_VERSION}.\n"
                            f"Allowed fields: {', '.join(allowed_fields)}."
                            + profile_contract(schema, PROFILE_BEHAVIOR_INSTRUCTION_VERSION)
                            + '\nThe only root field is updates. With insufficient evidence emit '
                            '{"updates": {}} exactly, not an empty root, no_change or a status. '
                            "Allowed fields belong inside updates only."
                        ),
                    ),
                    ChatMessage(
                        role="user",
                        content=json.dumps(summary, ensure_ascii=False, sort_keys=True),
                    ),
                ),
                task_profile=TaskProfile.FAST,
            ),
            json_schema=schema,
        )
        try:
            result = await self._gateway.generate_structured(request, retry_safe=True)
        except ProviderError:
            return ProfileBehaviorProposal({}, True)
        value = result.value
        if set(value) != {"updates"} or not isinstance(value["updates"], dict):
            return ProfileBehaviorProposal({}, True)
        updates = value["updates"]
        if not set(updates).issubset(allowed_fields):
            return ProfileBehaviorProposal({}, True)
        for field, field_value in updates.items():
            if field == "error_preferences":
                valid = isinstance(field_value, list) and bool(field_value)
            else:
                valid = isinstance(field_value, dict) and bool(field_value)
            if not valid:
                return ProfileBehaviorProposal({}, True)
        return ProfileBehaviorProposal(dict(updates), False)

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
                            + profile_contract(profile_output_schema(), PROFILE_INSTRUCTION_VERSION)
                            + "\nEvidence is an object keyed only by non-null profile dimensions; "
                            "each value is an array of records with exactly source, confidence, "
                            "observed_at, profile_version. Do not add inferred dimensions."
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
            if profile["initial_query"] != query or profile["profile_version"] != profile_version:
                raise ProfileSchemaError
            evidence = profile["evidence"]
            if not isinstance(evidence, dict) or any(
                not isinstance(records, list)
                or any(
                    not isinstance(record, dict) or record.get("source") != "initial_query"
                    for record in records
                )
                for records in evidence.values()
            ):
                raise ProfileSchemaError
        except (ProviderError, ProfileSchemaError):
            fallback = empty_transient_profile(query)
            fallback["profile_version"] = profile_version
            return ProfileExtraction(profile=fallback, degraded=True)
        return ProfileExtraction(profile=profile, degraded=False)
