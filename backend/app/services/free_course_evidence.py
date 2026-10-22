"""Trusted exact-version attestations and source-aware effective evidence."""

from copy import deepcopy
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.free_course_answers import FreeCourseAnswerAttempt, FreeCourseExerciseVersion
from app.models.free_course_evidence import (
    FreeCourseAttestation,
    FreeCourseAttestationRevocation,
    FreeCourseEvidenceAdmission,
    FreeCourseEvidenceRevocation,
)
from app.models.learning import GeneratedResource
from app.models.learning_state import LearningEvidence
from app.services.catalog_assessment import fixed_question_digest, mastery_eligible
from app.services.catalog_package import content_digest
from app.services.free_course_answers import ensure_exercise
from app.services.free_course_quality import (
    Maintenance,
    assert_visible,
    locate,
    validate_schema,
    visibility_state,
)
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, digest
from app.services.knowledge_graph_versions import graph_repository_for_version
from app.services.quiz_scoring import _canonical_answer

RULE = "free-course-evidence-v1"


async def active_attestations(
    db: AsyncSession, owner: UUID, e: FreeCourseExerciseVersion
) -> dict[str, FreeCourseAttestation]:
    rows = (
        await db.scalars(
            select(FreeCourseAttestation)
            .where(
                FreeCourseAttestation.user_id == owner,
                FreeCourseAttestation.exercise_version_id == e.id,
                ~FreeCourseAttestation.id.in_(
                    select(FreeCourseAttestationRevocation.attestation_id)
                ),
            )
            .order_by(FreeCourseAttestation.created_at.desc(), FreeCourseAttestation.id.desc())
        )
    ).all()
    result: dict[str, FreeCourseAttestation] = {}
    for r in rows:
        if r.content_digest == e.content_digest and r.context_digest == e.context_digest:
            result.setdefault(r.kind, r)
    return result


class Attestations(Maintenance):
    async def preview_attestation(self, owner: UUID, draft: dict[str, Any]) -> dict[str, Any]:
        validate_schema("AttestationDraft", draft)
        if not draft["reason"].strip() or any(
            b["kind"] == "mechanical_rule"
            or any(not b[k].strip() for k in ["source_ref", "excerpt", "reason"])
            for b in draft["basis"]
        ):
            raise SnapshotError("INDEPENDENT_ATTESTATION_REQUIRED")
        async with self.sessions() as db:
            manifest, scene, raw, block = await locate(
                db,
                owner,
                UUID(draft["course_id"]),
                draft["binding"],
                exercise_id=draft["exercise_id"],
                exercise_version_id=draft["exercise_version_id"],
            )
            if block is None:
                raise SnapshotError("NOT_FOUND")
            await assert_visible(db, owner, scene.course_id, scene.id, block["anchor_id"])
            if draft["kind"] == "mapping_attestation":
                graph = graph_repository_for_version(draft["graph_version"])
                if graph.get_node(draft["node_id"]) is None or not any(
                    link["node_id"] == draft["node_id"]
                    and link["graph_version"] == draft["graph_version"]
                    for link in manifest["node_links"]
                ):
                    raise SnapshotError("MAPPING_ASSOCIATION_REQUIRED")
            return dict(
                content_digest=digest(
                    "exercise-content-v1", block=block, rule="quiz-exact-text-v1"
                ),
                context_digest=digest(
                    "exercise-context-v1",
                    content=raw["content"],
                    actions=raw["actions"],
                    dependencies=raw["dependencies"],
                ),
            )

    async def attest(self, owner: UUID, draft: dict[str, Any]) -> dict[str, str]:
        # The preview never persists even an exercise version. Apply rechecks under owner lock.
        validate_schema("AttestationDraft", draft)
        cid = UUID(draft["course_id"])
        fingerprint = digest("attestation-v1", draft=draft)
        async with self.sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            await repo._course(cid, lock=True)
            old = await db.scalar(
                select(FreeCourseAttestation).where(
                    FreeCourseAttestation.user_id == owner,
                    FreeCourseAttestation.decision_key == draft["decision_key"],
                )
            )
            if old:
                if old.request_digest != fingerprint:
                    raise SnapshotError("IDEMPOTENCY_CONFLICT")
                return dict(attestation_id=str(old.id))
            await self.preview_attestation(owner, draft)
            e = await ensure_exercise(
                db, owner, cid, draft["binding"], draft["exercise_id"], draft["exercise_version_id"]
            )
            await assert_visible(db, owner, cid, e.scene_version_id, e.anchor_id)
            if e.content_digest != draft["content_digest"]:
                raise SnapshotError("ATTESTATION_DIGEST_MISMATCH")
            if draft["kind"] in await active_attestations(db, owner, e):
                raise SnapshotError("ATTESTATION_EXISTS")
            row = FreeCourseAttestation(
                user_id=owner,
                course_id=cid,
                exercise_version_id=e.id,
                kind=draft["kind"],
                decision_key=draft["decision_key"],
                request_digest=fingerprint,
                content_digest=e.content_digest,
                context_digest=e.context_digest,
                node_id=draft["node_id"],
                graph_version=draft["graph_version"],
                authority=self.authority.name,
                rule_version=RULE,
                evidence_json=deepcopy(draft),
            )
            db.add(row)
            await db.flush()
            return dict(attestation_id=str(row.id))


