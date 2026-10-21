"""Offline stage-isolated probes. No environment, credentials, DB or live transport factory."""

import asyncio
import json
import re
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
from acceptance_support.luna_schema_projection import projection, schema_nodes
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from app.agents.learning_unit_generator import StructuredResourceGateway
from app.core.config import ProviderSettings
from app.core.provider_target import ApprovedTarget
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.learning_contract import LearningContractError
from app.services.learning_stage_gateway import (
    GENERATION_STAGES,
    REVIEW_STAGES,
    LearningStageGateway,
)
from app.services.provider_gateway import (
    OutputFailureReason,
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
)

PLAN_PROJECTION = "plan-check-string-types-reachable-defs-v1"
CONFIG = dict(
    generation=dict(
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        reasoning="none",
        transport="responses_json_schema",
    ),
    review=dict(
        base_url="https://www.cbbb.fun/v1",
        model="gpt-6-luna",
        reasoning="high",
        transport="responses_json_schema",
    ),
    review_output=8192,
    per_call_seconds=60,
)


def projected_schema(schema, stage):
    if stage in ("resource_review", "unit_review"):
        return projection(schema)
    if stage not in ("plan_check", "plan_recheck") or schema.get("$ref") != "#/$defs/model_result":
        raise ValueError("UNKNOWN_REVIEW_CONTRACT")
    if set(schema) != {"$ref", "$defs"}:
        raise ValueError("PLAN_WRAPPER_CONSTRAINT_CHANGED")
    Draft202012Validator.check_schema(schema)
    source = deepcopy(schema)
    defs = source["$defs"]
    wire = deepcopy(defs["model_result"])
    if wire.get("properties", {}).get("schema_version") != {"const": "plan-review-result-v1"}:
        raise ValueError("PLAN_SCHEMA_CHANGED")
    needed = set()

    def refs(value):
        for _, node in schema_nodes(value):
            if "$ref" in node:
                ref = node["$ref"]
                if not ref.startswith("#/$defs/") or "/" in ref[8:] or ref[8:] not in defs:
                    raise ValueError("UNSUPPORTED_REFERENCE")
                needed.add(ref[8:])

    refs(wire)
    kept = {}
    while needed - kept.keys():
        name = sorted(needed - kept.keys())[0]
        kept[name] = deepcopy(defs[name])
        refs(kept[name])
    if kept:
        wire["$defs"] = kept
    added = []
    for path, node in schema_nodes(wire):
        if "type" not in node and ("const" in node or "enum" in node):
            values = [node["const"]] if "const" in node else node["enum"]
            if not values or not all(isinstance(v, str) for v in values):
                raise ValueError("NON_STRING_ENUM")
            node["type"] = "string"
            added.append(list(path))
    Draft202012Validator.check_schema(wire)
    return wire, dict(
        profile=PLAN_PROJECTION,
        added_string_type_paths=added,
        retained_definitions=sorted(kept),
        pruned_definitions=sorted(set(defs) - set(kept) - {"model_result"}),
        removed_reachable_constraints=[],
    )


class CandidateReviewAdapter(DeepSeekResponsesAdapter):
    async def generate_structured(self, request):
        original = deepcopy(dict(request.json_schema))
        wire, _ = projected_schema(original, request.stage)
        result = await super().generate_structured(replace(request, json_schema=wire))
        try:
            Draft202012Validator(original).validate(dict(result.value))
        except ValidationError as exc:
            safe = {
                "type",
                "required",
                "additionalProperties",
                "const",
                "enum",
                "minLength",
                "maxLength",
                "minItems",
                "maxItems",
                "uniqueItems",
                "pattern",
            }
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.STRUCTURED_SCHEMA_MISMATCH,
                schema_keyword=exc.validator if exc.validator in safe else "other",
                usage=result.usage,
            ) from None
        return result


