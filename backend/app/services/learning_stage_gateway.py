"""Explicit, server-owned stage routing. No prompt-text detection or implicit fallback."""

from app.agents.learning_unit_generator import StructuredResourceGateway
from app.services.learning_contract import LearningContractError
from app.services.provider_gateway import StructuredRequest, StructuredResult

GENERATION_STAGES = frozenset(
    {
        "goal_mapping",
        "plan_generation",
        "plan_rebuild",
        "resource_generation",
        "resource_correction",
    }
)
REVIEW_STAGES = frozenset({"plan_check", "plan_recheck", "resource_review", "unit_review"})


class LearningStageGateway:
    def __init__(self, generation: StructuredResourceGateway, review: StructuredResourceGateway):
        self.generation = generation
        self.review = review

    async def generate_structured(
        self, request: StructuredRequest, *, retry_safe: bool = False
    ) -> StructuredResult:
        if retry_safe:
            raise LearningContractError("LEARNING_RETRY_FORBIDDEN")
        if request.stage in GENERATION_STAGES:
            gateway = self.generation
        elif request.stage in REVIEW_STAGES:
            gateway = self.review
        else:
            raise LearningContractError("LEARNING_STAGE_REQUIRED")
        return await gateway.generate_structured(request, retry_safe=False)
