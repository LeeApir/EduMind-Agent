"""Apply minimal learning-behavior summaries after their evidence is committed."""

import hashlib
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.profile_agent import ProfileAgent, StructuredProfileGateway
from app.agents.profile_schema import (
    ProfileSchemaError,
    merge_explicit_profile_values,
    merge_profile_snapshots,
)
from app.core.product_mode import catalog_only
from app.core.provider_factory import build_default_provider_gateway
from app.models.learning import ProfileEvent, StudentProfile
from app.models.learning_state import LearningEvidence
from app.services.owned_learning import latest_profile
from app.services.profile_updates import (
    ProfileVersionConflict,
    persist_profile_version,
    snapshot_profile,
)
from app.services.provider_gateway import ProviderError


def profile_behavior_gateway_factory() -> Callable[[], StructuredProfileGateway]:
    """Defer Provider construction until after evidence has committed."""
    return build_default_provider_gateway


def learning_evidence_summary(record: LearningEvidence) -> dict[str, object] | None:
    """Never forward raw answers, question text, hint text, or prior profile fields."""
    summary: dict[str, object] = {
        "event_type": record.evidence_type,
        "knowledge_node_id": record.knowledge_node_id,
    }
    if record.evidence_type == "quiz_attempt":
        results = record.payload.get("question_results")
        score = record.payload.get("score")
        if not isinstance(results, list) or not isinstance(score, (int, float)):
            return None
        patterns: set[str] = set()
        for item in results:
            if not isinstance(item, dict):
                return None
            value = item.get("error_patterns")
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                return None
            patterns.update(value)
        summary["score"] = score
        summary["error_patterns"] = sorted(patterns)
    elif record.evidence_type in {"hint_used", "reexplanation_requested", "explicit_feedback"}:
        action = record.payload.get("action")
        if not isinstance(action, str):
            return None
        summary["action"] = action
    else:
        return None
    return summary


def resource_event_summary(record: ProfileEvent) -> dict[str, object] | None:
    """Resource selection is a preference signal, never mastery evidence."""
    if record.event_type != "resource_selected" or record.action not in {"code", "exercise"}:
        return None
    return {
        "event_type": "resource_selected",
        "knowledge_node_id": record.knowledge_node_id,
        "action": record.action,
    }


def _allowed_fields(summary: dict[str, object]) -> tuple[str, ...]:
    if summary["event_type"] == "resource_selected":
        return ("engineering_preference",)
    return ("error_preferences",)


async def update_profile_from_summary(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    owner_id: UUID,
    evidence_id: UUID,
    observed_at: datetime,
    summary: dict[str, object] | None,
    gateway_factory: Callable[[], StructuredProfileGateway],
) -> str:
    """Never put Provider I/O in the evidence transaction or invent unknown fields."""
    if catalog_only():
        return "no_change"
    if summary is None:
        return "no_change"
    key = f"profile-evidence-{evidence_id}"
    async with session_factory() as db:
        previous = await latest_profile(db, owner_id)
        existing = await db.scalar(
            select(StudentProfile).where(
                StudentProfile.user_id == owner_id,
                StudentProfile.idempotency_key == key,
            )
        )
    if existing is not None:
        return "updated"
    if previous is None or not previous.initial_query:
        return "no_change"
    try:
        gateway = gateway_factory()
        proposal = await ProfileAgent(gateway).update_from_behavior(
            summary, allowed_fields=_allowed_fields(summary)
        )
    except ProviderError:
        return "provider_failed"
    if proposal.degraded:
        return "provider_failed"
    if not proposal.updates:
        return "no_change"

    source = (
        "explicit_feedback" if summary["event_type"] == "explicit_feedback" else "learning_behavior"
    )
    confidence = 0.9 if source == "explicit_feedback" else 0.7
    digest = hashlib.sha256(str(evidence_id).encode()).hexdigest()
    for _ in range(3):
        async with session_factory() as db:
            existing = await db.scalar(
                select(StudentProfile).where(
                    StudentProfile.user_id == owner_id,
                    StudentProfile.idempotency_key == key,
                )
            )
            if existing is not None:
                return "updated"
            latest = await latest_profile(db, owner_id)
            if latest is None or not latest.initial_query:
                return "no_change"
            next_version = latest.version + 1
            evidence = {
                field: [
                    {
                        "source": source,
                        "confidence": confidence,
                        "observed_at": observed_at.isoformat(),
                        "profile_version": next_version,
                    }
                ]
                for field in proposal.updates
            }
            try:
                candidate = merge_explicit_profile_values(
                    latest.initial_query,
                    proposal.updates,
                    evidence,
                    profile_version=next_version,
                )
                merged = merge_profile_snapshots(snapshot_profile(latest), candidate)
                await persist_profile_version(
                    db,
                    owner_id=owner_id,
                    profile=merged,
                    idempotency_key=key,
                    request_digest=digest,
                )
            except ProfileSchemaError:
                return "provider_failed"
            except ProfileVersionConflict:
                continue
            return "updated"
    return "conflict"
