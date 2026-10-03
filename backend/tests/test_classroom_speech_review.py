"""High-risk classroom-speech escalation maps one bounded review to retraction."""

import asyncio

from app.agents.classroom_speech_review import (
    SPEECH_REVIEW_INSTRUCTION_VERSION,
    SPEECH_REVIEW_PROMPT_VERSION,
    SpeechReviewer,
    SpeechReviewVerdict,
)
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
)


class StubReviewGateway:
    def __init__(
        self,
        *,
        verdict: str = "pass",
        error_code: ProviderErrorCode | None = None,
        invalid: bool = False,
    ) -> None:
        self.verdict = verdict  # "pass" | "revise" | "reject"
        self.error_code = error_code
        self.invalid = invalid
        self.last_request: StructuredRequest | None = None

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult:
        self.last_request = request
        if self.error_code is not None:
            raise ProviderError(self.error_code)
        if self.invalid:
            return StructuredResult(value={"verdict": "pass"}, model_id="review-test")
        issues = (
            []
            if self.verdict == "pass"
            else [{"area": "code_safety", "severity": "major", "message": "Unsafe."}]
        )
        return StructuredResult(
            value={
                "review_version": "resource-review-v3",
                "verdict": self.verdict,
                "issues": issues,
            },
            model_id="review-test",
        )


def test_pass_approves() -> None:
    reviewer = SpeechReviewer(StubReviewGateway(verdict="pass"))
    outcome = asyncio.run(reviewer.review(turn_text="普通讲解", reference="{}"))
    assert outcome.verdict is SpeechReviewVerdict.PASS
    assert outcome.approved is True
    assert outcome.model_id == "review-test"


def test_reject_retracts() -> None:
    reviewer = SpeechReviewer(StubReviewGateway(verdict="reject"))
    outcome = asyncio.run(reviewer.review(turn_text="危险内容", reference="{}"))
    assert outcome.verdict is SpeechReviewVerdict.REJECT
    assert outcome.approved is False


def test_revise_is_mapped_to_reject() -> None:
    reviewer = SpeechReviewer(StubReviewGateway(verdict="revise"))
    outcome = asyncio.run(reviewer.review(turn_text="需要修改", reference="{}"))
    assert outcome.verdict is SpeechReviewVerdict.REJECT


def test_provider_error_returns_unavailable() -> None:
    reviewer = SpeechReviewer(
        StubReviewGateway(error_code=ProviderErrorCode.TEMPORARILY_UNAVAILABLE)
    )
    outcome = asyncio.run(reviewer.review(turn_text="危险内容", reference="{}"))
    assert outcome.verdict is SpeechReviewVerdict.UNAVAILABLE
    assert outcome.approved is False
    assert outcome.model_id is None


def test_invalid_review_schema_returns_unavailable() -> None:
    reviewer = SpeechReviewer(StubReviewGateway(invalid=True))
    outcome = asyncio.run(reviewer.review(turn_text="危险内容", reference="{}"))
    assert outcome.verdict is SpeechReviewVerdict.UNAVAILABLE


def test_review_request_pins_prompt_and_instruction_versions() -> None:
    gateway = StubReviewGateway(verdict="pass")
    reviewer = SpeechReviewer(gateway)
    asyncio.run(reviewer.review(turn_text="危险内容", reference='{"node": {}}'))
    assert gateway.last_request is not None
    system = gateway.last_request.prompt.messages[0].content
    assert SPEECH_REVIEW_PROMPT_VERSION in system
    assert SPEECH_REVIEW_INSTRUCTION_VERSION in system
    schema = gateway.last_request.json_schema
    assert schema["properties"]["review_version"]["const"] == "resource-review-v3"
