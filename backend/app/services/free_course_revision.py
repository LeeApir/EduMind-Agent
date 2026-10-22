"""Bounded revision impact, private staging and atomic full replacement; no external calls."""

from copy import deepcopy
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.free_course import FreeCourseRequest, FreeCourseSceneVersion
from app.models.free_course_progress import FreeCourseEvent, FreeCourseStep
from app.models.free_course_revision import (
    FreeCourseRevision,
    FreeCourseRevisionPlan,
    FreeCourseRevisionStage,
)
from app.models.free_course_writes import FreeCourseOperation
from app.models.free_scene_validation import FreeSceneValidation
from app.services import free_scene_availability as visibility
from app.services.free_course_snapshots import (
    SCHEMA,
    SnapshotError,
    SnapshotRepository,
    WriteFence,
    digest,
)
from app.services.free_scene_actions import prepare_presentation


async def context(db: AsyncSession, oid: UUID) -> FreeCourseRevision | None:
    op = await db.get(FreeCourseOperation, oid)
    if op is None or op.kind not in ("revise_scene", "adjust_outline", "clarify"):
        return None
    return cast(
        FreeCourseRevision | None,
        await db.scalar(select(FreeCourseRevision).where(FreeCourseRevision.operation_id == oid)),
    )


async def preview(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    *,
    kind: str,
    base: int | None,
    scene_id: UUID | None = None,
) -> dict[str, Any]:
    if (
        kind not in ("revise_scene", "adjust_outline")
        or (base is not None and (type(base) is not int or base < 1))
        or (base is None and kind == "revise_scene")
    ):
        raise SnapshotError("INVALID_REVISION_INPUT")
    repo = SnapshotRepository(db, owner)
    course = await repo.get_course(cid)
    if course["head_version"] != base:
        raise SnapshotError("STALE_COURSE_VERSION")
    if base is None:
        plan = {"scenes": []}
    else:
        manifest = await repo.get_version(cid, base)
        plan = await repo.get_plan(cid, UUID(manifest["plan_id"]))
    ids = [s["scene_id"] for s in plan["scenes"]]
    if (kind == "revise_scene" and str(scene_id) not in ids) or (
        kind == "adjust_outline" and scene_id is not None
    ):
        raise SnapshotError("NOT_FOUND")
    affected = set(ids) if kind == "adjust_outline" else {str(scene_id)}
    for s in plan["scenes"]:
        if set(s["depends_on"]) & affected:
            affected.add(s["scene_id"])
    value = dict(
        course_id=str(cid),
        base_head_version=base,
        kind=kind,
        affected_scene_ids=[i for i in ids if i in affected],
        requires_outline_adjustment=kind == "adjust_outline",
        max_attempts=13,
        max_seconds=600,
    )
    return {**value, "impact_digest": digest("revision-impact", **value)}


async def stages(db: AsyncSession, oid: UUID) -> dict[str, FreeCourseRevisionStage]:
    return {
        str(s.scene_id): s
        for s in (
            await db.scalars(
                select(FreeCourseRevisionStage).where(FreeCourseRevisionStage.operation_id == oid)
            )
        ).all()
    }


async def plan_binding(db: AsyncSession, oid: UUID) -> UUID | None:
    return cast(
        UUID | None,
        await db.scalar(
            select(FreeCourseRevisionPlan.plan_id).where(FreeCourseRevisionPlan.operation_id == oid)
        ),
    )


