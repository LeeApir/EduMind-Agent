"""Generate unreviewed explanation, code, and exercise candidates for one topic."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from app.agents.learning_resource_prompt import learning_resource_prompt
from app.agents.learning_resource_schema import (
    RESOURCE_PROMPT_VERSION,
    LearningResourceType,
    ResourceSchemaError,
    resource_output_schema,
    validate_learning_resource,
)
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
    TaskProfile,
    TextRequest,
    TokenUsage,
)


class ResourceGenerationInputError(ValueError):
    """A safe input error before a provider request is made."""

    def __init__(self) -> None:
        super().__init__("A knowledge point, learning goal, and code language are required.")


class StructuredResourceGateway(Protocol):
    """The narrow structured generation capability used by this agent."""

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult: ...


@dataclass(frozen=True, slots=True)
class LearningResourceRequest:
    knowledge_point: str
    learner_goal: str
    code_language: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.knowledge_point, self.learner_goal, self.code_language)
        ):
            raise ResourceGenerationInputError


@dataclass(frozen=True, slots=True)
class PendingLearningResource:
    """A schema-valid candidate that must pass ReviewAgent before publication."""

    resource_type: LearningResourceType
    content: Mapping[str, object]
    prompt_version: str
    model_id: str
    usage: TokenUsage | None
    review_status: Literal["pending"] = "pending"


@dataclass(frozen=True, slots=True)
class ResourceGenerationFailure:
    resource_type: LearningResourceType
    code: ProviderErrorCode
    message: str


@dataclass(frozen=True, slots=True)
class LearningUnitGeneration:
    resources: tuple[PendingLearningResource, ...]
    failures: tuple[ResourceGenerationFailure, ...]


class LearningUnitGenerator:
    """Generate each P0 resource independently so one failure does not invent a replacement."""

    def __init__(self, gateway: StructuredResourceGateway) -> None:
        self._gateway = gateway

    @staticmethod
    def _context(request: LearningResourceRequest, resource_type: LearningResourceType) -> str:
        language_instruction = (
            f"Requested code language: {request.code_language}."
            if resource_type is LearningResourceType.CODE
            else ""
        )
        return "\n".join(
            part
            for part in (
                f"Knowledge point: {request.knowledge_point.strip()}",
                f"Learner goal: {request.learner_goal.strip()}",
                language_instruction,
            )
            if part
        )

    async def generate(self, request: LearningResourceRequest) -> LearningUnitGeneration:
        """Return all valid candidates and explicit safe errors for failed resource types."""
        resources: list[PendingLearningResource] = []
        failures: list[ResourceGenerationFailure] = []
        for resource_type in LearningResourceType:
            provider_request = StructuredRequest(
                prompt=TextRequest(
                    messages=(
                        ChatMessage(role="system", content=learning_resource_prompt(resource_type)),
                        ChatMessage(role="user", content=self._context(request, resource_type)),
                    ),
                    task_profile=TaskProfile.QUALITY,
                ),
                json_schema=resource_output_schema(resource_type),
            )
            try:
                result = await self._gateway.generate_structured(provider_request, retry_safe=True)
                envelope = validate_learning_resource(result.value, expected_type=resource_type)
            except ProviderError as error:
                failures.append(
                    ResourceGenerationFailure(
                        resource_type=resource_type,
                        code=error.code,
                        message=str(error),
                    )
                )
                continue
            except ResourceSchemaError as error:
                failures.append(
                    ResourceGenerationFailure(
                        resource_type=resource_type,
                        code=ProviderErrorCode.INVALID_OUTPUT,
                        message=str(error),
                    )
                )
                continue

            content = envelope["content"]
            assert isinstance(content, dict)
            resources.append(
                PendingLearningResource(
                    resource_type=resource_type,
                    content=content,
                    prompt_version=RESOURCE_PROMPT_VERSION,
                    model_id=result.model_id,
                    usage=result.usage,
                )
            )
        return LearningUnitGeneration(resources=tuple(resources), failures=tuple(failures))
