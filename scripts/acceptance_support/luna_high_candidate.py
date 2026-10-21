"""Single final review candidate: only low -> high; production defaults stay unchanged."""

import json
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
from acceptance_support.luna_review_routing import ExplicitRouter, RouteConfig
from acceptance_support.luna_schema_projection import ProjectedReviewAdapter

from app.core.config import ProviderSettings
from app.core.provider_target import ApprovedTarget
from app.services.deepseek_responses import DeepSeekResponsesAdapter


@dataclass(frozen=True)
class HighConfig(RouteConfig):
    review_reasoning: str = "high"

    def check(self):
        if self != HighConfig():
            raise ValueError("CANDIDATE_CONFIG_CHANGED")


CONFIG = HighConfig()


def offline_router(value):
    generation, reviews, targets = [], [], []

    def adapter(base, model, reasoning, wires, cls):
        host = urlsplit(base).hostname
        guard = SimpleNamespace(approve_base=lambda: ApprovedTarget(base, host, 443, ("8.8.8.8",)))

        def reply(request):
            wires.append(request.content)
            targets.append(
                dict(
                    host=request.headers["host"],
                    sni=request.extensions.get("sni_hostname"),
                    url=str(request.url),
                )
            )
            return httpx.Response(
                200,
                stream=httpx.ByteStream(
                    json.dumps(
                        {
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
                        }
                    ).encode()
                ),
            )

        return cls(
            ProviderSettings(base, "OFFLINE_ONLY", model),
            guard,
            transport=httpx.MockTransport(reply),
            reasoning_effort=reasoning,
        )

    router = ExplicitRouter(
        adapter(
            CONFIG.generation_base,
            CONFIG.generation_model,
            "none",
            generation,
            DeepSeekResponsesAdapter,
        ),
        adapter(
            CONFIG.review_base,
            CONFIG.review_model,
            CONFIG.review_reasoning,
            reviews,
            ProjectedReviewAdapter,
        ),
        config=CONFIG,
    )
    return router, generation, reviews, targets
