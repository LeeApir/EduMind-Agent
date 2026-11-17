"""Private immutable mastery snapshots and minimal, owner-checked provenance references."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.free_course import FreeCourseVersion
from app.models.free_course_answers import FreeCourseAnswerAttempt, FreeCourseExerciseVersion
from app.models.learning import GeneratedResource, LearningUnit
from app.models.learning_state import LearningEvidence, NodeMasteryRevision
from app.services.free_course_contract import validate
from app.services.free_course_snapshots import SnapshotError


async def evidence_ref(
    db: AsyncSession, owner: UUID, node: str, identity: UUID
) -> dict[str, Any] | None:
    row = (
        (
            await db.execute(
                select(
                    LearningEvidence.id,
                    LearningEvidence.source_protocol,
                    LearningEvidence.free_course_attempt_id,
                    LearningEvidence.corrects_evidence_id,
                    LearningEvidence.resource_id,
                    LearningEvidence.resource_version,
                    LearningEvidence.learning_unit_id,
                ).where(
                    LearningEvidence.id == identity,
                    LearningEvidence.user_id == owner,
                    LearningEvidence.knowledge_node_id == node,
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None


async def attempt_ref(db: AsyncSession, owner: UUID, identity: UUID) -> dict[str, Any] | None:
    attempt = FreeCourseAnswerAttempt
    exercise = FreeCourseExerciseVersion
    version = FreeCourseVersion
    row = (
        await db.execute(
            select(
                attempt.id,
                attempt.course_id,
                attempt.binding_json,
                attempt.exercise_version_id,
                exercise.exercise_id,
                exercise.scene_version_id,
                version.version,
                version.manifest_json,
            )
            .join(
                exercise,
                (exercise.id == attempt.exercise_version_id)
                & (exercise.user_id == owner)
                & (exercise.course_id == attempt.course_id),
            )
            .join(
                version,
                (version.id == attempt.course_version_id)
                & (version.user_id == owner)
                & (version.course_id == attempt.course_id),
            )
            .where(attempt.id == identity, attempt.user_id == owner)
        )
    ).one_or_none()
    if row is None:
        return None
    binding = row.binding_json
    if (
        not isinstance(binding, dict)
        or binding.get("course_version") != row.version
        or binding.get("scene_version_id") != str(row.scene_version_id)
        or not any(
            isinstance(item, dict)
            and item.get("scene_id") == binding.get("scene_id")
            and item.get("scene_version_id") == binding.get("scene_version_id")
            for item in row.manifest_json.get("scenes", [])
        )
    ):
        return None
    value = dict(
        kind="free_course_attempt",
        course_id=str(row.course_id),
        course_version=row.version,
        scene_id=binding.get("scene_id"),
        scene_version_id=str(row.scene_version_id),
        exercise_id=str(row.exercise_id),
        exercise_version_id=str(row.exercise_version_id),
        attempt_id=str(row.id),
    )
    try:
        validate("FreeAttemptRef", value)
    except SnapshotError:
        return None
    return value


async def source_ref(db: AsyncSession, owner: UUID, node: str, identity: UUID) -> dict[str, Any]:
    source = await evidence_ref(db, owner, node, identity)
    closed = dict(
        protocol="unavailable", evidence_id=str(identity) if source else None, reference=None
    )
    if source is None:
        return closed
    protocol = source["source_protocol"]
    original = source
    if protocol == "free-course-correction-v1":
        if source["corrects_evidence_id"] is None:
            return closed
        prior = await evidence_ref(db, owner, node, source["corrects_evidence_id"])
        if prior is None or prior["source_protocol"] != "free-course-v1":
            return closed
        original = prior
    if protocol in {"free-course-v1", "free-course-correction-v1"}:
        if original["free_course_attempt_id"] is None:
            return closed
        reference = await attempt_ref(db, owner, original["free_course_attempt_id"])
        return (
            dict(protocol=protocol, evidence_id=str(identity), reference=reference)
            if reference
            else closed
        )
    if protocol is not None:
        return closed
    if source["learning_unit_id"] is not None:
        owned_unit = await db.scalar(
            select(LearningUnit.id).where(
                LearningUnit.id == source["learning_unit_id"], LearningUnit.user_id == owner
            )
        )
        if owned_unit is None:
            return closed
    if source["resource_id"] is not None:
        query = select(GeneratedResource.id).where(
            GeneratedResource.id == source["resource_id"], GeneratedResource.user_id == owner
        )
        if source["learning_unit_id"] is not None:
            query = query.where(GeneratedResource.learning_unit_id == source["learning_unit_id"])
        if source["resource_version"] is not None:
            query = query.where(GeneratedResource.version == source["resource_version"])
        if await db.scalar(query) is None:
            return closed
    return dict(
        protocol="legacy",
        evidence_id=str(identity),
        reference=dict(
            kind="legacy_evidence",
            resource_id=str(source["resource_id"]) if source["resource_id"] else None,
            resource_version=source["resource_version"],
            learning_unit_id=str(source["learning_unit_id"])
            if source["learning_unit_id"]
            else None,
        ),
    )


async def read_revisions(
    db: AsyncSession, owner: UUID, node: str, *, limit: int = 20, before_revision: int | None = None
) -> dict[str, Any]:
    if not 1 <= limit <= 50 or before_revision is not None and before_revision < 1:
        raise SnapshotError("INVALID_API_INPUT")
    query = select(NodeMasteryRevision).where(
        NodeMasteryRevision.user_id == owner, NodeMasteryRevision.knowledge_node_id == node
    )
    if before_revision is not None:
        query = query.where(NodeMasteryRevision.revision < before_revision)
    rows = (
        await db.scalars(query.order_by(NodeMasteryRevision.revision.desc()).limit(limit + 1))
    ).all()
    items = []
    for row in rows[:limit]:
        previous = None
        if row.recomputed_from_id is not None:
            previous = await db.scalar(
                select(NodeMasteryRevision.revision).where(
                    NodeMasteryRevision.id == row.recomputed_from_id,
                    NodeMasteryRevision.user_id == owner,
                    NodeMasteryRevision.knowledge_node_id == node,
                )
            )
        items.append(
            dict(
                revision=row.revision,
                previous_score=row.previous_score,
                score=row.score,
                status=row.status,
                rule_version=row.rule_version,
                created_at=row.created_at.isoformat(),
                evidence_summary=row.evidence_summary,
                recomputed_from_revision=previous,
                source=await source_ref(db, owner, node, row.evidence_id),
            )
        )
    return dict(
        node_id=node,
        items=items,
        next_before_revision=rows[limit - 1].revision if len(rows) > limit else None,
    )
