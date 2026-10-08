"""Bounded quality-tier generation; corrections never bypass independent local review."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from app.agents.animation_dsl_review import (
    AnimationDSLReviewAgent,
    DSLReference,
    DSLReviewOutcome,
    GenerationSource,
    ModelSource,
    canonical,
    digest,
)
from app.core.credential_crypto import CredentialFailure
from app.services.animation_dsl_compiler import DSLCompileError
from app.services.animation_dsl_validation import CONTRACT, DSLValidationError
from app.services.animation_intent import intent_from_payload
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    StructuredRequest,
    TaskProfile,
    TextRequest,
)

_DIRECTORY = Path(__file__).resolve().parents[3] / "data/animation_dsl/generate-v1"
_PROMPT = (_DIRECTORY / "prompt.md").read_bytes()
_SCHEMA = (CONTRACT / "schema.json").read_bytes()
_POLICY = (CONTRACT / "policy.json").read_bytes()
PROMPT_SHA256 = hashlib.sha256(_PROMPT).hexdigest()
GENERATOR_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
INSTRUCTIONS = _PROMPT.decode().split("```text\n", 1)[1].split("\n```", 1)[0]
SAMPLING = {
    "task_profile": "quality",
    "max_output_tokens": 8192,
    "temperature": 0.0,
    "request_timeout_seconds": 60,
    "operation_timeout_seconds": 180,
    "max_corrections": 2,
    "retry_safe": False,
}


@dataclass(frozen=True, slots=True)
class GenerationCall:
    raw: bytes = field(repr=False)
    source: ModelSource


class DSLGenerationGateway(Protocol):
    async def generate_candidate(self, request: StructuredRequest) -> GenerationCall: ...


@dataclass(frozen=True, slots=True)
class GenerationResult:
    outcome: DSLReviewOutcome | None = field(default=None, repr=False)
    error_code: str | None = None
    candidates: int = 0


class AnimationDSLGenerator:
    def __init__(self, gateway: DSLGenerationGateway, reviewer: AnimationDSLReviewAgent):
        self.gateway, self.reviewer = gateway, reviewer

    async def generate(
        self, *, reference: DSLReference, intent: dict[str, object]
    ) -> GenerationResult:
        candidates = 0
        try:
            # Re-read every invocation. A changed file cannot silently inherit an old prompt hash.
            if (
                (_DIRECTORY / "prompt.md").read_bytes() != _PROMPT
                or (CONTRACT / "schema.json").read_bytes() != _SCHEMA
                or (CONTRACT / "policy.json").read_bytes() != _POLICY
                or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != GENERATOR_SHA256
            ):
                return GenerationResult(error_code="DSL_GENERATION_UNAVAILABLE")
            ref = reference.payload()
            checked_intent = intent_from_payload(intent)
            if checked_intent.knowledge_point_id != reference.knowledge_point_id:
                return GenerationResult(error_code="DSL_INTENT_INVALID")
            frozen_intent = checked_intent.payload()
            previous = None
            initial_source = None
            async with asyncio.timeout(180):
                for attempt in range(3):
                    payload = {
                        "reference": ref,
                        "intent": frozen_intent,
                        "schema": json.loads(_SCHEMA),
                        "policy": json.loads(_POLICY),
                    }
                    if previous is not None:
                        payload["correction"] = {
                            "candidate": previous.compiled.validated.candidate,
                            "issues": [asdict(i) for i in previous.issues],
                        }
                    request = StructuredRequest(
                        TextRequest(
                            (
                                ChatMessage("system", INSTRUCTIONS),
                                ChatMessage("user", canonical(payload)),
                            ),
                            task_profile=TaskProfile.QUALITY,
                            max_output_tokens=8192,
                            temperature=0.0,
                        ),
                        json.loads(_SCHEMA),
                    )
                    async with asyncio.timeout(60):
                        call = await self.gateway.generate_candidate(request)
                    candidates += 1
                    if initial_source is None:
                        initial_source = call.source
                    elif call.source != initial_source:
                        return GenerationResult(
                            error_code="DSL_TARGET_CHANGED", candidates=candidates
                        )
                    source = GenerationSource(
                        call.source,
                        digest(
                            {
                                "prompt": PROMPT_SHA256,
                                "schema": hashlib.sha256(_SCHEMA).hexdigest(),
                                "policy": hashlib.sha256(_POLICY).hexdigest(),
                                "input": request.prompt.messages[1].content,
                                "generator": GENERATOR_SHA256,
                            }
                        ),
                        digest(SAMPLING),
                    )
                    # Review freshly validates, compiles and sends complete trusted frames.
                    outcome = await self.reviewer.review(
                        call.raw,
                        reference=reference,
                        generation_source=source,
                        animation_intent=frozen_intent,
                    )
                    if outcome.approved:
                        return GenerationResult(outcome, candidates=candidates)
                    if outcome.verdict == "unavailable":
                        return GenerationResult(
                            error_code="DSL_REVIEW_UNAVAILABLE", candidates=candidates
                        )
                    if outcome.verdict == "reject" or attempt == 2:
                        return GenerationResult(
                            error_code="DSL_REVIEW_REJECTED", candidates=candidates
                        )
                    previous = (
                        outcome  # Only strict, sanitized revise issues can reach a correction.
                    )
        except DSLValidationError as error:
            return GenerationResult(error_code=error.code, candidates=candidates)
        except DSLCompileError as error:
            code = str(error)
            return GenerationResult(
                error_code=code
                if code in {"DSL_COMPILE_REJECTED", "DSL_COMPILE_UNAVAILABLE", "DSL_RESOURCE_LIMIT"}
                else "DSL_COMPILE_UNAVAILABLE",
                candidates=candidates,
            )
        except (
            CredentialFailure,
            ProviderError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            TimeoutError,
        ):
            return GenerationResult(error_code="DSL_GENERATION_UNAVAILABLE", candidates=candidates)
        return GenerationResult(error_code="DSL_GENERATION_UNAVAILABLE", candidates=candidates)