class LaneGateway:
    def __init__(self, gateway: StructuredResourceGateway, lane: str):
        if lane not in ("fixed_review", "plan_review", "generation_draft"):
            raise ValueError("UNKNOWN_LANE")
        self.gateway, self.lane, self.calls = gateway, lane, 0

    async def generate_structured(self, request, *, retry_safe=False):
        allowed = {
            "fixed_review": {"unit_review"},
            "plan_review": {"plan_check"},
            "generation_draft": {"plan_generation", "resource_generation"},
        }[self.lane]
        if (
            retry_safe
            or request.stage not in allowed
            or self.calls >= (4 if self.lane == "generation_draft" else 1)
        ):
            raise LearningContractError("DIAGNOSTIC_LANE_OR_QUOTA_VIOLATION")
        self.calls += 1
        return await self.gateway.generate_structured(request, retry_safe=False)


class CandidateGateway:
    """Validate exact selected model, output limit, usage and content-free transport audit."""

    def __init__(self, gateway):
        self.gateway = gateway

    async def generate_structured(self, request, *, retry_safe=False):
        if retry_safe or request.stage not in GENERATION_STAGES | REVIEW_STAGES:
            raise LearningContractError("DIAGNOSTIC_ROUTE_CHANGED")
        role = "review" if request.stage in REVIEW_STAGES else "generation"
        caps = {
            "goal_mapping": 512,
            "plan_generation": 2048,
            "plan_rebuild": 2048,
            "resource_generation": 4096,
            "resource_correction": 4096,
        }
        expected = 8192 if role == "review" else caps[request.stage]
        if request.prompt.max_output_tokens != expected:
            raise LearningContractError("DIAGNOSTIC_OUTPUT_LIMIT_CHANGED")
        async with asyncio.timeout(CONFIG["per_call_seconds"]):
            result = await self.gateway.generate_structured(request, retry_safe=False)
        usage = result.usage
        audit = result.transport_audit
        if (
            result.model_id != CONFIG[role]["model"]
            or usage is None
            or type(usage.input_tokens) is not int
            or type(usage.output_tokens) is not int
            or usage.input_tokens < 0
            or not 0 <= usage.output_tokens <= expected
        ):
            raise LearningContractError("DIAGNOSTIC_MODEL_OR_USAGE_CHANGED")
        if audit is None or any(
            not re.fullmatch(r"[0-9a-f]{64}", getattr(audit, key))
            for key in ("request_digest", "response_digest", "config_digest")
        ):
            raise LearningContractError("DIAGNOSTIC_AUDIT_REQUIRED")
        return result


def offline_router(values):
    """Actual adapter capture only; no alternate live path, dotenv, keys or DNS."""
    wires = []
    queue = list(values)

    def adapter(role, cls):
        cfg = CONFIG[role]
        base = cfg["base_url"]
        host = urlsplit(base).hostname
        guard = SimpleNamespace(approve_base=lambda: ApprovedTarget(base, host, 443, ("8.8.8.8",)))

        def reply(request):
            value = queue.pop(0)
            wires.append(
                dict(
                    role=role,
                    url=str(request.url),
                    host=request.headers["host"],
                    sni=request.extensions.get("sni_hostname"),
                    body=json.loads(request.content),
                )
            )
            return httpx.Response(
                200,
                json=dict(
                    model=cfg["model"],
                    status="completed",
                    output=[
                        dict(
                            type="message",
                            role="assistant",
                            status="completed",
                            content=[dict(type="output_text", text=json.dumps(value))],
                        )
                    ],
                    usage=dict(input_tokens=100, output_tokens=100),
                ),
            )

        return ProviderGateway(
            cls(
                ProviderSettings(base, "OFFLINE_PLACEHOLDER", cfg["model"]),
                guard,
                transport=httpx.MockTransport(reply),
                reasoning_effort=cfg["reasoning"],
            )
        )

    return CandidateGateway(
        LearningStageGateway(
            adapter("generation", DeepSeekResponsesAdapter),
            adapter("review", CandidateReviewAdapter),
        )
    ), wires
