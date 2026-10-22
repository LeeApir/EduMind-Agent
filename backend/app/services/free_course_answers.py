"""Exact-version deterministic provisional practice, without model grading or mastery claims."""

from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.free_course_answers import (
    FreeCourseAnswerAttempt,
    FreeCourseAssessmentExposure,
    FreeCourseExerciseVersion,
)
from app.services.catalog_assessment import fixed_question_digest
from app.services.catalog_package import content_digest
from app.services.free_course_exercise_identity import exercise_identity
from app.services.free_course_quality import (
    assert_visible,
    locate,
    validate_schema,
    visibility_state,
)
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, digest
from app.services.quiz_scoring import QUIZ_SCORING_RULE_VERSION, _canonical_answer


def exercise_digests(block: dict[str, Any]) -> tuple[str, str]:
    items = block["items"]
    assessment = fixed_question_digest(
        dict(items=[dict(question=q["question"], answer=q["answer_key"]) for q in items])
    )
    stems = content_digest(sorted(_canonical_answer(q["question"]) for q in items))
    return assessment, stems


async def ensure_exercise(
    db: AsyncSession, owner: UUID, cid: UUID, binding: dict[str, Any], eid: str, evid: str
) -> FreeCourseExerciseVersion:
    _, scene, raw, block = await locate(
        db, owner, cid, binding, exercise_id=eid, exercise_version_id=evid
    )
    if block is None:
        raise SnapshotError("NOT_FOUND")
    row = await db.get(FreeCourseExerciseVersion, UUID(evid))
    if row is not None:
        if row.user_id != owner or row.course_id != cid or row.scene_version_id != scene.id:
            raise SnapshotError("NOT_FOUND")
        return row
    assessment, stems = exercise_digests(block)
    row = FreeCourseExerciseVersion(
        id=UUID(evid),
        user_id=owner,
        course_id=cid,
        scene_version_id=scene.id,
        exercise_id=UUID(eid),
        anchor_id=block["anchor_id"],
        content_json=deepcopy(block),
        content_digest=digest("exercise-content-v1", block=block, rule=QUIZ_SCORING_RULE_VERSION),
        context_digest=digest(
            "exercise-context-v1",
            content=raw["content"],
            actions=raw["actions"],
            dependencies=raw["dependencies"],
        ),
        assessment_digest=assessment,
        question_stem_digest=stems,
        rule_version=QUIZ_SCORING_RULE_VERSION,
    )
    db.add(row)
    await db.flush()
    return row


async def prior_exposure(
    db: AsyncSession, owner: UUID, exercise: FreeCourseExerciseVersion
) -> bool:
    return (
        await db.scalar(
            select(FreeCourseAssessmentExposure.id)
            .where(
                FreeCourseAssessmentExposure.user_id == owner,
                or_(
                    FreeCourseAssessmentExposure.assessment_digest == exercise.assessment_digest,
                    FreeCourseAssessmentExposure.question_stem_digest
                    == exercise.question_stem_digest,
                ),
            )
            .limit(1)
        )
        is not None
    )


async def record_exposure(
    db: AsyncSession,
    owner: UUID,
    exercise: FreeCourseExerciseVersion,
    kind: str,
    binding: dict[str, Any],
) -> None:
    # Caller holds the same owner lock as answers/maintenance/tutor dispatch.
    db.add(
        FreeCourseAssessmentExposure(
            user_id=owner,
            course_id=exercise.course_id,
            exercise_version_id=exercise.id,
            assessment_digest=exercise.assessment_digest,
            question_stem_digest=exercise.question_stem_digest,
            kind=kind,
            binding_json=deepcopy(binding),
        )
    )
    await db.flush()


def provisional(
    exercise: FreeCourseExerciseVersion, answers: list[dict[str, str]]
) -> dict[str, Any]:
    submitted = {q["question_id"]: q["answer"] for q in answers}
    items = exercise.content_json["items"]
    complete = all(submitted.get(q["question_id"], "").strip() for q in items)
    result: dict[str, Any] = dict(
        completeness="complete" if complete else "incomplete",
        reliability="provisional",
        comparison_score=None,
        question_results=[],
        mastery_effect="course_only",
        reason_code="PROVISIONAL_REFERENCE_ANSWER",
    )
    if complete:
        results = [
            dict(
                question_id=q["question_id"],
                matches_reference=_canonical_answer(submitted[q["question_id"]])
                == _canonical_answer(q["answer_key"]),
                explanation=q["solution"],
            )
            for q in items
        ]
        result.update(
            comparison_score=sum(q["matches_reference"] for q in results) / len(results),
            question_results=results,
        )
    return result


