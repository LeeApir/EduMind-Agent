"""Atomic incremental learning commits; no HTTP, Provider, scheduler or semantic approval."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.free_course_planning import validate_response as validate_plan
from app.models.free_course import FreeCourseVersion
from app.models.free_course_progress import FreeCourseEvent, FreeCourseStep
from app.models.free_course_writes import FreeCourseOperation
from app.models.free_scene_actions import FreeScenePresentation
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.models.free_scene_validation import FreeSceneValidation
from app.services.free_course_graph_links import suggest_node_links
from app.services.free_course_planning import load_inputs as load_request
from app.services.free_course_snapshots import (
    SnapshotError,
    SnapshotRepository,
    WriteFence,
    canonical,
    digest,
)
from app.services.free_scene_actions import prepare_presentation

EVENT_SCHEMA = json.loads(Path(__file__).with_suffix(".events.json").read_text())
FAILURES = {
    "SCHEMA_INVALID",
    "DEPENDENCY_UNAVAILABLE",
    "PROVIDER_REJECTED",
    "OUTCOME_UNKNOWN",
    "BUDGET_EXHAUSTED",
    "DEADLINE_EXCEEDED",
    "LEASE_LOST",
    "CANCELLED",
}


async def _live(db: AsyncSession, owner: UUID, cid: UUID, fence: WriteFence) -> None:
    changed = await db.scalar(
        update(FreeCourseOperation)
        .where(
            FreeCourseOperation.id == fence.operation_id,
            FreeCourseOperation.user_id == owner,
            FreeCourseOperation.course_id == cid,
            FreeCourseOperation.state == "running",
            FreeCourseOperation.lease_epoch == fence.epoch,
            FreeCourseOperation.lease_token == fence.token,
            FreeCourseOperation.cancel_requested_at.is_(None),
            FreeCourseOperation.lease_expires_at > func.clock_timestamp(),
            FreeCourseOperation.deadline_at > func.clock_timestamp(),
        )
        .values(state="running")
        .returning(FreeCourseOperation.id)
        .execution_options(synchronize_session="fetch")
    )
    if changed is None:
        raise SnapshotError("OPERATION_FENCED")


async def _emit(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    fence: WriteFence,
    kind: str,
    version: dict[str, Any],
    payload: dict[str, Any],
) -> int:
    seq = (
        await db.scalar(
            select(func.max(FreeCourseEvent.seq)).where(
                FreeCourseEvent.operation_id == fence.operation_id,
            )
        )
        or 0
    ) + 1
    event = dict(
        schema_version="free-course-events-v1",
        operation_id=str(fence.operation_id),
        seq=seq,
        type=kind,
        course_version=version["version"],
        payload=payload,
    )
    Draft202012Validator(EVENT_SCHEMA).validate(event)
    if seq > 256 or len(canonical(event)) > 4096:
        raise SnapshotError("EVENT_LIMIT_EXCEEDED")
    db.add(
        FreeCourseEvent(
            user_id=owner,
            course_id=cid,
            operation_id=fence.operation_id,
            seq=seq,
            event_type=kind,
            course_version_id=UUID(version["version_id"]),
            payload=payload,
        )
    )
    await db.flush()
    return seq


async def _steps(db: AsyncSession, owner: UUID, cid: UUID, oid: UUID) -> list[FreeCourseStep]:
    return list(
        (
            await db.scalars(
                select(FreeCourseStep)
                .where(
                    FreeCourseStep.user_id == owner,
                    FreeCourseStep.course_id == cid,
                    FreeCourseStep.operation_id == oid,
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    )


async def commit_outline(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    fence: WriteFence,
    *,
    plan_id: UUID,
    key: str,
    graph_version: str | None = None,
) -> dict[str, Any]:
    """Publish a complete empty manifest/step list, never a first learnable scene."""
    repo = SnapshotRepository(db, owner)
    route = f"availability:outline:{cid}"
    fingerprint = digest(
        "outline-commit",
        operation_id=str(fence.operation_id),
        plan_id=str(plan_id),
        graph_version=graph_version,
    )
    async with db.begin_nested():
        await repo._owner_lock()
        course = await repo._course(cid, lock=True)
        replay = await repo._receipt(route, key, fingerprint)
        if replay is not None:
            return replay
        operation = await repo._fence(cid, fence)
        if operation.kind not in {"create", "clarify", "resume"}:
            raise SnapshotError("ATOMIC_REVISION_REQUIRED")
        await repo._expected(course, None)
        plan = await repo.get_plan(cid, plan_id)
        inputs = await load_request(db, owner, cid, fence.operation_id)
        if plan["request_id"] != inputs["request_id"]:
            raise SnapshotError("PLAN_BINDING_MISMATCH")
        validate_plan(
            dict(
                needs_clarification=False,
                plan=plan["candidate"],
                questions=[],
                reason=None,
                source_keys=[],
            ),
            inputs,
        )
        links = (
            (await suggest_node_links(db, owner, cid, plan_id, graph_version=graph_version))[
                "links"
            ]
            if graph_version
            else []
        )
        result = await repo.commit_manifest(
            cid,
            fence,
            expected_head=None,
            key=f"outline:{fence.operation_id}",
            plan_id=plan_id,
            bindings=[None] * len(plan["scenes"]),
            node_links=links,
        )
        for scene in plan["scenes"]:
            db.add(
                FreeCourseStep(
                    user_id=owner,
                    course_id=cid,
                    operation_id=fence.operation_id,
                    plan_id=plan_id,
                    scene_id=UUID(scene["scene_id"]),
                    step_key="scene:" + scene["scene_key"],
                    state="pending",
                )
            )
        await db.flush()
        seq = await _emit(db, owner, cid, fence, "outline_ready", result, {})
        await _live(db, owner, cid, fence)
        return await repo._record(cid, route, key, fingerprint, {**result, "last_event_id": seq})


async def commit_scene(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    fence: WriteFence,
    *,
    validation_id: UUID,
    expected_head: int,
    key: str,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    repo = SnapshotRepository(db, owner)
    route = f"availability:scene:{cid}"
    fingerprint = digest(
        "ready-commit",
        operation_id=str(fence.operation_id),
        validation_id=str(validation_id),
        expected_head=expected_head,
        fallback_reason=fallback_reason,
    )
    async with db.begin_nested():
        await repo._owner_lock()
        course = await repo._course(cid, lock=True)
        replay = await repo._receipt(route, key, fingerprint)
        if replay is not None:
            return replay
        operation = await repo._fence(cid, fence)
        if operation.kind not in {"create", "clarify", "resume"}:
            raise SnapshotError("ATOMIC_REVISION_REQUIRED")
        await repo._expected(course, expected_head)
        prepared = await prepare_presentation(
            db, owner, cid, fence, validation_id=validation_id, fallback_reason=fallback_reason
        )
        validation = await db.get(FreeSceneValidation, validation_id)
        if validation is None:
            raise SnapshotError("NOT_FOUND")
        source = await db.get(FreeSceneGenerationResult, validation.generation_result_id)
        if source is None or source.expected_head != expected_head:
            raise SnapshotError("STALE_COURSE_VERSION")
        manifest = await repo.get_version(cid, expected_head)
        if manifest["plan_id"] != str(source.plan_id):
            raise SnapshotError("PLAN_BINDING_MISMATCH")
        steps = await _steps(db, owner, cid, fence.operation_id)
        step = next(
            (s for s in steps if s.scene_id == source.scene_id and s.plan_id == source.plan_id),
            None,
        )
        if step is None:
            raise SnapshotError("STEP_NOT_FOUND")
        if step.state == "ready":
            raise SnapshotError("SCENE_ALREADY_READY")
        if step.state not in {"pending", "running"}:
            raise SnapshotError("DEPENDENCY_UNAVAILABLE")
        body = cast(dict[str, Any] | None, validation.cleaned_json)
        if body is None:
            raise SnapshotError("HARD_GATE_REJECTED")
        stored = await repo.store_scene(
            cid,
            fence,
            expected_head=expected_head,
            key=f"ready:{source.id}",
            plan_id=source.plan_id,
            scene_id=source.scene_id,
            content=body["content"],
            actions=body["actions"],
            dependencies=body["dependencies"],
        )
        scene_version_id = UUID(stored["scene_version_id"])
        bindings: list[UUID | None] = []
        for binding in manifest["scenes"]:
            if binding["scene_id"] == str(source.scene_id):
                if binding["scene_version_id"] is not None:
                    raise SnapshotError("SCENE_ALREADY_READY")
                bindings.append(scene_version_id)
            else:
                bindings.append(
                    UUID(binding["scene_version_id"]) if binding["scene_version_id"] else None
                )
        result = await repo.commit_manifest(
            cid,
            fence,
            expected_head=expected_head,
            key=f"ready-manifest:{source.id}",
            plan_id=source.plan_id,
            bindings=bindings,
            node_links=manifest["node_links"],
        )
        step.state, step.reason_code = "ready", None
        step.scene_version_id, step.presentation_id = (
            scene_version_id,
            UUID(prepared["presentation_id"]),
        )
        await db.flush()
        payload = dict(
            scene_id=str(source.scene_id), scene_version_id=str(scene_version_id), state="ready"
        )
        seq = await _emit(db, owner, cid, fence, "scene_ready", result, payload)
        is_first = manifest["scenes"][0]["scene_id"] == str(source.scene_id)
        prior_first = await db.scalar(
            select(FreeCourseEvent.id).where(
                FreeCourseEvent.course_id == cid, FreeCourseEvent.event_type == "first_scene_ready"
            )
        )
        if is_first and prior_first is None:
            seq = await _emit(db, owner, cid, fence, "first_scene_ready", result, payload)
        await _live(db, owner, cid, fence)
        return await repo._record(
            cid,
            route,
            key,
            fingerprint,
            {**result, "scene_version_id": str(scene_version_id), "last_event_id": seq},
        )


async def fail_scene(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    fence: WriteFence,
    *,
    scene_id: UUID,
    expected_head: int,
    reason_code: str,
    key: str,
) -> dict[str, Any]:
    if reason_code not in FAILURES:
        raise SnapshotError("FAILURE_REASON_INVALID")
    repo = SnapshotRepository(db, owner)
    route = f"availability:failure:{cid}"
    fingerprint = digest(
        "step-failure",
        operation_id=str(fence.operation_id),
        scene_id=str(scene_id),
        expected_head=expected_head,
        reason_code=reason_code,
    )
    async with db.begin_nested():
        await repo._owner_lock()
        course = await repo._course(cid, lock=True)
        replay = await repo._receipt(route, key, fingerprint)
        if replay is not None:
            return replay
        await repo._fence(cid, fence)
        await repo._expected(course, expected_head)
        manifest = await repo.get_version(cid, expected_head)
        plan = await repo.get_plan(cid, UUID(manifest["plan_id"]))
        steps = await _steps(db, owner, cid, fence.operation_id)
        target = next((s for s in steps if s.scene_id == scene_id), None)
        if target is None:
            raise SnapshotError("NOT_FOUND")
        if target.state == "ready":
            raise SnapshotError("SCENE_ALREADY_READY")
        affected = {str(scene_id)}
        for scene in plan["scenes"]:
            if set(scene["depends_on"]) & affected:
                affected.add(scene["scene_id"])
        for step in steps:
            if str(step.scene_id) not in affected or step.state == "ready":
                continue
            step.state = "failed" if step.scene_id == scene_id else "blocked_dependency"
            step.reason_code = (
                reason_code if step.scene_id == scene_id else "DEPENDENCY_UNAVAILABLE"
            )
        await db.flush()
        result = dict(version=expected_head, version_id=manifest["id"])
        seq = await _emit(
            db,
            owner,
            cid,
            fence,
            "error",
            result,
            dict(scene_id=str(scene_id), reason_code=reason_code),
        )
        await _live(db, owner, cid, fence)
        return await repo._record(cid, route, key, fingerprint, {**result, "last_event_id": seq})


async def read_availability(
    db: AsyncSession, owner: UUID, cid: UUID, *, version: int
) -> dict[str, Any]:
    manifest = await SnapshotRepository(db, owner).get_version(cid, version)
    admitted = list(
        (
            await db.scalars(
                select(FreeCourseStep)
                .where(
                    FreeCourseStep.user_id == owner,
                    FreeCourseStep.course_id == cid,
                    FreeCourseStep.plan_id == UUID(manifest["plan_id"]),
                )
                .order_by(FreeCourseStep.created_at.desc(), FreeCourseStep.id.desc())
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    from app.services.free_course_quality import visibility_state

    scenes = []
    for item in manifest["scenes"]:
        ready = next(
            (
                s
                for s in admitted
                if str(s.scene_version_id) == item["scene_version_id"] and s.state == "ready"
            ),
            None,
        )
        step = next((s for s in admitted if str(s.scene_id) == item["scene_id"]), None)
        disabled = bool(item["scene_version_id"]) and await visibility_state(
            db, owner, cid, UUID(item["scene_version_id"])
        )
        scenes.append(
            dict(
                **item,
                content_state="ready" if ready and not disabled else "not_ready",
                generation_state=step.state if step else "pending",
                reason_code="CONTENT_UNAVAILABLE"
                if disabled
                else (step.reason_code if step else None),
            )
        )
    count = sum(s["content_state"] == "ready" for s in scenes)
    return dict(
        course_id=str(cid),
        course_version=version,
        scenes=scenes,
        ready_count=count,
        all_scenes_ready=count == len(scenes),
    )


async def read_ready_scene(
    db: AsyncSession, owner: UUID, cid: UUID, *, version: int, scene_id: UUID
) -> dict[str, Any]:
    availability = await read_availability(db, owner, cid, version=version)
    binding = next((s for s in availability["scenes"] if s["scene_id"] == str(scene_id)), None)
    if binding and binding["reason_code"] == "CONTENT_UNAVAILABLE":
        raise SnapshotError("CONTENT_UNAVAILABLE")
    if binding is None or binding["content_state"] != "ready":
        raise SnapshotError("SCENE_NOT_READY")
    step = await db.scalar(
        select(FreeCourseStep)
        .where(
            FreeCourseStep.user_id == owner,
            FreeCourseStep.course_id == cid,
            FreeCourseStep.scene_version_id == UUID(binding["scene_version_id"]),
            FreeCourseStep.state == "ready",
        )
        .execution_options(populate_existing=True)
    )
    if step is None:
        raise SnapshotError("SCENE_NOT_READY")
    row = await db.get(FreeScenePresentation, step.presentation_id)
    if row is None or row.presentation_digest != row.presentation_json.get("digest"):
        raise SnapshotError("SNAPSHOT_CORRUPT")
    from app.services.free_scene_actions import initial_state

    initial_state(row.presentation_json)  # Recheck the stored presentation body digest.
    from app.services.free_course_quality import visibility_state

    blocks: Any = deepcopy(row.presentation_json["blocks"])
    for block in blocks:
        if block["kind"] == "exercise" and await visibility_state(
            db, owner, cid, UUID(binding["scene_version_id"]), block["anchor_id"]
        ):
            block["disabled"] = True
            block["reason_code"] = "CONTENT_UNAVAILABLE"
            block["items"] = []
    return dict(
        course_id=str(cid),
        course_version=version,
        scene_id=str(scene_id),
        scene_version_id=binding["scene_version_id"],
        blocks=blocks,
        actions=deepcopy(row.presentation_json["timeline"]),
        diagnostics=deepcopy(row.presentation_json["diagnostics"]),
    )


async def read_events(
    db: AsyncSession, owner: UUID, cid: UUID, operation_id: UUID, *, after: int = 0
) -> list[dict[str, Any]]:
    await SnapshotRepository(db, owner).get_course(cid)
    operation = await db.scalar(
        select(FreeCourseOperation.id).where(
            FreeCourseOperation.user_id == owner,
            FreeCourseOperation.course_id == cid,
            FreeCourseOperation.id == operation_id,
        )
    )
    if operation is None:
        raise SnapshotError("NOT_FOUND")
    if type(after) is not int or after < 0:
        raise SnapshotError("EVENT_CURSOR_INVALID")
    last = (
        await db.scalar(
            select(func.max(FreeCourseEvent.seq)).where(
                FreeCourseEvent.operation_id == operation_id
            )
        )
    ) or 0
    if after > last:
        raise SnapshotError("EVENT_CURSOR_AHEAD")
    rows = (
        await db.execute(
            select(FreeCourseEvent, FreeCourseVersion.version)
            .outerjoin(FreeCourseVersion, FreeCourseVersion.id == FreeCourseEvent.course_version_id)
            .where(
                FreeCourseEvent.user_id == owner,
                FreeCourseEvent.course_id == cid,
                FreeCourseEvent.operation_id == operation_id,
                FreeCourseEvent.seq > after,
            )
            .order_by(FreeCourseEvent.seq)
        )
    ).all()
    return [
        dict(
            schema_version="free-course-events-v1",
            operation_id=str(operation_id),
            seq=e.seq,
            type=e.event_type,
            course_version=v,
            payload=deepcopy(e.payload),
        )
        for e, v in rows
    ]