async def legacy_prior(db: AsyncSession, owner: UUID, e: FreeCourseExerciseVersion) -> str | None:
    # Compare exact retained versions globally, without a current-node shortcut.
    rows = (
        await db.scalars(
            select(LearningEvidence).where(
                LearningEvidence.user_id == owner,
                LearningEvidence.source_protocol.is_(None),
                LearningEvidence.evidence_type.in_(
                    ("quiz_attempt", "hint_used", "reexplanation_requested")
                ),
            )
        )
    ).all()
    unknown = False
    for r in rows:
        resource = await db.get(GeneratedResource, r.resource_id) if r.resource_id else None
        if (
            resource is None
            or resource.user_id != owner
            or resource.version != r.resource_version
            or resource.resource_type != "exercise"
        ):
            unknown = True
            continue
        try:
            items = cast(list[dict[str, Any]], resource.content["items"])
            assessment = fixed_question_digest(dict(items=items))
            stem = content_digest(sorted(_canonical_answer(q["question"]) for q in items))
            allowed = {q["id"] for q in items}
            answers = r.payload.get("answers", [])
            complete = (
                isinstance(answers, list)
                and {a["question_id"] for a in answers if a["answer"].strip()} == allowed
            )
            if (assessment == e.assessment_digest or stem == e.question_stem_digest) and (
                r.evidence_type != "quiz_attempt" or complete
            ):
                return "PRIOR_ASSESSMENT"
        except (KeyError, TypeError, ValueError, AssertionError):
            unknown = True
    return "PRIOR_ASSESSMENT_UNKNOWN" if unknown else None


async def admission_state(
    db: AsyncSession, owner: UUID, aid: UUID
) -> tuple[FreeCourseEvidenceAdmission | None, bool]:
    admission = await db.scalar(
        select(FreeCourseEvidenceAdmission).where(
            FreeCourseEvidenceAdmission.user_id == owner,
            FreeCourseEvidenceAdmission.attempt_id == aid,
        )
    )
    revoked = (
        admission is not None
        and await db.scalar(
            select(FreeCourseEvidenceRevocation.id).where(
                FreeCourseEvidenceRevocation.admission_id == admission.id
            )
        )
        is not None
    )
    return admission, revoked


async def effective_evidence(db: AsyncSession, row: LearningEvidence) -> bool:
    if row.source_protocol is None:
        return row.evidence_type != "evidence_correction" and mastery_eligible(row.payload)
    if (
        row.source_protocol != "free-course-v1"
        or row.evidence_type != "quiz_attempt"
        or row.free_course_attempt_id is None
    ):
        return False
    admission, revoked = await admission_state(db, row.user_id, row.free_course_attempt_id)
    if (
        admission is None
        or revoked
        or admission.evidence_id != row.id
        or admission.node_id != row.knowledge_node_id
    ):
        return False
    attempt = await db.get(FreeCourseAnswerAttempt, admission.attempt_id)
    if attempt is None:
        return False
    e = await db.get(FreeCourseExerciseVersion, attempt.exercise_version_id)
    if e is None or await visibility_state(
        db, row.user_id, e.course_id, e.scene_version_id, e.anchor_id
    ):
        return False
    active = await active_attestations(db, row.user_id, e)
    return (
        active.get("answer_attestation") is not None
        and active.get("mapping_attestation") is not None
        and active["answer_attestation"].id == admission.answer_attestation_id
        and active["mapping_attestation"].id == admission.mapping_attestation_id
    )


