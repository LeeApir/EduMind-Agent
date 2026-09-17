"""Independent review and bounded targeted correction for formal resources."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from app.agents.learning_resource_prompt import learning_resource_prompt
from app.agents.learning_resource_schema import resource_output_schema, validate_learning_resource
from app.agents.learning_unit_generator import PendingLearningResource
from app.agents.review_schema import (
    MAX_TARGETED_CORRECTIONS,
    REVIEW_PROMPT_VERSION,
    ReviewSchemaError,
    ReviewVerdict,
    review_output_schema,
    severe_code_issues,
    validate_review,
)
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    StructuredRequest,
    StructuredResult,
    TaskProfile,
    TextRequest,
)

_REVIEW_INSTRUCTIONS = """Independently review this formal learning resource. Check factual
accuracy against supplied context, difficulty fit, misconception coverage, and code safety.
Return only the requested JSON review. Do not pass a resource with any unresolved issue."""


class StructuredReviewGateway(Protocol):
    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult: ...


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    resource: PendingLearningResource
    verdict: ReviewVerdict
    issues: tuple[Mapping[str, str], ...]
    review_model_id: str | None
    correction_attempts: int

    @property
    def approved(self) -> bool:
        return self.verdict is ReviewVerdict.PASS


class ReviewAgent:
    def __init__(self, gateway: StructuredReviewGateway) -> None:
        self._gateway = gateway

    @staticmethod
    def _candidate_payload(resource: PendingLearningResource) -> str:
        return json.dumps(
            {"resource_type": resource.resource_type.value, "content": resource.content},
            ensure_ascii=False,
            sort_keys=True,
        )

    async def _review(
        self, resource: PendingLearningResource
    ) -> tuple[dict[str, object], str | None]:
        local_issues = severe_code_issues(resource.resource_type, resource.content)
        if local_issues:
            return (
                {
                    "review_version": REVIEW_PROMPT_VERSION,
                    "verdict": "reject",
                    "issues": local_issues,
                },
                None,
            )
        request = StructuredRequest(
            prompt=TextRequest(
                messages=(
                    ChatMessage(role="system", content=_REVIEW_INSTRUCTIONS),
                    ChatMessage(role="user", content=self._candidate_payload(resource)),
                ),
                task_profile=TaskProfile.REVIEW,
            ),
            json_schema=review_output_schema(),
        )
        try:
            result = await self._gateway.generate_structured(request, retry_safe=True)
            return validate_review(result.value), result.model_id
        except (ProviderError, ReviewSchemaError):
            return (
                {
                    "review_version": REVIEW_PROMPT_VERSION,
                    "verdict": "reject",
                    "issues": [
                        {
                            "area": "fact",
                            "severity": "severe",
                            "message": "Resource review is unavailable.",
                        }
                    ],
                },
                None,
            )

    async def _correct(
        self, resource: PendingLearningResource, issues: tuple[Mapping[str, str], ...]
    ) -> PendingLearningResource | None:
        serialized_issues = json.dumps(list(issues), ensure_ascii=False)
        request = StructuredRequest(
            prompt=TextRequest(
                messages=(
                    ChatMessage(
                        role="system", content=learning_resource_prompt(resource.resource_type)
                    ),
                    ChatMessage(
                        role="user",
                        content=(
                            f"Current candidate: {self._candidate_payload(resource)}\n"
                            f"Correct only these review issues: {serialized_issues}"
                        ),
                    ),
                ),
                task_profile=TaskProfile.QUALITY,
            ),
            json_schema=resource_output_schema(resource.resource_type),
        )
        try:
            result = await self._gateway.generate_structured(request, retry_safe=True)
            envelope = validate_learning_resource(
                result.value, expected_type=resource.resource_type
            )
        except (ProviderError, ReviewSchemaError):
            return None
        content = envelope["content"]
        assert isinstance(content, dict)
        return PendingLearningResource(
            resource_type=resource.resource_type,
            content=content,
            prompt_version=resource.prompt_version,
            model_id=result.model_id,
            usage=result.usage,
        )

    async def review(self, resource: PendingLearningResource) -> ReviewOutcome:
        """Approve only an independent pass; revise at most twice, otherwise reject."""
        candidate = resource
        review_model_id: str | None = None
        for attempt in range(MAX_TARGETED_CORRECTIONS + 1):
            review, model_id = await self._review(candidate)
            review_model_id = model_id or review_model_id
            raw_verdict = review["verdict"]
            raw_issues = review["issues"]
            assert isinstance(raw_verdict, str)
            assert isinstance(raw_issues, list)
            verdict = ReviewVerdict(raw_verdict)
            typed_issues = tuple(cast(dict[str, str], issue) for issue in raw_issues)
            if verdict is not ReviewVerdict.REVISE:
                return ReviewOutcome(candidate, verdict, typed_issues, review_model_id, attempt)
            if attempt == MAX_TARGETED_CORRECTIONS:
                return ReviewOutcome(
                    candidate,
                    ReviewVerdict.REJECT,
                    typed_issues
                    + (
                        {
                            "area": "fact",
                            "severity": "major",
                            "message": "Correction limit reached.",
                        },
                    ),
                    review_model_id,
                    attempt,
                )
            corrected = await self._correct(candidate, typed_issues)
            if corrected is None:
                return ReviewOutcome(
                    candidate,
                    ReviewVerdict.REJECT,
                    typed_issues,
                    review_model_id,
                    attempt + 1,
                )
            candidate = corrected
        raise AssertionError("unreachable review state")
