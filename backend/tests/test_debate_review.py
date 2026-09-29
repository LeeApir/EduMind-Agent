"""Debate review is independent, bounded, and never promotes partial results."""

import asyncio
from collections import deque

from test_debate_candidate_generator import candidate

from app.agents.debate_candidate_generator import PendingDebateCandidate
from app.agents.debate_candidate_schema import DEBATE_CANDIDATE_SCHEMA_VERSION
from app.agents.debate_review import (
    DEBATE_REVIEW_VERSION,
    MAX_DEBATE_CORRECTIONS,
    DebateReviewAgent,
    DebateReviewVerdict,
)
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
)


def pending() -> PendingDebateCandidate:
    return PendingDebateCandidate(
        content={**candidate(), "graph_basis": {"graph_version": "g1", "nodes": []}},
        schema_version=DEBATE_CANDIDATE_SCHEMA_VERSION,
        prompt_version="array-vs-linked-list-instructions-v1",
        model_id="generation-model", usage=None,
    )


def decision(verdict: str, area: str = "fact") -> StructuredResult:
    issues = [] if verdict == "pass" else [{
        "area": area, "severity": "severe", "message": "数组随机访问不是 O(n)。",
    }]
    return StructuredResult(value={
        "review_version": DEBATE_REVIEW_VERSION, "verdict": verdict, "issues": issues,
    }, model_id="review-model")


class Gateway:
    def __init__(self, *results: StructuredResult | ProviderError) -> None:
        self.results = deque(results)
        self.calls: list[tuple[StructuredRequest, bool]] = []

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult:
        self.calls.append((request, retry_safe))
        outcome = self.results.popleft()
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome


def test_clear_correct_fixture_passes_only_after_independent_review() -> None:
    async def exercise() -> None:
        gateway = Gateway(decision("pass"))
        outcome = await DebateReviewAgent(gateway).review(pending())
        assert outcome.approved
        assert outcome.verdict is DebateReviewVerdict.PASS
        assert outcome.review_model_id == "review-model"
        assert outcome.correction_attempts == 0
        assert len(gateway.calls) == 1
        assert gateway.calls[0][0].prompt.task_profile == "review"
        assert all(not retry_safe for _, retry_safe in gateway.calls)

    asyncio.run(exercise())


def test_severe_false_algorithm_claim_is_rejected_with_no_correction() -> None:
    async def exercise() -> None:
        gateway = Gateway(decision("reject"))
        outcome = await DebateReviewAgent(gateway).review(pending())
        assert not outcome.approved
        assert outcome.verdict is DebateReviewVerdict.REJECT
        assert outcome.issues[0]["severity"] == "severe"
        assert len(gateway.calls) == 1

    asyncio.run(exercise())


def test_revisions_are_bounded_and_final_pass_uses_corrected_candidate() -> None:
    async def exercise() -> None:
        revised = candidate()
        revised["perspectives"]["performance"] = "修正后的条件化性能结论。"
        gateway = Gateway(
            decision("revise"), StructuredResult(value=revised, model_id="correction-model"),
            decision("pass"),
        )
        outcome = await DebateReviewAgent(gateway).review(pending())
        assert outcome.approved
        assert outcome.correction_attempts == 1
        assert outcome.candidate.model_id == "correction-model"
        assert (
            outcome.candidate.content["perspectives"]["performance"]
            == "修正后的条件化性能结论。"
        )
        assert outcome.candidate.content["graph_basis"]["graph_version"] == "g1"
        assert len(gateway.calls) == 3

    asyncio.run(exercise())


def test_repeated_revise_stops_at_limit_without_publication() -> None:
    async def exercise() -> None:
        gateway = Gateway(
            decision("revise"), StructuredResult(value=candidate(), model_id="fix-1"),
            decision("revise"), StructuredResult(value=candidate(), model_id="fix-2"),
            decision("revise"),
        )
        outcome = await DebateReviewAgent(gateway).review(pending())
        assert not outcome.approved
        assert outcome.correction_attempts == MAX_DEBATE_CORRECTIONS
        assert len(gateway.calls) == 2 * MAX_DEBATE_CORRECTIONS + 1

    asyncio.run(exercise())


def test_timeout_or_malformed_review_cannot_pass() -> None:
    async def exercise() -> None:
        for result in (
            ProviderError(ProviderErrorCode.TIMEOUT),
            StructuredResult(value={"verdict": "pass"}, model_id="bad-model"),
        ):
            gateway = Gateway(result)
            outcome = await DebateReviewAgent(gateway).review(pending())
            assert not outcome.approved
            assert outcome.unavailable
            assert outcome.review_model_id is None
            assert len(gateway.calls) == 1

    asyncio.run(exercise())