async def bind_plan(db: AsyncSession, owner: UUID, cid: UUID, fence: WriteFence, pid: UUID) -> None:
    repo = SnapshotRepository(db, owner)
    rev = await context(db, fence.operation_id)
    if rev is None:
        raise SnapshotError("NOT_FOUND")
    plan = await repo.get_plan(cid, pid)
    db.add(
        FreeCourseRevisionPlan(
            user_id=owner, course_id=cid, operation_id=fence.operation_id, plan_id=pid
        )
    )
    for scene in plan["scenes"]:
        db.add(
            FreeCourseStep(
                user_id=owner,
                course_id=cid,
                operation_id=fence.operation_id,
                plan_id=pid,
                scene_id=UUID(scene["scene_id"]),
                step_key="scene:" + scene["scene_key"],
                state="pending",
            )
        )
    await db.flush()
    if rev.kind == "adjust_outline":
        return
    if rev.base_head is None:
        raise SnapshotError("STALE_COURSE_VERSION")
    old = await repo.get_version(cid, rev.base_head)
    oldplan = await repo.get_plan(cid, UUID(old["plan_id"]))
    if plan["candidate"] != oldplan["candidate"]:
        raise SnapshotError("OUTLINE_ADJUSTMENT_REQUIRED")
    by_id = {s["scene_id"]: s for s in old["scenes"]}
    copied: dict[str, UUID] = {}
    for scene in plan["scenes"]:
        sid = scene["scene_id"]
        binding = by_id[sid]
        if sid in rev.impact_json["affected_scene_ids"] or binding["scene_version_id"] is None:
            continue
        source = await visibility.read_ready_scene(
            db, owner, cid, version=rev.base_head, scene_id=UUID(sid)
        )
        raw = await repo.get_scene_snapshot(cid, rev.base_head, UUID(sid))
        deps = []
        for d in raw["dependencies"]:
            if d["scene_id"] not in copied:
                raise SnapshotError("REVISION_DEPENDENCY_INVALID")
            row = await db.get(FreeCourseSceneVersion, copied[d["scene_id"]])
            if row is None:
                raise SnapshotError("SNAPSHOT_CORRUPT")
            deps.append(
                dict(
                    scene_id=d["scene_id"],
                    scene_version_id=str(row.id),
                    content_digest=row.content_digest,
                )
            )
        stored = await repo.store_scene(
            cid,
            fence,
            expected_head=rev.base_head,
            key="copy:" + str(fence.operation_id) + ":" + sid,
            plan_id=pid,
            scene_id=UUID(sid),
            content=raw["content"],
            actions=raw["actions"],
            dependencies=deps,
        )
        previous = await db.scalar(
            select(FreeCourseStep).where(
                FreeCourseStep.scene_version_id == UUID(source["scene_version_id"]),
                FreeCourseStep.user_id == owner,
                FreeCourseStep.course_id == cid,
                FreeCourseStep.state == "ready",
            )
        )
        if previous is None or previous.presentation_id is None:
            raise SnapshotError("HARD_GATE_REJECTED")
        sv = UUID(stored["scene_version_id"])
        copied[sid] = sv
        db.add(
            FreeCourseRevisionStage(
                user_id=owner,
                course_id=cid,
                operation_id=fence.operation_id,
                scene_id=UUID(sid),
                scene_version_id=sv,
                presentation_id=previous.presentation_id,
                source_version_id=UUID(source["scene_version_id"]),
            )
        )
    await db.flush()


async def ensure_plan(db: AsyncSession, owner: UUID, cid: UUID, fence: WriteFence) -> None:
    rev = await context(db, fence.operation_id)
    if rev is None or await plan_binding(db, fence.operation_id) is not None:
        return
    if rev.kind == "adjust_outline":
        return
    repo = SnapshotRepository(db, owner)
    if rev.base_head is None:
        raise SnapshotError("STALE_COURSE_VERSION")
    base = await repo.get_version(cid, rev.base_head)
    old = await repo.get_plan(cid, UUID(base["plan_id"]))
    new = await repo.store_plan(
        cid,
        fence,
        expected_head=rev.base_head,
        key="revision-plan:" + str(fence.operation_id),
        candidate=old["candidate"],
    )
    await bind_plan(db, owner, cid, fence, UUID(new["plan_id"]))


async def next_step(
    db: AsyncSession, owner: UUID, cid: UUID, fence: WriteFence
) -> FreeCourseStep | None:
    pid = await plan_binding(db, fence.operation_id)
    if pid is None:
        return None
    repo = SnapshotRepository(db, owner)
    plan = await repo.get_plan(cid, pid)
    saved = await stages(db, fence.operation_id)
    steps = {
        str(s.scene_id): s
        for s in await visibility._steps(db, owner, cid, fence.operation_id)
        if s.scene_id
    }
    rev = await context(db, fence.operation_id)
    if rev is None:
        raise SnapshotError("NOT_FOUND")
    affected = (
        set(rev.impact_json["affected_scene_ids"])
        if rev.kind == "revise_scene"
        else {s["scene_id"] for s in plan["scenes"]}
    )
    for scene in plan["scenes"]:
        sid = scene["scene_id"]
        if sid not in affected or sid in saved:
            continue
        step = steps[sid]
        if step.state not in ("pending", "running"):
            continue
        if set(scene["depends_on"]) <= set(saved):
            return step
    return None


