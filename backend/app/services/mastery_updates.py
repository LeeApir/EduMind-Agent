"""Atomically project committed evidence into owner/node mastery revisions."""

from hashlib import sha256
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import utc_now
from app.models.learning_state import (
    LearningEvidence,
    LearningPathCurrent,
    NodeMasteryCurrent,
    NodeMasteryRevision,
)
from app.services.catalog_assessment import mastery_eligible
from app.services.learning_owner_lock import lock_learning_owner
from app.services.mastery_rules import MASTERY_RULE_VERSION, MasteryFact, reduce_mastery


async def lock_mastery_node(db: AsyncSession, *, owner_id: UUID, node_id: str) -> None:
    """Serialize writers for one owner/node before inserting their evidence."""
    await lock_learning_owner(db, owner_id)
    digest = sha256(f"{owner_id}:{node_id}".encode("utf-8")).digest()
    lock_key = int.from_bytes(digest[:8], "big", signed=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


async def apply_mastery_evidence(
    db: AsyncSession, record: LearningEvidence
) -> tuple[dict[str, object] | None, bool]:
    """Rebuild owner facts and write revision, current state, and stale flag atomically."""
    if not mastery_eligible(record.payload):
        return None, False
    await db.flush()
    rows = (
        await db.scalars(
            select(LearningEvidence)
            .where(
                LearningEvidence.user_id == record.user_id,
                LearningEvidence.knowledge_node_id == record.knowledge_node_id,
            )
            .order_by(LearningEvidence.created_at, LearningEvidence.id)
        )
    ).all()
    decision = reduce_mastery([MasteryFact(row.evidence_type, row.payload) for row in rows
                              if mastery_eligible(row.payload)])
    current = await db.scalar(
        select(NodeMasteryCurrent)
        .where(
            NodeMasteryCurrent.user_id == record.user_id,
            NodeMasteryCurrent.knowledge_node_id == record.knowledge_node_id,
        )
        .with_for_update()
    )
    previous_score = current.score if current is not None else 0.0
    change: dict[str, object] | None = None
    if (
        current is None
        or current.score != decision.score
        or current.status != decision.status
        or current.rule_version != MASTERY_RULE_VERSION
    ):
        revision_number = 1 if current is None else current.revision + 1
        revision = NodeMasteryRevision(
            user_id=record.user_id,
            knowledge_node_id=record.knowledge_node_id,
            revision=revision_number,
            previous_score=previous_score,
            score=decision.score,
            status=decision.status,
            rule_version=MASTERY_RULE_VERSION,
            evidence_id=record.id,
            evidence_summary=list(decision.evidence_summary),
        )
        db.add(revision)
        await db.flush()
        if current is None:
            db.add(
                NodeMasteryCurrent(
                    user_id=record.user_id,
                    knowledge_node_id=record.knowledge_node_id,
                    revision_id=revision.id,
                    revision=revision_number,
                    score=decision.score,
                    status=decision.status,
                    rule_version=MASTERY_RULE_VERSION,
                )
            )
        else:
            current.revision_id = revision.id
            current.revision = revision_number
            current.score = decision.score
            current.status = decision.status
            current.rule_version = MASTERY_RULE_VERSION
            current.updated_at = utc_now()
        change = {
            "knowledge_node_id": record.knowledge_node_id,
            "previous_score": previous_score,
            "score": decision.score,
            "status": decision.status,
            "revision": revision_number,
            "rule_version": MASTERY_RULE_VERSION,
            "evidence_summary": list(decision.evidence_summary),
        }

    stale = await db.execute(
        update(LearningPathCurrent)
        .where(LearningPathCurrent.user_id == record.user_id)
        .values(replan_required=True, updated_at=utc_now())
    )
    return change, bool(stale.rowcount)
