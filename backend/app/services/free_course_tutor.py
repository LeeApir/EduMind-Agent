"""Exact public-scene tutor contexts. No Provider or implicit model dispatch."""

from copy import deepcopy
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.free_course_evidence import FreeCourseAttestationRevocation
from app.models.free_course_progress import FreeCourseEvent, FreeCourseStep
from app.models.free_course_scheduler import FreeCourseAttempt, FreeCourseSettlement
from app.models.free_course_tutor import FreeCourseTutorReply, FreeCourseTutorTurn
from app.models.free_course_writes import FreeCourseOperation
from app.models.learning_state import LearningEvidence
from app.services.free_course_answers import ensure_exercise, public_exercise, record_exposure
from app.services.free_course_evidence import active_attestations, effective_evidence
from app.services.free_course_quality import validate_schema, visibility_state
from app.services.free_course_snapshots import (
    SnapshotError,
    SnapshotRepository,
    WriteFence,
    canonical,
    digest,
)
from app.services.free_scene_availability import _live, read_ready_scene
from app.services.free_scene_validation import clean_markdown
from app.services.mastery_rules import MasteryFact, reduce_mastery
from app.services.owned_learning import latest_profile

POLICY = dict(
    kind="tutor_turn",
    version="free-course-tutor-v1",
    attempts=1,
    seconds=90,
    input_tokens=16000,
    output_tokens=2000,
    automatic_retries=0,
    format_repairs=0,
    shared_course_attempts=40,
    shared_course_input_tokens=600000,
    shared_course_output_tokens=144000,
)


def identity(row: FreeCourseTutorTurn) -> str:
    return digest("tutor-context-v1", context=row.context_json, sources=row.sources_json)


