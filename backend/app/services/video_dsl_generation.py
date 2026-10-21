"""Select reviewed cache -> applicable template -> bounded DSL -> explicit same-goal fallback.

Internal planning only: no public API, render, publication, or dynamic-opening authority.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Literal

from app.agents.animation_dsl_generation import AnimationDSLGenerator
from app.agents.animation_dsl_review import DSLReference, DSLReviewOutcome, canonical, digest
from app.core.product_mode import catalog_only
from app.services.animation_cache import AnimationCache, CachedAnimation
from app.services.animation_dsl_candidate_cache import ReviewedDSLCandidateCache
from app.services.animation_intent import VideoIntent
from app.services.animation_templates import (
    TemplateValidationError,
    load_template,
    normalize_parameters,
)


@dataclass(frozen=True, slots=True)
class VideoPlan:
    source: Literal[
        "reviewed_cache",
        "parameterized_template",
        "generated_dsl",
        "reviewed_dsl_cache",
        "template_fallback",
        "unavailable",
    ]
    intent_sha256: str
    template_id: str | None = None
    template_version: str | None = None
    parameters_json: str | None = field(default=None, repr=False)
    media: CachedAnimation | None = field(default=None, repr=False)
    outcome: DSLReviewOutcome | None = field(default=None, repr=False)
    error_code: str | None = None
    candidates: int = 0
    omitted_presentation: str | None = None


def _template(intent: VideoIntent) -> tuple[str, str, str] | None:
    template_id = {"insert": "linked-list-insertion", "delete": "linked-list-deletion"}.get(
        intent.operation
    )
    if template_id is None or intent.knowledge_point_id != template_id:
        return None
    try:
        spec = load_template(template_id, require_executable=True)
        parameters = normalize_parameters(spec, json.loads(intent.parameters_json))
        return spec.template_id, spec.template_version, canonical(parameters)
    except (TemplateValidationError, ValueError, OSError):
        return None


class VideoDSLPlanner:
    def __init__(
        self,
        generator: AnimationDSLGenerator,
        *,
        cache: AnimationCache | None = None,
        reviewed_cache: ReviewedDSLCandidateCache | None = None,
    ):
        self.generator, self.cache = generator, cache
        self.reviewed_cache = reviewed_cache

    async def plan(
        self, intent: VideoIntent, *, reference: DSLReference, dynamic_allowed: bool = False
    ) -> VideoPlan:
        try:
            payload = intent.payload()
            reference.payload()
            if intent.knowledge_point_id != reference.knowledge_point_id:
                raise ValueError()
            key = digest({"intent": payload, "reference": reference.sha256})
        except (ValueError, TypeError, KeyError, UnicodeError):
            return VideoPlan(
                "unavailable", digest("invalid-intent"), error_code="DSL_INTENT_INVALID"
            )
        if dynamic_allowed is True and not catalog_only() and self.reviewed_cache is not None:
            cached = await self.reviewed_cache.lookup(intent, reference)
            if cached is not None:
                return VideoPlan("reviewed_dsl_cache", key, outcome=cached)
        template = _template(intent)
        if template is not None and intent.presentation == "standard":
            tid, version, params = template
            if self.cache is not None:
                try:
                    hit = await asyncio.to_thread(self.cache.lookup, tid, json.loads(params))
                    if hit is not None and await asyncio.to_thread(
                        self.cache.validate, hit, json.loads(params)
                    ):
                        return VideoPlan("reviewed_cache", key, tid, version, params, hit)
                except (TemplateValidationError, ValueError, OSError):
                    pass  # Corrupt bytes are not a hit; the same-goal template is eligible.
            return VideoPlan("parameterized_template", key, tid, version, params)
        # Detailed trace is optional presentation; fallback retains the operation and inputs.
        if dynamic_allowed is not True or catalog_only():
            error, candidates = "DSL_GENERATION_UNAVAILABLE", 0
        else:
            result = await self.generator.generate(reference=reference, intent=payload)
            if result.outcome is not None:
                return VideoPlan(
                    "generated_dsl", key, outcome=result.outcome, candidates=result.candidates
                )
            error, candidates = result.error_code or "DSL_GENERATION_UNAVAILABLE", result.candidates
        template = _template(
            intent
        )  # Fresh review/source check; old applicability is not authority.
        if template is not None:
            tid, version, params = template
            return VideoPlan(
                "template_fallback",
                key,
                tid,
                version,
                params,
                error_code=error,
                candidates=candidates,
                omitted_presentation=intent.presentation,
            )
        return VideoPlan("unavailable", key, error_code=error, candidates=candidates)