class Answers:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def submit(
        self, owner: UUID, cid: UUID, body: dict[str, Any], *, key: str
    ) -> dict[str, str]:
        validate_schema("AttemptRequest", body)
        supplied = body["answers"]
        ids = [q["question_id"] for q in supplied]
        if len(ids) != len(set(ids)) or not any(q["answer"].strip() for q in supplied):
            raise SnapshotError("INVALID_ANSWER_INPUT")
        async with self.sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            await repo._course(cid, lock=True)
            route = f"/api/free-courses/{cid}/attempts"
            fingerprint = digest("free-course-answers-v1", body=body)
            replay = await repo._receipt(route, key, fingerprint)
            if replay is not None:
                return replay
            binding = {k: body[k] for k in ("course_version", "scene_id", "scene_version_id")}
            current = await repo.get_course(cid)
            if current["head_version"] != body["course_version"]:
                raise SnapshotError("STALE_COURSE_VERSION")
            exercise = await ensure_exercise(
                db, owner, cid, binding, body["exercise_id"], body["exercise_version_id"]
            )
            await assert_visible(db, owner, cid, exercise.scene_version_id, exercise.anchor_id)
            from app.services.free_scene_availability import read_ready_scene

            await read_ready_scene(
                db, owner, cid, version=body["course_version"], scene_id=UUID(body["scene_id"])
            )
            allowed = {q["question_id"] for q in exercise.content_json["items"]}
            if not set(ids) <= allowed:
                raise SnapshotError("INVALID_ANSWER_INPUT")
            feedback = provisional(exercise, supplied)
            qualification = dict(
                first_complete=False,
                assisted=await prior_exposure(db, owner, exercise),
                rule_version="free-course-first-complete-v1",
            )
            if feedback["completeness"] == "complete":
                qualification["first_complete"] = not qualification["assisted"]
                await record_exposure(db, owner, exercise, "first_complete", binding)
            manifest = await repo.get_version(cid, body["course_version"])
            attempt = FreeCourseAnswerAttempt(
                id=uuid4(),
                created_at=await repo._now(),
                user_id=owner,
                course_id=cid,
                course_version_id=UUID(manifest["id"]),
                exercise_version_id=exercise.id,
                binding_json=binding,
                answers_json=deepcopy(supplied),
                completeness=feedback["completeness"],
                feedback_json=feedback,
                qualification_json=qualification,
                request_digest=fingerprint,
            )
            from app.services.free_course_evidence import admit_attempt

            evidence = await admit_attempt(db, owner, exercise, attempt)
            db.add(attempt)
            await db.flush()
            if evidence is not None:
                from app.services.mastery_updates import apply_mastery_evidence

                await apply_mastery_evidence(db, evidence)
            return await repo._record(
                cid, route, key, fingerprint, dict(attempt_id=str(attempt.id))
            )

    async def read(self, owner: UUID, cid: UUID, aid: UUID) -> dict[str, Any]:
        async with self.sessions() as db:
            await SnapshotRepository(db, owner).get_course(cid)
            row = await db.scalar(
                select(FreeCourseAnswerAttempt).where(
                    FreeCourseAnswerAttempt.user_id == owner,
                    FreeCourseAnswerAttempt.course_id == cid,
                    FreeCourseAnswerAttempt.id == aid,
                )
            )
            if row is None:
                raise SnapshotError("NOT_FOUND")
            exercise = await db.get(FreeCourseExerciseVersion, row.exercise_version_id)
            if exercise is None:
                raise SnapshotError("NOT_FOUND")
            feedback = deepcopy(row.feedback_json)
            from app.services.free_course_evidence import active_attestations, admission_state

            admission, revoked = await admission_state(db, owner, aid)
            active = await active_attestations(db, owner, exercise)
            from app.models.free_course_evidence import (
                FreeCourseAttestation,
                FreeCourseAttestationRevocation,
            )

            revocations = (
                await db.scalars(
                    select(FreeCourseAttestationRevocation)
                    .join(
                        FreeCourseAttestation,
                        FreeCourseAttestation.id == FreeCourseAttestationRevocation.attestation_id,
                    )
                    .where(
                        FreeCourseAttestation.user_id == owner,
                        FreeCourseAttestation.exercise_version_id == exercise.id,
                        FreeCourseAttestation.kind == "answer_attestation",
                    )
                )
            ).all()
            withdrawn = revoked or any(
                "answer_attestation" not in active or rev.created_at >= row.created_at
                for rev in revocations
            )
            if withdrawn or await visibility_state(
                db, owner, cid, exercise.scene_version_id, exercise.anchor_id
            ):
                feedback.update(
                    reliability="withdrawn",
                    comparison_score=None,
                    question_results=[],
                    mastery_effect="revoked" if revoked else "course_only",
                    reason_code="EVIDENCE_REVOKED" if revoked else "CONTENT_UNAVAILABLE",
                )
            return dict(
                attempt_id=str(aid),
                binding=deepcopy(row.binding_json),
                exercise_id=str(exercise.exercise_id),
                exercise_version_id=str(exercise.id),
                answers=deepcopy(row.answers_json),
                **feedback,
            )


def public_exercise(
    owner: UUID, cid: UUID, sid: UUID, sv: UUID, block: dict[str, Any], *, disabled: bool = False
) -> dict[str, Any]:
    eid, evid = exercise_identity(owner, cid, sid, sv, block["exercise_key"])
    base = dict(
        kind="exercise_unavailable" if disabled else "exercise",
        anchor_id=block["anchor_id"],
        exercise_id=str(eid),
        exercise_version_id=str(evid),
    )
    if disabled:
        return dict(**base, reason_code="EXERCISE_UNAVAILABLE")
    return dict(
        **base,
        question=block["question"],
        items=[
            {k: q[k] for k in ("question_id", "question", "input_type")} for q in block["items"]
        ],
    )