async def admit_attempt(
    db: AsyncSession, owner: UUID, e: FreeCourseExerciseVersion, attempt: FreeCourseAnswerAttempt
) -> LearningEvidence | None:
    if attempt.completeness != "complete":
        return None
    reason = await legacy_prior(db, owner, e)
    if reason:
        attempt.feedback_json = {**attempt.feedback_json, "reason_code": reason}
        return None
    if not attempt.qualification_json["first_complete"]:
        return None
    active = await active_attestations(db, owner, e)
    answer, mapping = active.get("answer_attestation"), active.get("mapping_attestation")
    if answer is None or mapping is None:
        return None
    if answer.created_at > attempt.created_at or mapping.created_at > attempt.created_at:
        return None
    if mapping.node_id is None:
        raise SnapshotError("MAPPING_ASSOCIATION_REQUIRED")
    from app.services.mastery_updates import lock_mastery_node

    await lock_mastery_node(db, owner_id=owner, node_id=mapping.node_id)
    evidence_id = uuid4()
    admission = FreeCourseEvidenceAdmission(
        id=uuid4(),
        user_id=owner,
        course_id=e.course_id,
        attempt_id=attempt.id,
        evidence_id=evidence_id,
        answer_attestation_id=answer.id,
        mapping_attestation_id=mapping.id,
        node_id=mapping.node_id,
        rule_version=RULE,
        binding_digest=digest(
            "evidence-binding-v1",
            exercise_id=str(e.id),
            answer=str(answer.id),
            mapping=str(mapping.id),
            attempt=str(attempt.id),
        ),
    )
    record = LearningEvidence(
        id=evidence_id,
        user_id=owner,
        idempotency_key=f"free-course:{attempt.id}",
        request_digest=attempt.request_digest,
        evidence_type="quiz_attempt",
        knowledge_node_id=mapping.node_id,
        schema_version=1,
        rule_version="mastery-v1",
        source_protocol="free-course-v1",
        free_course_attempt_id=attempt.id,
        payload=dict(
            score=attempt.feedback_json["comparison_score"], admission_id=str(admission.id)
        ),
    )
    db.add_all([admission, record])
    attempt.feedback_json = {
        **attempt.feedback_json,
        "mastery_effect": "admitted",
        "reliability": "verified",
        "reason_code": None,
    }
    return record


async def revoke_exercises(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    exercises: list[FreeCourseExerciseVersion],
    cause: dict[str, Any],
) -> None:
    from app.services.mastery_updates import apply_mastery_evidence, lock_mastery_node

    ids = [e.id for e in exercises]
    attestations = (
        await db.scalars(
            select(FreeCourseAttestation).where(
                FreeCourseAttestation.user_id == owner,
                FreeCourseAttestation.exercise_version_id.in_(ids),
            )
        )
    ).all()
    for a in attestations:
        if (
            await db.scalar(
                select(FreeCourseAttestationRevocation.id).where(
                    FreeCourseAttestationRevocation.attestation_id == a.id
                )
            )
            is None
        ):
            db.add(
                FreeCourseAttestationRevocation(
                    user_id=owner, course_id=cid, attestation_id=a.id, reason_json=cause
                )
            )
    admissions = (
        await db.scalars(
            select(FreeCourseEvidenceAdmission)
            .join(
                FreeCourseAnswerAttempt,
                FreeCourseAnswerAttempt.id == FreeCourseEvidenceAdmission.attempt_id,
            )
            .where(
                FreeCourseEvidenceAdmission.user_id == owner,
                FreeCourseAnswerAttempt.exercise_version_id.in_(ids),
            )
            .order_by(FreeCourseEvidenceAdmission.node_id, FreeCourseEvidenceAdmission.id)
        )
    ).all()
    for node in sorted({a.node_id for a in admissions}):
        await lock_mastery_node(db, owner_id=owner, node_id=node)
    for admission in admissions:
        if (
            await db.scalar(
                select(FreeCourseEvidenceRevocation.id).where(
                    FreeCourseEvidenceRevocation.admission_id == admission.id
                )
            )
            is not None
        ):
            continue
        correction = LearningEvidence(
            id=uuid4(),
            user_id=owner,
            idempotency_key=f"free-course-revoke:{admission.id}",
            request_digest=digest("revoke-v1", cause=cause, admission=str(admission.id)),
            evidence_type="evidence_correction",
            knowledge_node_id=admission.node_id,
            schema_version=1,
            rule_version="mastery-v1",
            source_protocol="free-course-correction-v1",
            corrects_evidence_id=admission.evidence_id,
            payload=dict(reason=cause, admission_id=str(admission.id)),
        )
        db.add(correction)
        db.add(
            FreeCourseEvidenceRevocation(
                user_id=owner,
                course_id=cid,
                admission_id=admission.id,
                correction_evidence_id=correction.id,
                reason_json=cause,
            )
        )
        await db.flush()
        await apply_mastery_evidence(db, correction)
