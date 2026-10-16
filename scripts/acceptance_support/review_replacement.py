"""Diagnostic-only review composition; no production default or generation routing changes."""

import json
from dataclasses import replace

from app.agents.hybrid_resource_review import INSTRUCTION, REVIEW_V4_PROMPT
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.learning_policy import active_policy_digest
from app.services.provider_gateway import ChatMessage, StructuredRequest, TaskProfile


def candidate_config():
    return {
        "version": "review-replacement-high-v1",
        "scope": "diagnostic-review-only",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "reasoning_effort": "high",
        "max_output_tokens": 8192,
        "timeout_seconds": 60,
        "temperature": 0,
        "review_prompt_version": REVIEW_V4_PROMPT,
        "policy_digest": active_policy_digest(),
        "entry_task_profile": "quality",
        "generation_routing": "unchanged",
        "single_changed_wire_path": "reasoning.effort",
        "baseline_effort": "low",
    }


class CandidateReviewGateway:
    """Used only by the offline review-entry proof; real execution replays its exact wire."""

    def __init__(self, config, settings, guard, *, transport):
        if config != candidate_config() or settings.model != config["model"]:
            raise ValueError("CANDIDATE_CONFIG_MISMATCH")
        self.config = dict(config)
        self.adapter = DeepSeekResponsesAdapter(
            settings, guard, transport=transport, reasoning_effort=config["reasoning_effort"]
        )
        self.calls = []

    async def generate_structured(self, request, *, retry_safe=False):
        if (
            retry_safe is not False
            or request.prompt.task_profile != TaskProfile.QUALITY
            or request.prompt.messages[0] != ChatMessage("system", INSTRUCTION)
            or json.loads(request.prompt.messages[1].content)["unit"]["binding"]["policy_digest"]
            != self.config["policy_digest"]
        ):
            raise ValueError("NOT_BOUND_REVIEW_REQUEST")
        # The comparison baseline already uses 8192; the business entry's default is 2048.
        # This diagnostic composition keeps that pre-existing override, not a new variable.
        self.calls.append(request)
        effective = StructuredRequest(
            replace(request.prompt, max_output_tokens=self.config["max_output_tokens"]),
            request.json_schema,
        )
        return await self.adapter.generate_structured(effective)