async def stage_validation(
    db: AsyncSession, owner: UUID, cid: UUID, fence: WriteFence, vid: UUID
) -> None:
    repo = SnapshotRepository(db, owner)
    rev = await context(db, fence.operation_id)
    prepared = await prepare_presentation(db, owner, cid, fence, validation_id=vid)
    validation = await db.get(FreeSceneValidation, vid)
    # Validation row records actual generator input separately; use its source identity.
    from app.models.free_scene_generation import FreeSceneGenerationResult

    if validation is None or rev is None:
        raise SnapshotError("NOT_FOUND")
    generated = await db.get(FreeSceneGenerationResult, validation.generation_result_id)
    body = cast(dict[str, Any] | None, validation.cleaned_json)
    if generated is None or body is None:
        raise SnapshotError("HARD_GATE_REJECTED")
    stored = await repo.store_scene(
        cid,
        fence,
        expected_head=rev.base_head,
        key="stage:" + str(vid),
        plan_id=generated.plan_id,
        scene_id=generated.scene_id,
        content=body["content"],
        actions=body["actions"],
        dependencies=body["dependencies"],
    )
    db.add(
        FreeCourseRevisionStage(
            user_id=owner,
            course_id=cid,
            operation_id=fence.operation_id,
            scene_id=generated.scene_id,
            scene_version_id=UUID(stored["scene_version_id"]),
            presentation_id=UUID(prepared["presentation_id"]),
        )
    )
    await db.flush()


async def publish(db: AsyncSession, owner: UUID, cid: UUID, fence: WriteFence) -> dict[str, Any]:
    repo = SnapshotRepository(db, owner)
    rev = await context(db, fence.operation_id)
    pid = await plan_binding(db, fence.operation_id)
    if rev is None or pid is None:
        raise SnapshotError("REVISION_INCOMPLETE")
    await repo._fence(cid, fence)
    course = await repo._course(cid, lock=True)
    await repo._expected(course, rev.base_head)
    plan = await repo.get_plan(cid, pid)
    saved = await stages(db, fence.operation_id)
    required = (
        set(rev.impact_json["affected_scene_ids"])
        if rev.kind == "revise_scene"
        else {s["scene_id"] for s in plan["scenes"]}
    )
    if not required <= set(saved):
        raise SnapshotError("REVISION_INCOMPLETE")
    base = (
        await repo.get_version(cid, rev.base_head)
        if rev.base_head
        else {"scenes": [], "node_links": []}
    )
    result = await repo.commit_manifest(
        cid,
        fence,
        expected_head=rev.base_head,
        key="revision-publish:" + str(fence.operation_id),
        plan_id=pid,
        bindings=[
            saved[s["scene_id"]].scene_version_id if s["scene_id"] in saved else None
            for s in plan["scenes"]
        ],
        node_links=base["node_links"] if rev.kind == "revise_scene" else [],
    )
    for step in await visibility._steps(db, owner, cid, fence.operation_id):
        if str(step.scene_id) not in saved:
            continue
        row = saved[str(step.scene_id)]
        step.state, step.reason_code = "ready", None
        step.scene_version_id, step.presentation_id = row.scene_version_id, row.presentation_id
    await db.flush()
    for scene in plan["scenes"]:
        if scene["scene_id"] not in saved:
            continue
        stage = saved[scene["scene_id"]]
        payload = dict(
            scene_id=scene["scene_id"], scene_version_id=str(stage.scene_version_id), state="ready"
        )
        await visibility._emit(db, owner, cid, fence, "scene_ready", result, payload)
        if (
            scene == plan["scenes"][0]
            and await db.scalar(
                select(FreeCourseEvent.id).where(
                    FreeCourseEvent.course_id == cid,
                    FreeCourseEvent.event_type == "first_scene_ready",
                )
            )
            is None
        ):
            await visibility._emit(db, owner, cid, fence, "first_scene_ready", result, payload)
    from app.services.free_course_effects import replacement_effects

    await replacement_effects(
        db, owner, cid, base, await repo.get_version(cid, result["version"]), required
    )
    await visibility._live(db, owner, cid, fence)
    return result


