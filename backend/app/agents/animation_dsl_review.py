"""Independent review of a locally compiled candidate; never execute generated code."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol, cast

from jsonschema import Draft202012Validator, validators  # type: ignore[import-untyped]

from app.core.credential_crypto import CredentialFailure
from app.services.animation_dsl_compiler import CompiledDSL, compile_animation_dsl
from app.services.animation_intent import intent_from_payload
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    StructuredRequest,
    StructuredResult,
    TaskProfile,
    TextRequest,
)

DIRECTORY = Path(__file__).resolve().parents[3] / "data/animation_dsl/review-v1"
_PROMPT = (DIRECTORY / "prompt.md").read_bytes()
_SCHEMA = (DIRECTORY / "schema.json").read_bytes()
PROMPT_SHA256 = hashlib.sha256(_PROMPT).hexdigest()
REVIEW_SCHEMA_SHA256 = hashlib.sha256(_SCHEMA).hexdigest()
REVIEW_VERSION = "animation-dsl-review-v1"
REVIEWER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
INSTRUCTIONS = _PROMPT.decode().split("```text\n", 1)[1].split("\n```", 1)[0]
_VALIDATOR = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda checker, value: type(value) is int
    ),
)(json.loads(_SCHEMA))
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@+/-]{0,159}")
_HASH = re.compile(r"[0-9a-f]{64}")
_UNSAFE = re.compile(
    r"https?://|(?:^|\s)/(?:Users|home|tmp|etc|var)/|[A-Za-z]:\\|"
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b(?:sk-[A-Za-z0-9_-]+|Bearer\s+\S+|"
    r"api[_ -]?key\s*[:=]|Cookie\s*:)",
    re.I,
)


def canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ModelSource:
    """Gateway/composition-root evidence, never fields supplied by generated JSON."""

    provider_type: str
    model_id: str
    adapter_version: str
    capability_version: str
    target_sha256: str
    model_revision: str = "unknown"

    def __post_init__(self) -> None:
        if self.provider_type not in {
            "openai-compatible",
            "ollama",
            "anthropic",
            "gemini",
            "spark",
        }:
            raise ValueError("DSL_SOURCE_INVALID")
        for value in (
            self.model_id,
            self.adapter_version,
            self.capability_version,
            self.model_revision,
        ):
            if type(value) is not str or not _TOKEN.fullmatch(value) or _UNSAFE.search(value):
                raise ValueError("DSL_SOURCE_INVALID")
        if type(self.target_sha256) is not str or not _HASH.fullmatch(self.target_sha256):
            raise ValueError("DSL_SOURCE_INVALID")


@dataclass(frozen=True, slots=True)
class GenerationSource:
    source: ModelSource
    prompt_sha256: str
    sampling_sha256: str

    def __post_init__(self) -> None:
        if any(
            type(v) is not str or not _HASH.fullmatch(v)
            for v in (self.prompt_sha256, self.sampling_sha256)
        ):
            raise ValueError("DSL_SOURCE_INVALID")


@dataclass(frozen=True, slots=True)
class ReviewCall:
    result: StructuredResult = field(repr=False)
    source: ModelSource


class DSLReviewGateway(Protocol):
    """A server-selected review route with authorization and actual Gateway attribution."""

    async def review_structured(self, request: StructuredRequest) -> ReviewCall: ...


@dataclass(frozen=True, slots=True)
class DSLReference:
    """Constructed by the server from approved target/graph, not arbitrary API JSON."""

    serialized: str = field(repr=False)
    target_sha256: str
    graph_sha256: str
    knowledge_point_id: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.serialized.encode()).hexdigest()

    def payload(self) -> dict[str, object]:
        if (
            len(self.serialized.encode()) > 8192
            or not self.serialized
            or not _HASH.fullmatch(self.target_sha256)
            or not _HASH.fullmatch(self.graph_sha256)
        ):
            raise ValueError("DSL_REVIEW_UNAVAILABLE")
        value = json.loads(self.serialized)
        if type(value) is not dict or value.get("context_version") != "animation-dsl-reference-v1":
            raise ValueError("DSL_REVIEW_UNAVAILABLE")
        if (
            set(value)
            != {
                "context_version",
                "target",
                "graph_version",
                "node",
                "prerequisites",
                "known_profile",
            }
            or type(value["target"]) is not dict
            or digest(value["target"]) != self.target_sha256
            or type(value["node"]) is not dict
            or value["node"].get("id") != self.knowledge_point_id
            or not value["node"].get("description")
            or not value["node"].get("learning_objectives")
            or type(value["prerequisites"]) is not list
            or not value["graph_version"]
            or value["known_profile"] != {}
        ):
            raise ValueError("DSL_REVIEW_UNAVAILABLE")
        return value


@dataclass(frozen=True, slots=True)
class DSLIssue:
    area: str
    severity: str
    action_index: int | None
    message: str


@dataclass(frozen=True, slots=True)
class DSLReviewOutcome:
    compiled: CompiledDSL = field(repr=False)
    reference: DSLReference = field(repr=False)
    generation_source: GenerationSource
    review_source: ModelSource | None
    verdict: str
    issues: tuple[DSLIssue, ...]
    binding_sha256: str
    review_sha256: str
    error_code: str | None = None
    animation_intent_json: str | None = field(default=None, repr=False)

    @property
    def approved(self) -> bool:
        return self.verdict == "pass" and self.error_code is None


def binding(
    compiled: CompiledDSL,
    reference: DSLReference,
    generation: GenerationSource,
    animation_intent_json: str | None = None,
) -> str:
    return digest(
        {
            "animation_intent": animation_intent_json,
            "compiled": compiled.identity_sha256,
            "reference": reference.sha256,
            "target": reference.target_sha256,
            "graph": reference.graph_sha256,
            "generation": asdict(generation),
            "prompt": PROMPT_SHA256,
            "review_schema": REVIEW_SCHEMA_SHA256,
            "reviewer": REVIEWER_SHA256,
        }
    )


def strict_issues(value: object, *, actions: int) -> tuple[str, tuple[DSLIssue, ...]]:
    if type(value) is not dict or not _VALIDATOR.is_valid(value):
        raise ValueError("DSL_REVIEW_UNAVAILABLE")
    issues = []
    for item in value["issues"]:
        index, message = item["action_index"], item["message"]
        if (
            index is not None
            and (type(index) is not int or not 0 <= index < actions)
            or not message.strip()
            or unicodedata.normalize("NFC", message) != message
            or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in message)
            or _UNSAFE.search(message)
        ):
            raise ValueError("DSL_REVIEW_UNAVAILABLE")
        issues.append(DSLIssue(**item))
    return value["verdict"], tuple(issues)


class AnimationDSLReviewAgent:
    def __init__(self, gateway: DSLReviewGateway) -> None:
        self.gateway = gateway

    async def review(
        self,
        raw: bytes | str,
        *,
        reference: DSLReference,
        generation_source: GenerationSource,
        animation_intent: dict[str, object] | None = None,
    ) -> DSLReviewOutcome:
        # Fresh local checks. No caller-supplied frames, Python, or earlier pass is accepted.
        compiled = await asyncio.to_thread(
            compile_animation_dsl, raw, knowledge_point_id=reference.knowledge_point_id
        )
        bound = binding(compiled, reference, generation_source)
        source = None
        intent_json = None
        try:
            payload = reference.payload()
            if (
                (DIRECTORY / "prompt.md").read_bytes() != _PROMPT
                or (DIRECTORY / "schema.json").read_bytes() != _SCHEMA
                or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != REVIEWER_SHA256
            ):
                raise ValueError("DSL_REVIEW_UNAVAILABLE")
            review_payload = {
                "dsl": compiled.validated.candidate,
                "frames": json.loads(compiled.validated.trace_json),
                "reference": payload,
            }
            if animation_intent is not None:
                intent = intent_from_payload(animation_intent)
                if intent.knowledge_point_id != reference.knowledge_point_id:
                    raise ValueError("DSL_REVIEW_UNAVAILABLE")
                review_payload["intent"] = intent.payload()
                intent_json = canonical(intent.payload())
                bound = binding(compiled, reference, generation_source, intent_json)
            request = StructuredRequest(
                TextRequest(
                    (
                        ChatMessage("system", INSTRUCTIONS),
                        ChatMessage(
                            "user",
                            canonical(review_payload),
                        ),
                    ),
                    task_profile=TaskProfile.REVIEW,
                    max_output_tokens=4096,
                ),
                json.loads(_SCHEMA),
            )
            async with asyncio.timeout(60):
                call = await self.gateway.review_structured(request)
            if call.result.model_id != call.source.model_id:
                raise ValueError("DSL_REVIEW_UNAVAILABLE")
            source = call.source
            verdict, issues = strict_issues(
                dict(call.result.value), actions=len(compiled.validated.frames)
            )
            # Reject untrusted echoes rather than feeding private captions back into correction.
            texts = [cast(str, compiled.validated.candidate["title"])]
            texts.extend(frame.caption for frame in compiled.validated.frames)
            if any(len(text) >= 20 and text in issue.message for text in texts for issue in issues):
                raise ValueError("DSL_REVIEW_UNAVAILABLE")
        except (
            CredentialFailure,
            ProviderError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            TimeoutError,
        ):
            verdict, issues = "unavailable", ()
        review_hash = digest(
            {
                "binding": bound,
                "verdict": verdict,
                "issues": [asdict(i) for i in issues],
                "source": asdict(source) if source else None,
            }
        )
        return DSLReviewOutcome(
            compiled,
            reference,
            generation_source,
            source,
            verdict,
            issues,
            bound,
            review_hash,
            "DSL_REVIEW_UNAVAILABLE" if verdict == "unavailable" else None,
            animation_intent_json=intent_json,
        )
