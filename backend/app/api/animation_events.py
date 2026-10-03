"""Bounded owner-scoped SSE replay of durable animation Job events."""

from __future__ import annotations

import asyncio
import json
import re
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.models.animation import AnimationJobEvent
from app.models.auth import GuestSessionRecord
from app.services.animation_jobs import (
    AnimationEventCursorExpired,
    AnimationEventCursorInvalid,
    AnimationTargetUnavailable,
    replay_animation_events,
)

router = APIRouter(tags=["Animation"])
_STREAM_LIMIT = threading.BoundedSemaphore(32)
_POLL_SECONDS = 1.5
_MAX_STREAM_SECONDS = 300
_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


def _frame(event: AnimationJobEvent) -> str:
    data = {"job_id": str(event.job_id), **event.payload}
    if event.event_type in {"queued", "running", "succeeded", "failed", "cancelled"}:
        data["status"] = event.event_type
    elif event.event_type == "recovered":
        data["status"] = "queued" if event.payload.get("stage") == "queued" else "failed"
    return (
        f"id: {event.event_id}\nevent: {event.event_type}\n"
        f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


async def _events(
    request: Request, sessions: async_sessionmaker[AsyncSession],
    *, owner_id: UUID, token_hash: str, job_id: UUID, after: int,
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _MAX_STREAM_SECONDS
    last_comment = loop.time()
    cursor = after
    try:
        while loop.time() < deadline and not await request.is_disconnected():
            async with sessions() as db:
                auth = await db.get(GuestSessionRecord, token_hash)
                if (
                    auth is None or auth.user_id != owner_id
                    or auth.expires_at <= datetime.now(timezone.utc)
                ):
                    return
                try:
                    job, events = await replay_animation_events(
                        db, owner_id=owner_id, job_id=job_id, after=cursor,
                    )
                except (AnimationTargetUnavailable, AnimationEventCursorExpired):
                    return
                terminal = job.status in _TERMINAL
                watermark = job.last_event_id
            for event in events:
                cursor = event.event_id
                yield _frame(event)
            if terminal and cursor >= watermark:
                return
            if loop.time() - last_comment >= 15:
                yield ": keep-alive\n\n"
                last_comment = loop.time()
            await asyncio.sleep(_POLL_SECONDS)
    finally:
        _STREAM_LIMIT.release()


@router.get("/api/animation-jobs/{job_id}/events")
async def animation_job_events(
    job_id: UUID, request: Request,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    after: int | None = Query(default=None, ge=0, le=999999999999999999),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> StreamingResponse:
    if last_event_id is not None and not re.fullmatch(r"[0-9]{1,18}", last_event_id):
        raise AuthFailure(409, "EVENT_CURSOR_INVALID", "Invalid animation event cursor.")
    cursor = int(last_event_id) if last_event_id is not None else (after or 0)
    async with sessions() as db:
        try:
            await replay_animation_events(db, owner_id=current.user.id, job_id=job_id, after=cursor)
        except AnimationTargetUnavailable:
            raise AuthFailure(404, "NOT_FOUND", "Animation job not found.") from None
        except AnimationEventCursorInvalid:
            raise AuthFailure(
                409, "EVENT_CURSOR_INVALID", "Invalid animation event cursor."
            ) from None
        except AnimationEventCursorExpired:
            raise AuthFailure(
                410, "EVENT_CURSOR_EXPIRED", "Animation event cursor expired."
            ) from None
    if not _STREAM_LIMIT.acquire(blocking=False):
        raise AuthFailure(503, "STREAM_CAPACITY", "Animation event stream is busy.")
    return StreamingResponse(
        _events(
            request, sessions, owner_id=current.user.id,
            token_hash=current.record.token_hash, job_id=job_id, after=cursor,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
