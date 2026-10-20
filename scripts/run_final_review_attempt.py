"""Actual high-only attempt; credentials remain in existing private env, not global rerouting."""

# ruff: noqa: E402
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_high_candidate import CONFIG
from acceptance_support.luna_review_routing import ExplicitRouter
from acceptance_support.luna_schema_projection import ProjectedReviewAdapter
from acceptance_support.qwen_review_budget import canonical, sha
from acceptance_support.luna_admission_gate import require
from app.agents.hybrid_resource_review import review_once
from app.agents.shared_learning_plan import CallWindow
from app.core.config import ProviderSettings
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from prepare_luna_admission import candidates
from run_luna_admission import (
    credential,
    ExactTransport,
    LunaAttemptFailure,
    safe_failure,
)


async def perform(root, manifest, case, wire, checked_authorize):
    # Existing env still says low; it selects/validates the same connection only.
    # New explicit authority selects high here; never modifies the global env/factory.
    CONFIG.check()
    key = credential(root, manifest)
    target = await asyncio.to_thread(
        ProviderTargetGuard(CONFIG.review_base, TargetPolicy()).approve_base
    )
    audit = ExactTransport(wire, target, checked_authorize)
    adapter = ProjectedReviewAdapter(
        ProviderSettings(CONFIG.review_base, key, CONFIG.review_model),
        SimpleNamespace(approve_base=lambda: target),
        transport=audit,
        reasoning_effort=CONFIG.review_reasoning,
    )

    class NoGeneration:
        async def generate_structured(self, request):
            raise ValueError("GENERATION_FORBIDDEN")

    router = ExplicitRouter(NoGeneration(), adapter, config=CONFIG)
    material = case["material"]
    started = time.monotonic()
    try:
        record = await review_once(
            router,
            CallWindow(),
            binding=material["binding"],
            target_digest=material["unit_digest"],
            payload={
                "unit": material,
                "reference_context": material["reference_context"],
            },
            candidates=candidates(case),
            scope="unit",
            input_snapshot=case["input_snapshot"],
        )
        require(
            audit.sent == 1
            and audit.raw_complete
            and record["request_digest"] == sha(wire),
            "AUDIT_MISMATCH",
        )
        require(key not in canonical(record).decode(), "SECRET_REFLECTION")
        return dict(
            record=record,
            sent=audit.sent,
            http_status=audit.status,
            raw_response_sha256=audit.raw_hash.hexdigest(),
            raw_bytes=audit.raw_bytes,
            raw_complete=audit.raw_complete,
            model=CONFIG.review_model,
            input_tokens=router.last_usage.input_tokens,
            output_tokens=router.last_usage.output_tokens,
            duration_ms=round((time.monotonic() - started) * 1000),
            requested_reasoning="high",
            provider_effective_reasoning="unknown unless provider supplies independently trustworthy metadata",
        )
    except BaseException as exc:
        usage = getattr(exc, "usage", None) or router.last_usage
        raise LunaAttemptFailure(
            safe_failure(exc),
            dict(
                http_status=audit.status,
                sent=audit.sent,
                raw_bytes=audit.raw_bytes,
                raw_complete=audit.raw_complete,
                raw_response_sha256=audit.raw_hash.hexdigest(),
                provider_error=audit.error_metadata,
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                output_failure_reason=getattr(
                    getattr(exc, "output_failure_reason", None), "value", None
                ),
                schema_keyword=getattr(exc, "schema_keyword", None),
            ),
        ) from None
    finally:
        async with asyncio.timeout(5):
            await audit.aclose()
