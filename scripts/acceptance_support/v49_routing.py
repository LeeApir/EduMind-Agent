"""Explicit diagnostic composition: production agents and adapters, injectable offline HTTP.

No credentials, environment loading, DNS, live transport or production registration here.
The injected ConnectionOperation must own live consent and budget if used by a future runner.
"""

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import httpx
from acceptance_support.om_diagnostic import valid_review
from acceptance_support.qwen_review_budget import sha

from app.agents.hybrid_resource_review import INSTRUCTION, REVIEW_V4_PROMPT
from app.core.config import ProviderSettings
from app.core.provider_target import ApprovedTarget
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.learning_contract import canonical
from app.services.learning_policy import active_policy_digest
from app.services.openai_compatible import OpenAICompatibleAdapter
from app.services.provider_connection_dispatch import ModelCapabilities
from app.services.provider_gateway import StructuredRequest, TaskProfile, TransportAudit
from app.services.qwen_schema import QWEN_SCHEMA_PROFILE

GENERATION_MODEL = "deepseek-flash"
REVIEW_MODEL = "qwen3.8-max-0902"
REVIEW_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def capabilities():
    return ModelCapabilities(
        UUID(int=49),
        1,
        REVIEW_MODEL,
        "v49-qwen-nonthinking-8192-v1",
        structured_output=True,
        structured_transport="json_schema",
        output_token_parameter="max_completion_tokens",
        thinking_enabled=False,
        schema_profile=QWEN_SCHEMA_PROFILE,
    )


class ExplicitRouter:
    """The same explicit selection used by capture; no implicit model fallback."""

    def __init__(self, generation, review_operation):
        self.generation = generation
        self.operation = review_operation

    async def generate_structured(self, request, *, retry_safe=False):
        if retry_safe is not False:
            raise ValueError("RETRY_FORBIDDEN")
        if request.prompt.messages[0].content != INSTRUCTION:
            return await self.generation.generate_structured(request)
        user = json.loads(request.prompt.messages[1].content)
        binding = user.get("unit", {}).get("binding", user.get("candidate", {}).get("binding"))
        # Resource requests carry their binding via authoritative input; operation identity
        # is checked at live dispatch. Unit requests also have an embedded exact policy.
        if binding is not None and binding["policy_digest"] != active_policy_digest():
            raise ValueError("POLICY_MISMATCH")
        if request.prompt.task_profile != TaskProfile.QUALITY:
            raise ValueError("REVIEW_PROFILE_MISMATCH")
        effective = StructuredRequest(
            replace(request.prompt, max_output_tokens=8192, temperature=0), request.json_schema
        )
        result = await OpenAICompatibleAdapter(self.operation).generate_structured(effective)
        if result.model_id != REVIEW_MODEL:
            raise ValueError("MODEL_MISMATCH")
        return replace(
            result,
            transport_audit=TransportAudit(
                sha(self.operation.wires[-1]),
                sha(self.operation.response_bytes),
                sha(
                    canonical(
                        {
                            "model": REVIEW_MODEL,
                            "prompt": REVIEW_V4_PROMPT,
                            "policy": active_policy_digest(),
                            "schema": QWEN_SCHEMA_PROFILE,
                            "thinking": False,
                            "output": 8192,
                        }
                    )
                ),
            ),
        )


class OfflineReviewOperation:
    """Only HTTP is scripted; this does not claim actual consent/DB/DNS verification."""

    def __init__(self):
        self.request = SimpleNamespace(
            route=SimpleNamespace(model_id=REVIEW_MODEL), capabilities=capabilities()
        )
        self.wires = []
        self.targets = []
        self.response_bytes = b""

    def _check(self):
        if (
            self.request.route.model_id != REVIEW_MODEL
            or self.request.capabilities != capabilities()
        ):
            raise ValueError("ROUTE_CHANGED")

    @asynccontextmanager
    async def send(self, body, *, stream=False):
        assert not stream

        def respond(request):
            self.wires.append(request.content)
            self.targets.append(str(request.url))
            data = json.loads(body["messages"][1]["content"])
            self.response_bytes = json.dumps(
                {
                    "model": REVIEW_MODEL,
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    valid_review(data["review_contract"]["scope"])
                                ),
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 100},
                }
            ).encode()
            return httpx.Response(200, content=self.response_bytes)

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False) as c:
            yield await c.post(REVIEW_ENDPOINT + "/chat/completions", json=body)


def offline_router(generation_value):
    """Build with exact selected hosts and adapters, replacing HTTP with MockTransport."""
    wires, targets = [], []

    def respond(request):
        wires.append(request.content)
        targets.append(
            {
                "url": str(request.url),
                "host": request.headers["host"],
                "sni": request.extensions.get("sni_hostname"),
            }
        )
        return httpx.Response(
            200,
            json={
                "model": GENERATION_MODEL,
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": json.dumps(generation_value)}],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 100},
            },
        )

    guard = SimpleNamespace(
        approve_base=lambda: ApprovedTarget(
            "https://api.deepseek.com", "api.deepseek.com", 443, ("8.8.8.8",)
        )
    )
    adapter = DeepSeekResponsesAdapter(
        ProviderSettings("https://api.deepseek.com", "OFFLINE_PLACEHOLDER", GENERATION_MODEL),
        guard,
        transport=httpx.MockTransport(respond),
        reasoning_effort="none",
    )
    router = ExplicitRouter(adapter, OfflineReviewOperation())
    return router, wires, targets