def merge_sources(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in target:
        for item in source[key]:
            if canonical(item) not in [canonical(v) for v in target[key]]:
                target[key].append(deepcopy(item))


async def preferences(db: AsyncSession, owner: UUID) -> dict[str, Any]:
    profile = await latest_profile(db, owner)
    result: dict[str, Any] = {}
    if profile is None:
        return result
    evidence = profile.evidence or {}
    for field in ("cognitive_style", "engineering_preference"):
        proofs = evidence.get(field)
        value = getattr(profile, field)
        explicit = (
            [
                p
                for p in proofs
                if isinstance(p, dict)
                and p.get("source")
                in ("initial_query", "learner_statement", "explicit_feedback", "manual_correction")
                and isinstance(p.get("confidence"), (int, float))
                and p["confidence"] > 0
            ]
            if isinstance(proofs, list)
            else []
        )
        if value is not None and explicit:
            result[field] = dict(
                value=deepcopy(value), source="student_declared", evidence=explicit
            )
    return result


async def check_sources(db: AsyncSession, owner: UUID, cid: UUID, sources: dict[str, Any]) -> bool:
    """Recheck all used source facts; a newer head alone does not erase valid history."""
    try:
        for binding in sources["scenes"]:
            actual = await read_ready_scene(
                db,
                owner,
                cid,
                version=binding["course_version"],
                scene_id=UUID(binding["scene_id"]),
            )
            if actual["scene_version_id"] != binding["scene_version_id"]:
                return False
        for exercise in sources["exercises"]:
            if await visibility_state(
                db, owner, cid, UUID(exercise["scene_version_id"]), exercise["anchor_id"]
            ):
                return False
            for aid in exercise["answer_attestations"]:
                rev = await db.scalar(
                    select(FreeCourseAttestationRevocation).where(
                        FreeCourseAttestationRevocation.user_id == owner,
                        FreeCourseAttestationRevocation.attestation_id == UUID(aid),
                    )
                )
                if rev and rev.reason_json.get("kind") == "confirmed_defect":
                    return False
        current = await preferences(db, owner)
        for p in sources["preferences"]:
            if digest("tutor-preference", value=current.get(p["field"])) != p["digest"]:
                return False
        for eid in sources["evidence_ids"]:
            row = await db.get(LearningEvidence, UUID(eid))
            if row is None or row.user_id != owner or not await effective_evidence(db, row):
                return False
    except SnapshotError:
        return False
    return True


async def context(
    db: AsyncSession, owner: UUID, cid: UUID, binding: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    repo = SnapshotRepository(db, owner)
    manifest = await repo.get_version(cid, binding["course_version"])
    raw = await repo.get_scene_snapshot(cid, binding["course_version"], UUID(binding["scene_id"]))
    if raw["scene_version_id"] != binding["scene_version_id"]:
        raise SnapshotError("SCENE_BINDING_MISMATCH")
    sources: dict[str, Any] = dict(scenes=[], exercises=[], preferences=[], evidence_ids=[])
    source_bindings = [binding]
    for dep in raw["dependencies"][:2]:
        match = next(
            (s for s in manifest["scenes"] if s["scene_version_id"] == dep["scene_version_id"]),
            None,
        )
        if match is None:
            raise SnapshotError("DEPENDENCY_UNAVAILABLE")
        source_bindings.append(
            dict(
                course_version=binding["course_version"],
                scene_id=match["scene_id"],
                scene_version_id=match["scene_version_id"],
            )
        )
    public = []
    anchors = []
    for source in source_bindings:
        value = await read_ready_scene(
            db, owner, cid, version=source["course_version"], scene_id=UUID(source["scene_id"])
        )
        if value["scene_version_id"] != source["scene_version_id"]:
            raise SnapshotError("SCENE_BINDING_MISMATCH")
        sources["scenes"].append(deepcopy(source))
        blocks = []
        for block in value["blocks"]:
            if block["kind"] == "exercise":
                if block.get("disabled"):
                    continue
                block = public_exercise(
                    owner, cid, UUID(source["scene_id"]), UUID(source["scene_version_id"]), block
                )
                exercise = await ensure_exercise(
                    db, owner, cid, source, block["exercise_id"], block["exercise_version_id"]
                )
                active = await active_attestations(db, owner, exercise)
                sources["exercises"].append(
                    dict(
                        **source,
                        anchor_id=block["anchor_id"],
                        exercise_id=block["exercise_id"],
                        exercise_version_id=block["exercise_version_id"],
                        answer_attestations=[str(active["answer_attestation"].id)]
                        if "answer_attestation" in active
                        else [],
                    )
                )
            blocks.append(deepcopy(block))
            if len(block["anchor_id"]) <= 128:
                anchors.append(block["anchor_id"])
        public.append(dict(binding=deepcopy(source), blocks=blocks))
    declared = await preferences(db, owner)
    for field, value in declared.items():
        sources["preferences"].append(
            dict(field=field, digest=digest("tutor-preference", value=value))
        )
    nodes = {
        link["node_id"]
        for link in manifest["node_links"]
        if link["scene_id"] is None or link["scene_id"] in {b["scene_id"] for b in source_bindings}
    }
    mastery = []
    for node in sorted(nodes):
        facts = []
        rows = (
            await db.scalars(
                select(LearningEvidence)
                .where(
                    LearningEvidence.user_id == owner, LearningEvidence.knowledge_node_id == node
                )
                .order_by(LearningEvidence.created_at, LearningEvidence.id)
            )
        ).all()
        for row in rows:
            if await effective_evidence(db, row):
                facts.append(MasteryFact(row.evidence_type, row.payload))
                sources["evidence_ids"].append(str(row.id))
        if facts:
            decision = reduce_mastery(facts)
            mastery.append(
                dict(
                    node_id=node,
                    score=decision.score,
                    status=decision.status,
                    source="effective_evidence",
                )
            )
    previous = (
        await db.scalars(
            select(FreeCourseTutorTurn)
            .where(
                FreeCourseTutorTurn.user_id == owner,
                FreeCourseTutorTurn.course_id == cid,
                FreeCourseTutorTurn.scene_version_id == UUID(binding["scene_version_id"]),
                FreeCourseTutorTurn.binding_json["course_version"].as_integer()
                == binding["course_version"],
            )
            .order_by(FreeCourseTutorTurn.created_at.desc(), FreeCourseTutorTurn.id.desc())
        )
    ).all()
    history = []
    for turn in previous:
        reply = await db.scalar(
            select(FreeCourseTutorReply).where(FreeCourseTutorReply.turn_id == turn.id)
        )
        if (
            reply
            and turn.context_digest == identity(turn)
            and await check_sources(db, owner, cid, turn.sources_json)
        ):
            if reply.reply_digest != digest(
                "tutor-reply-v1", markdown=reply.markdown, anchor_refs=reply.anchor_refs
            ):
                raise SnapshotError("SNAPSHOT_CORRUPT")
            history.append(
                dict(message=turn.message, markdown=reply.markdown, anchor_refs=reply.anchor_refs)
            )
            merge_sources(sources, turn.sources_json)
            if len(history) == 2:
                break
    course = await repo.get_course(cid)
    payload = dict(
        schema_version="free-course-tutor-context-v1",
        original_goal=course["original_goal"],
        current=public[0],
        upstream=public[1:],
        learner=dict(
            declared_preferences=declared,
            effective_mastery=mastery,
            unknown="Other learner facts are unknown; declarations are not demonstrated mastery.",
        ),
        history=list(reversed(history)),
        anchor_refs=list(dict.fromkeys(anchors)),
    )
    if len(canonical(dict(context=payload, sources=sources))) > 128000:
        raise SnapshotError("TUTOR_CONTEXT_TOO_LARGE")
    return payload, sources


class TutorTurns:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def enqueue(
        self, owner: UUID, cid: UUID, body: dict[str, Any], *, key: str
    ) -> dict[str, Any]:
        validate_schema("TutorRequest", body)
        if not body["message"].strip():
            raise SnapshotError("INVALID_TUTOR_INPUT")
        route = f"/api/free-courses/{cid}/tutor-turns"
        fingerprint = digest("tutor-request-v1", body=body)
        async with self.sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            course = await repo._course(cid, lock=True)
            replay = await repo._receipt(route, key, fingerprint)
            if replay is not None:
                return replay
            head = await repo._expected(course, body["course_version"])
            if head is None:
                raise SnapshotError("SCENE_NOT_READY")
            if await db.scalar(
                select(FreeCourseOperation.id).where(
                    FreeCourseOperation.user_id == owner,
                    FreeCourseOperation.state.in_(("queued", "running", "cancel_requested")),
                )
            ):
                raise SnapshotError("OPERATION_ACTIVE")
            if await db.scalar(
                select(FreeCourseAttempt.id)
                .outerjoin(
                    FreeCourseSettlement, FreeCourseSettlement.attempt_id == FreeCourseAttempt.id
                )
                .where(FreeCourseAttempt.user_id == owner, FreeCourseSettlement.id.is_(None))
            ):
                raise SnapshotError("OUTCOME_UNRESOLVED")
            binding = {k: body[k] for k in ("course_version", "scene_id", "scene_version_id")}
            payload, sources = await context(db, owner, cid, binding)
            plan = await repo.get_plan(cid, head.plan_id)
            req = await repo.get_request(cid, 1)
            op = FreeCourseOperation(
                user_id=owner,
                course_id=cid,
                request_id=UUID(plan["request_id"]),
                kind="tutor_turn",
                base_head_version=head.version,
                config_snapshot=deepcopy(req["nonsecret_config_snapshot"]),
                policy_snapshot=POLICY,
                deadline_at=await repo._now() + timedelta(seconds=90),
            )
            db.add(op)
            await db.flush()
            turn = FreeCourseTutorTurn(
                id=uuid4(),
                user_id=owner,
                course_id=cid,
                operation_id=op.id,
                course_version_id=head.id,
                scene_version_id=UUID(body["scene_version_id"]),
                binding_json=binding,
                message=body["message"],
                context_json=payload,
                sources_json=sources,
                context_digest=digest("tutor-context-v1", context=payload, sources=sources),
            )
            db.add(turn)
            db.add(
                FreeCourseStep(
                    user_id=owner,
                    course_id=cid,
                    operation_id=op.id,
                    step_key="tutor",
                    state="pending",
                )
            )
            # Mark all involved groups assisted, including previously unattempted groups.
            for source in sources["exercises"]:
                exercise = await ensure_exercise(
                    db, owner, cid, source, source["exercise_id"], source["exercise_version_id"]
                )
                await record_exposure(
                    db, owner, exercise, "help", dict(**binding, tutor_turn_id=str(turn.id))
                )
            db.add(
                FreeCourseEvent(
                    user_id=owner,
                    course_id=cid,
                    operation_id=op.id,
                    seq=1,
                    event_type="queued",
                    course_version_id=head.id,
                    payload={},
                )
            )
            await db.flush()
            return await repo._record(
                cid,
                route,
                key,
                fingerprint,
                dict(operation_id=str(op.id), turn_id=str(turn.id)),
                status_code=202,
            )

    async def read(self, owner: UUID, cid: UUID, tid: UUID) -> dict[str, Any]:
        async with self.sessions() as db:
            await SnapshotRepository(db, owner)._course(cid)
            turn = await db.scalar(
                select(FreeCourseTutorTurn).where(
                    FreeCourseTutorTurn.user_id == owner,
                    FreeCourseTutorTurn.course_id == cid,
                    FreeCourseTutorTurn.id == tid,
                )
            )
            if turn is None:
                raise SnapshotError("NOT_FOUND")
            if turn.context_digest != identity(turn):
                raise SnapshotError("SNAPSHOT_CORRUPT")
            op = await SnapshotRepository(db, owner)._operation(cid, turn.operation_id)
            reply = await db.scalar(
                select(FreeCourseTutorReply).where(FreeCourseTutorReply.turn_id == tid)
            )
            status = (
                "ready"
                if reply
                else {
                    "succeeded": "failed",
                    "cancel_requested": "running",
                    "partially_succeeded": "failed",
                    "awaiting_clarification": "failed",
                }.get(op.state, op.state)
            )
            reason = op.reason_code
            valid = await check_sources(db, owner, cid, turn.sources_json)
            if not valid:
                status, reason = "invalidated", "CONTEXT_UNAVAILABLE"
            if reply and reply.reply_digest != digest(
                "tutor-reply-v1", markdown=reply.markdown, anchor_refs=reply.anchor_refs
            ):
                raise SnapshotError("SNAPSHOT_CORRUPT")
            return dict(
                turn_id=str(tid),
                operation_id=str(op.id),
                binding=deepcopy(turn.binding_json),
                message=turn.message,
                status=status,
                markdown=reply.markdown if status == "ready" and reply else None,
                anchor_refs=deepcopy(reply.anchor_refs) if status == "ready" and reply else [],
                reason_code=reason,
            )


async def store_reply(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    fence: WriteFence,
    tid: UUID,
    markdown: str,
    anchor_refs: list[str],
) -> None:
    """Private commit hook for T044's settled single send; cannot change course snapshots."""
    repo = SnapshotRepository(db, owner)
    await repo._owner_lock()
    course = await repo._course(cid, lock=True)
    op = await repo._fence(cid, fence)
    turn = await db.scalar(
        select(FreeCourseTutorTurn).where(
            FreeCourseTutorTurn.user_id == owner,
            FreeCourseTutorTurn.course_id == cid,
            FreeCourseTutorTurn.id == tid,
            FreeCourseTutorTurn.operation_id == op.id,
        )
    )
    if turn is None or op.kind != "tutor_turn" or turn.context_digest != identity(turn):
        raise SnapshotError("TUTOR_BINDING_MISMATCH")
    await repo._expected(course, turn.binding_json["course_version"])
    if not await check_sources(db, owner, cid, turn.sources_json):
        raise SnapshotError("CONTEXT_UNAVAILABLE")
    if (
        not isinstance(markdown, str)
        or not markdown.strip()
        or len(markdown) > 6000
        or not isinstance(anchor_refs, list)
        or not all(isinstance(a, str) and 1 <= len(a) <= 128 for a in anchor_refs)
        or len(anchor_refs) > 32
        or len(set(anchor_refs)) != len(anchor_refs)
        or any(a not in turn.context_json["anchor_refs"] for a in anchor_refs)
    ):
        raise SnapshotError("TUTOR_OUTPUT_INVALID")
    safe = clean_markdown(markdown)
    if len(safe) > 6000:
        raise SnapshotError("TUTOR_OUTPUT_INVALID")
    reply_digest = digest("tutor-reply-v1", markdown=safe, anchor_refs=anchor_refs)
    previous = await db.scalar(
        select(FreeCourseTutorReply).where(FreeCourseTutorReply.turn_id == tid)
    )
    if previous:
        if previous.reply_digest != reply_digest:
            raise SnapshotError("IDEMPOTENCY_CONFLICT")
        return
    db.add(
        FreeCourseTutorReply(
            user_id=owner,
            course_id=cid,
            turn_id=tid,
            markdown=safe,
            anchor_refs=deepcopy(anchor_refs),
            reply_digest=reply_digest,
        )
    )
    await db.flush()
    await _live(db, owner, cid, fence)