class Revisions:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def impact(
        self, owner: UUID, cid: UUID, *, kind: str, base: int | None, scene_id: UUID | None = None
    ) -> dict[str, Any]:
        async with self.sessions() as db:
            return await preview(db, owner, cid, kind=kind, base=base, scene_id=scene_id)

    async def start(
        self,
        owner: UUID,
        cid: UUID,
        *,
        kind: str,
        base: int | None,
        scene_id: UUID | None,
        instruction: str,
        impact_digest: str,
        key: str,
    ) -> dict[str, Any]:
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 4000:
            raise SnapshotError("INVALID_REVISION_INPUT")
        from app.services.free_course_recovery import Recovery
        from app.services.free_course_scheduler import ACTIVE, POLICY, Lease, Scheduler

        async with self.sessions() as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            await repo._course(cid, lock=True)
            route = f"/api/free-courses/{cid}/operations"
            fingerprint = digest(
                "revision-start",
                kind=kind,
                base=base,
                scene_id=str(scene_id) if scene_id else None,
                instruction=instruction,
                impact_digest=impact_digest,
            )
            replay = await repo._receipt(route, key, fingerprint)
            if replay is not None:
                return replay
            impact = await preview(db, owner, cid, kind=kind, base=base, scene_id=scene_id)
            if impact["impact_digest"] != impact_digest:
                raise SnapshotError("IMPACT_CHANGED")
            if await db.scalar(
                select(FreeCourseOperation.id).where(
                    FreeCourseOperation.user_id == owner, FreeCourseOperation.state.in_(ACTIVE)
                )
            ):
                raise SnapshotError("OPERATION_ACTIVE")
            if await Recovery(self.sessions)._unresolved(db, owner):
                raise SnapshotError("OUTCOME_UNRESOLVED")
            if base is not None:
                manifest = await repo.get_version(cid, base)
                oldplan = await repo.get_plan(cid, UUID(manifest["plan_id"]))
                old = await db.get(FreeCourseRequest, UUID(oldplan["request_id"]))
            else:
                old = await db.scalar(
                    select(FreeCourseRequest)
                    .where(FreeCourseRequest.user_id == owner, FreeCourseRequest.course_id == cid)
                    .order_by(FreeCourseRequest.version.desc())
                    .limit(1)
                )
            scheduler = Scheduler(self.sessions)
            remaining = await scheduler.budget(db, cid, UUID(int=0))
            if (
                remaining["course_attempts"] >= 40
                or remaining["course_input"] >= 600000
                or remaining["course_output"] >= 144000
            ):
                raise SnapshotError("BUDGET_EXHAUSTED")
            if old is None:
                raise SnapshotError("SNAPSHOT_CORRUPT")
            n = await db.scalar(
                select(func.max(FreeCourseRequest.version)).where(
                    FreeCourseRequest.course_id == cid
                )
            )
            payload = dict(
                request_text=instruction,
                kind="adjustment",
                profile_id=str(old.profile_id) if old.profile_id else None,
                profile_version=old.profile_version,
                evidence_snapshot=deepcopy(old.evidence_snapshot),
                nonsecret_config_snapshot=deepcopy(old.nonsecret_config_snapshot),
                parent_request_id=str(old.id),
            )
            req = FreeCourseRequest(
                user_id=owner,
                course_id=cid,
                version=(n or 0) + 1,
                schema_version=SCHEMA,
                digest=digest("request", **payload),
                **{**payload, "profile_id": old.profile_id, "parent_request_id": old.id},
            )
            db.add(req)
            await db.flush()
            op = FreeCourseOperation(
                user_id=owner,
                course_id=cid,
                request_id=req.id,
                kind=kind,
                base_head_version=base,
                config_snapshot=deepcopy(old.nonsecret_config_snapshot),
                policy_snapshot=deepcopy(POLICY),
            )
            db.add(op)
            await db.flush()
            db.add(
                FreeCourseRevision(
                    user_id=owner,
                    course_id=cid,
                    operation_id=op.id,
                    kind=kind,
                    base_head=base,
                    instruction=instruction,
                    impact_json=impact,
                    impact_digest=impact_digest,
                )
            )
            if kind == "adjust_outline":
                db.add(
                    FreeCourseStep(
                        user_id=owner,
                        course_id=cid,
                        operation_id=op.id,
                        step_key="plan",
                        state="pending",
                    )
                )
            await Scheduler(self.sessions)._event(
                db, Lease(owner, cid, WriteFence(op.id, 0, uuid4())), "queued", {}
            )
            return await repo._record(
                cid,
                route,
                key,
                fingerprint,
                dict(course_id=str(cid), operation_id=str(op.id)),
                status_code=202,
            )
