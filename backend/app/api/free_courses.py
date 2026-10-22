"""Owner-private free-course REST and durable read-only SSE; default mode stays closed."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from threading import BoundedSemaphore
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.core.product_mode import catalog_only
from app.models.auth import GuestSessionRecord
from app.models.free_course import FreeCourse, FreeCourseVersion
from app.services.free_course_answers import Answers, public_exercise
from app.services.free_course_contract import SCHEMAS, validate
from app.services.free_course_quality import Feedback, visibility_state
from app.services.free_course_recovery import Recovery
from app.services.free_course_revision import Revisions
from app.services.free_course_scheduler import Scheduler
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository
from app.services.free_scene_availability import read_events, read_ready_scene

router = APIRouter(prefix="/api/free-courses", tags=["Free Courses"])
Owner = Annotated[AuthenticatedSession, Depends(require_authenticated_session)]
Sessions = Annotated[async_sessionmaker[AsyncSession], Depends(database_session_factory)]
Key = Annotated[
    str, Header(min_length=1, max_length=128, pattern=r"^[ -~]+$", alias="Idempotency-Key")
]
STREAM_LIMIT = BoundedSemaphore(32)
TERMINAL = {
    "succeeded",
    "partially_succeeded",
    "awaiting_clarification",
    "failed",
    "cancelled",
    "timed_out",
}


def enabled() -> None:
    if catalog_only():
        raise AuthFailure(409, "FREE_COURSE_DISABLED", "Free course generation is disabled.")


def reply(schema: str, value: dict[str, Any], status: int = 200) -> JSONResponse:
    try:
        validate(schema, value)
    except SnapshotError:
        raise SnapshotError("PUBLIC_PROJECTION_INVALID") from None
    return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})


async def manifest(db: AsyncSession, owner: UUID, cid: UUID, version: int) -> dict[str, Any]:
    repo = SnapshotRepository(db, owner)
    raw = await repo.get_version(cid, version)
    row = await db.get(FreeCourseVersion, UUID(raw["id"]))
    if row is None:
        raise SnapshotError("NOT_FOUND")
    plan = await repo.get_plan(cid, UUID(raw["plan_id"]))
    titles = {s["scene_id"]: s["title"] for s in plan["scenes"]}
    return dict(
        course_id=str(cid),
        version=version,
        plan_id=raw["plan_id"],
        created_at=row.created_at.isoformat(),
        complete=all(s["scene_version_id"] for s in raw["scenes"]),
        scenes=[dict(**s, title=titles[s["scene_id"]]) for s in raw["scenes"]],
        node_links=[
            {k: link[k] for k in SCHEMAS["NodeLink"]["required"]} for link in raw["node_links"]
        ],
    )


@router.post("", status_code=201)
async def create(
    body: dict[str, Any], current: Owner, sessions: Sessions, idempotency_key: Key
) -> JSONResponse:
    enabled()
    validate("CreateCourse", body)
    code = body.get("code_language", "c")
    result = await Scheduler(sessions).enqueue(
        current.user.id,
        body["goal"],
        key=idempotency_key,
        teaching_language=body.get("teaching_language", "zh-CN"),
        code_language="C" if code == "c" else None,
    )
    return reply("CreatedCourse", result, 201)


@router.get("")
async def courses(
    current: Owner,
    sessions: Sessions,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
) -> JSONResponse:
    async with sessions() as db:
        query = select(FreeCourse).where(FreeCourse.user_id == current.user.id)
        if cursor:
            try:
                cid = UUID(cursor)
            except ValueError:
                raise SnapshotError("INVALID_CURSOR") from None
            anchor = await db.scalar(
                select(FreeCourse).where(
                    FreeCourse.id == cid, FreeCourse.user_id == current.user.id
                )
            )
            if anchor is None:
                raise SnapshotError("INVALID_CURSOR")
            query = query.where(
                tuple_(FreeCourse.created_at, FreeCourse.id) < (anchor.created_at, anchor.id)
            )
        rows = (
            await db.scalars(
                query.order_by(FreeCourse.created_at.desc(), FreeCourse.id.desc()).limit(limit + 1)
            )
        ).all()
        items = []
        for row in rows[:limit]:
            owned = await SnapshotRepository(db, current.user.id).get_course(row.id)
            items.append(
                dict(
                    course_id=str(row.id),
                    original_goal=row.original_goal,
                    course_kind=row.course_kind,
                    endorsement=row.endorsement,
                    head_version=owned["head_version"],
                    created_at=row.created_at.isoformat(),
                )
            )
        return reply(
            "CourseList",
            dict(items=items, next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None),
        )


@router.get("/{course_id}")
async def course(course_id: UUID, current: Owner, sessions: Sessions) -> JSONResponse:
    async with sessions() as db:
        owned = await SnapshotRepository(db, current.user.id).get_course(course_id)
        head = owned.pop("head_version")
        owned["code_language"] = "c" if owned["code_language"] == "C" else None
        return reply(
            "Course",
            dict(
                **owned, head=await manifest(db, current.user.id, course_id, head) if head else None
            ),
        )


@router.get("/{course_id}/versions")
async def versions(
    course_id: UUID,
    current: Owner,
    sessions: Sessions,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
) -> JSONResponse:
    async with sessions() as db:
        await SnapshotRepository(db, current.user.id).get_course(course_id)
        query = select(FreeCourseVersion).where(
            FreeCourseVersion.user_id == current.user.id, FreeCourseVersion.course_id == course_id
        )
        if cursor:
            if not re.fullmatch(r"[0-9]{1,10}", cursor) or int(cursor) < 1:
                raise SnapshotError("INVALID_CURSOR")
            await SnapshotRepository(db, current.user.id).get_version(course_id, int(cursor))
            query = query.where(FreeCourseVersion.version < int(cursor))
        rows = (
            await db.scalars(query.order_by(FreeCourseVersion.version.desc()).limit(limit + 1))
        ).all()
        return reply(
            "VersionList",
            dict(
                items=[
                    dict(version=r.version, created_at=r.created_at.isoformat())
                    for r in rows[:limit]
                ],
                next_cursor=str(rows[limit - 1].version) if len(rows) > limit else None,
            ),
        )


@router.get("/{course_id}/versions/{version}")
async def version(
    course_id: UUID, version: int, current: Owner, sessions: Sessions
) -> JSONResponse:
    if version < 1:
        raise SnapshotError("INVALID_API_INPUT")
    async with sessions() as db:
        return reply("Manifest", await manifest(db, current.user.id, course_id, version))


@router.get("/{course_id}/versions/{version}/scenes/{scene_id}")
async def scene(
    course_id: UUID, version: int, scene_id: UUID, current: Owner, sessions: Sessions
) -> JSONResponse:
    if version < 1:
        raise SnapshotError("INVALID_API_INPUT")
    async with sessions() as db:
        value = await read_ready_scene(
            db, current.user.id, course_id, version=version, scene_id=scene_id
        )
        blocks = []
        for block in value["blocks"]:
            if block["kind"] == "exercise":
                disabled = await visibility_state(
                    db,
                    current.user.id,
                    course_id,
                    UUID(value["scene_version_id"]),
                    block["anchor_id"],
                )
                blocks.append(
                    public_exercise(
                        current.user.id,
                        course_id,
                        scene_id,
                        UUID(value["scene_version_id"]),
                        block,
                        disabled=disabled,
                    )
                )
            elif block["kind"] == "code":
                blocks.append({**block, "language": "c"})
            else:
                blocks.append(block)
        value.update(blocks=blocks)
        value.pop("diagnostics", None)
        return reply("SceneProjection", value)


@router.post("/{course_id}/operations", status_code=202)
async def operation(
    course_id: UUID, body: dict[str, Any], current: Owner, sessions: Sessions, idempotency_key: Key
) -> JSONResponse:
    enabled()
    kind = body.get("kind")
    schema = {
        "clarify": "ClarifyRequest",
        "resume": "ResumeRequest",
        "revise_scene": "ReviseRequest",
        "adjust_outline": "AdjustRequest",
    }.get(str(kind))
    if schema is None:
        raise SnapshotError("INVALID_API_INPUT")
    validate(schema, body)
    if kind in ("resume", "clarify"):
        result = await Recovery(sessions).start(
            current.user.id,
            course_id,
            kind=kind,
            source_operation_id=UUID(body["source_operation_id"]),
            expected_head=body["expected_head_version"],
            supplement=body.get("supplement"),
            key=idempotency_key,
        )
    else:
        result = await Revisions(sessions).start(
            current.user.id,
            course_id,
            kind=str(kind),
            base=body["expected_head_version"],
            scene_id=UUID(body["scene_id"]) if kind == "revise_scene" else None,
            instruction=body["instruction"],
            impact_digest=body["impact_digest"],
            key=idempotency_key,
        )
    return reply("AcceptedOperation", result, 202)


@router.get("/{course_id}/operations/{operation_id}")
async def operation_read(
    course_id: UUID, operation_id: UUID, current: Owner, sessions: Sessions
) -> JSONResponse:
    return reply(
        "Operation",
        await Recovery(sessions).read_operation(current.user.id, course_id, operation_id),
    )


@router.post("/{course_id}/operations/{operation_id}/cancel")
async def cancel(
    course_id: UUID,
    operation_id: UUID,
    body: dict[str, Any],
    current: Owner,
    sessions: Sessions,
    idempotency_key: Key,
) -> JSONResponse:
    validate("CancelRequest", body)
    return reply(
        "Operation",
        await Recovery(sessions).cancel(
            current.user.id, course_id, operation_id, key=idempotency_key
        ),
    )


@router.get("/{course_id}/impact")
async def impact(
    course_id: UUID,
    current: Owner,
    sessions: Sessions,
    kind: str,
    base_version: int | None = Query(None, ge=1),
    scene_id: UUID | None = None,
) -> JSONResponse:
    if kind not in ("revise_scene", "adjust_outline"):
        raise SnapshotError("INVALID_API_INPUT")
    return reply(
        "Impact",
        await Revisions(sessions).impact(
            current.user.id, course_id, kind=kind, base=base_version, scene_id=scene_id
        ),
    )


@router.post("/{course_id}/feedback", status_code=201)
async def feedback(
    course_id: UUID, body: dict[str, Any], current: Owner, sessions: Sessions, idempotency_key: Key
) -> JSONResponse:
    return reply(
        "FeedbackReceipt",
        await Feedback(sessions).submit(current.user.id, course_id, body, key=idempotency_key),
        201,
    )


@router.get("/{course_id}/feedback/{feedback_id}")
async def feedback_read(
    course_id: UUID, feedback_id: UUID, current: Owner, sessions: Sessions
) -> JSONResponse:
    return reply("Feedback", await Feedback(sessions).read(current.user.id, course_id, feedback_id))


@router.post("/{course_id}/attempts", status_code=201)
async def attempt(
    course_id: UUID, body: dict[str, Any], current: Owner, sessions: Sessions, idempotency_key: Key
) -> JSONResponse:
    enabled()
    return reply(
        "AttemptReceipt",
        await Answers(sessions).submit(current.user.id, course_id, body, key=idempotency_key),
        201,
    )


@router.get("/{course_id}/attempts/{attempt_id}")
async def attempt_read(
    course_id: UUID, attempt_id: UUID, current: Owner, sessions: Sessions
) -> JSONResponse:
    return reply("Attempt", await Answers(sessions).read(current.user.id, course_id, attempt_id))


async def raw_event_frames(
    request: Request,
    sessions: async_sessionmaker[AsyncSession],
    owner: UUID,
    token: str,
    cid: UUID,
    oid: UUID,
    after: int,
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 60
    last = loop.time()
    while loop.time() < deadline and not await request.is_disconnected():
        async with sessions() as db:
            auth = await db.get(GuestSessionRecord, token)
            if (
                auth is None
                or auth.user_id != owner
                or auth.expires_at <= datetime.now(timezone.utc)
            ):
                return
            try:
                events = await read_events(db, owner, cid, oid, after=after)
            except SnapshotError:
                return
        view = await Recovery(sessions).read_operation(owner, cid, oid)
        for event in events:
            validate("Event", event)
            after = event["seq"]
            data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            yield f"id: {after}\nevent: {event['type']}\ndata: {data}\n\n"
        if view["state"] in TERMINAL and after >= view["last_event_id"]:
            return
        if loop.time() - last >= 15:
            yield ": keep-alive\n\n"
            last = loop.time()
        await asyncio.sleep(1)


async def event_frames(
    request: Request,
    sessions: async_sessionmaker[AsyncSession],
    owner: UUID,
    token: str,
    cid: UUID,
    oid: UUID,
    after: int,
) -> AsyncIterator[str]:
    try:
        async for frame in raw_event_frames(request, sessions, owner, token, cid, oid, after):
            yield frame
    finally:
        STREAM_LIMIT.release()


@router.get("/{course_id}/operations/{operation_id}/events", response_model=None)
async def events(
    course_id: UUID,
    operation_id: UUID,
    request: Request,
    current: Owner,
    sessions: Sessions,
    after: int | None = Query(None, ge=0, le=999999999999999999),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> Response:
    if last_event_id is not None and not re.fullmatch(r"[0-9]{1,18}", last_event_id):
        raise SnapshotError("INVALID_API_INPUT")
    last = int(last_event_id) if last_event_id is not None else None
    if after is not None and last is not None and after != last:
        raise SnapshotError("INVALID_API_INPUT")
    cursor = last if last is not None else after or 0
    async with sessions() as db:
        await read_events(db, current.user.id, course_id, operation_id, after=cursor)
    view = await Recovery(sessions).read_operation(current.user.id, course_id, operation_id)
    if view["state"] in TERMINAL and cursor == view["last_event_id"]:
        return Response(status_code=204, headers={"Cache-Control": "no-store"})
    if not STREAM_LIMIT.acquire(blocking=False):
        raise AuthFailure(503, "STREAM_CAPACITY", "Event stream capacity reached.")
    return StreamingResponse(
        event_frames(
            request,
            sessions,
            current.user.id,
            current.record.token_hash,
            course_id,
            operation_id,
            cursor,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
