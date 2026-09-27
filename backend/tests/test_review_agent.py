"""ReviewAgent gates severe code and bounds directed corrections."""

import asyncio
import json

from app.agents.learning_resource_schema import LearningResourceType
from app.agents.learning_unit_generator import PendingLearningResource
from app.agents.review_agent import REVIEW_INSTRUCTION_VERSION, ReviewAgent
from app.agents.review_schema import REVIEW_PROMPT_VERSION, ReviewVerdict, review_output_schema
from app.services.provider_gateway import StructuredRequest, StructuredResult


def review(verdict: str, issues: list[dict[str, str]]) -> StructuredResult:
    return StructuredResult(
        value={"review_version": REVIEW_PROMPT_VERSION, "verdict": verdict, "issues": issues},
        model_id="review-model",
    )


def code_candidate(source: str = 'printf("ok\\n");') -> PendingLearningResource:
    return PendingLearningResource(
        resource_type=LearningResourceType.CODE,
        content={
            "language": "C",
            "source": source,
            "expected_output": "ok",
            "key_steps": ["输出"],
            "display_only": True,
        },
        prompt_version="learning-resources-v1",
        model_id="generation-model",
        usage=None,
    )


class QueueGateway:
    def __init__(self, outcomes: list[StructuredResult]) -> None:
        self.outcomes = outcomes
        self.requests: list[StructuredRequest] = []

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult:
        assert retry_safe is True
        self.requests.append(request)
        return self.outcomes.pop(0)


def test_passed_review_approves_candidate() -> None:
    async def exercise() -> None:
        gateway = QueueGateway([review("pass", [])])
        outcome = await ReviewAgent(gateway).review(code_candidate())
        assert outcome.approved is True
        assert outcome.verdict is ReviewVerdict.PASS
        assert outcome.correction_attempts == 0
        instruction = gateway.requests[0].prompt.messages[0].content
        assert REVIEW_INSTRUCTION_VERSION in instruction
        assert json.dumps(review_output_schema(), ensure_ascii=False) in instruction
        assert "examples demonstrate serialization only" in instruction
        assert "resource-review-instructions-v2" in instruction
        assert "including NULL dereference, use-after-free" in instruction
        assert (
            "even when the unsafe claim appears only in explanation or exercise text" in instruction
        )
        assert "Use fact for non-safety conceptual or complexity errors" in instruction
        assert "Do not invent a safety issue in a correct resource" in instruction

    asyncio.run(exercise())


def test_revise_once_then_passes_with_corrected_resource() -> None:
    corrected = {
        "resource_type": "code",
        "prompt_version": "learning-resources-v1",
        "content": {
            "language": "C",
            "source": 'printf("safe\\n");',
            "expected_output": "safe",
            "key_steps": ["输出"],
            "display_only": True,
        },
    }

    async def exercise() -> None:
        gateway = QueueGateway(
            [
                review(
                    "revise", [{"area": "difficulty", "severity": "minor", "message": "Simplify."}]
                ),
                StructuredResult(value=corrected, model_id="generation-model"),
                review("pass", []),
            ]
        )
        outcome = await ReviewAgent(gateway).review(code_candidate())
        assert outcome.approved is True
        assert outcome.correction_attempts == 1
        assert outcome.resource.content["expected_output"] == "safe"

    asyncio.run(exercise())


def test_severe_code_is_rejected_locally_without_provider_call() -> None:
    async def exercise() -> None:
        gateway = QueueGateway([])
        outcome = await ReviewAgent(gateway).review(code_candidate("os.system('bad')"))
        assert outcome.approved is False
        assert outcome.verdict is ReviewVerdict.REJECT
        assert outcome.issues[0]["area"] == "code_safety"
        assert gateway.requests == []

    asyncio.run(exercise())


def test_correction_limit_rejects_unresolved_candidate() -> None:
    issue = {"area": "fact", "severity": "major", "message": "Correct fact."}
    correction = {
        "resource_type": "code",
        "prompt_version": "learning-resources-v1",
        "content": {
            "language": "C",
            "source": 'printf("still\\n");',
            "expected_output": "still",
            "key_steps": ["输出"],
            "display_only": True,
        },
    }

    async def exercise() -> None:
        gateway = QueueGateway(
            [
                review("revise", [issue]),
                StructuredResult(value=correction, model_id="generation-model"),
                review("revise", [issue]),
                StructuredResult(value=correction, model_id="generation-model"),
                review("revise", [issue]),
            ]
        )
        outcome = await ReviewAgent(gateway).review(code_candidate())
        assert outcome.approved is False
        assert outcome.verdict is ReviewVerdict.REJECT
        assert outcome.correction_attempts == 2
        assert outcome.issues[-1]["message"] == "Correction limit reached."

    asyncio.run(exercise())
