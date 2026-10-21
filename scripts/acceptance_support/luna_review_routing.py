"""Explicit DeepSeek generation / Luna review candidate; no implicit environment factory.

Production agents and Responses adapter are reused. Only a separately approved diagnostic
runner may supply live transports/credentials. Offline construction uses placeholders.
"""

import asyncio
import json
from dataclasses import dataclass, replace
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx

from app.agents.hybrid_resource_review import INSTRUCTION
from app.core.config import ProviderSettings
from app.core.provider_target import ApprovedTarget
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.learning_policy import active_policy_digest
from app.services.provider_gateway import StructuredRequest, TaskProfile


@dataclass(frozen=True)
class RouteConfig:
    generation_base: str = "https://api.deepseek.com"
    generation_model: str = "deepseek-flash"
    review_base: str = "https://www.cbbb.fun/v1"
    review_model: str = "gpt-6-luna"
    review_reasoning: str = "low"
    review_output: int = 8192
    per_call_seconds: int = 60

    def check(self):
        if self != RouteConfig():
            raise ValueError("CANDIDATE_CONFIG_CHANGED")


CONFIG = RouteConfig()


class ExplicitRouter:
    """Exact review instruction selects Luna; other approved agent calls select DeepSeek."""

    def __init__(self, generation, review, config=CONFIG):
        config.check()
        self.generation, self.review, self.config = generation, review, config
        self.last_usage = None

    async def generate_structured(self, request, *, retry_safe=False):
        self.config.check()
        if retry_safe is not False:
            raise ValueError("RETRY_FORBIDDEN")
        is_review = request.prompt.messages[0].content == INSTRUCTION
        if request.prompt.task_profile != TaskProfile.QUALITY:
            raise ValueError("UNEXPECTED_TASK_PROFILE")
        if is_review:
            user = json.loads(request.prompt.messages[1].content)
            binding = user.get("unit", {}).get("binding")
            if binding and binding["policy_digest"] != active_policy_digest():
                raise ValueError("POLICY_MISMATCH")
            effective = StructuredRequest(
                replace(request.prompt, max_output_tokens=self.config.review_output),
                request.json_schema,
            )
            adapter, model, limit = self.review, self.config.review_model, self.config.review_output
        else:
            effective = request
            adapter, model, limit = (
                self.generation,
                self.config.generation_model,
                request.prompt.max_output_tokens,
            )
        async with asyncio.timeout(self.config.per_call_seconds):
            result = await adapter.generate_structured(effective)
        self.last_usage = result.usage
        if result.model_id != model:
            raise ValueError("RESPONSE_MODEL_CHANGED")
        if (
            result.usage is None
            or type(result.usage.input_tokens) is not int
            or type(result.usage.output_tokens) is not int
            or result.usage.input_tokens < 0
            or result.usage.output_tokens < 0
            or result.usage.output_tokens > limit
        ):
            raise ValueError("USAGE_MISSING_OR_EXCEEDED")
        if result.transport_audit is None:
            raise ValueError("AUDIT_MISSING")
        self.last_usage = result.usage
        return result


def offline_router(value):
    """Mock HTTP capture at real configured Host/SNI/path; no DNS or credential access."""
    generation_wires, review_wires, targets = [], [], []

    def adapter(base, model, reasoning, wires):
        host = urlsplit(base).hostname
        guard = SimpleNamespace(approve_base=lambda: ApprovedTarget(base, host, 443, ("8.8.8.8",)))

        def respond(request):
            wires.append(request.content)
            targets.append(
                {
                    "role": "generation" if model == CONFIG.generation_model else "review",
                    "url": str(request.url),
                    "host": request.headers["host"],
                    "sni": request.extensions.get("sni_hostname"),
                }
            )
            return httpx.Response(
                200,
                json={
                    "model": model,
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": json.dumps(value)}],
                        }
                    ],
                    "usage": {"input_tokens": 100, "output_tokens": 100},
                },
            )

        return DeepSeekResponsesAdapter(
            ProviderSettings(base, "OFFLINE_PLACEHOLDER", model),
            guard,
            transport=httpx.MockTransport(respond),
            reasoning_effort=reasoning,
        )

    router = ExplicitRouter(
        adapter(CONFIG.generation_base, CONFIG.generation_model, "none", generation_wires),
        adapter(CONFIG.review_base, CONFIG.review_model, CONFIG.review_reasoning, review_wires),
    )
    return router, generation_wires, review_wires, targets
