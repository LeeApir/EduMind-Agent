"""Cookie-protected MP4/SRT reads from owner-bound reviewed animation media."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator, Callable
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.background import BackgroundTask

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.services.animation_cache import AnimationCache
from app.services.animation_media import (
    MediaUnavailable,
    VerifiedMediaFile,
    open_verified_media,
    owned_reviewed_media,
)

router = APIRouter(tags=["Animation"])

_pread = cast(Callable[[int, int, int], bytes] | None, getattr(os, "pread", None))


def _read_at(fd: int, count: int, offset: int) -> bytes:
    """Read ``count`` bytes at ``offset``; ``pread`` where available, seek+read otherwise.

    ``os.pread`` is POSIX-only and leaves the descriptor offset untouched; the
    Windows fallback seeks before reading. This generator is the sole reader of
    its descriptor, so the seek is safe.
    """
    if _pread is not None:
        return _pread(fd, count, offset)
    os.lseek(fd, offset, os.SEEK_SET)
    return os.read(fd, count)


def _range(value: str | None, size: int) -> tuple[int, int] | None:
    if value is None:
        return 0, size - 1
    match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", value)
    if match is None or (not match.group(1) and not match.group(2)):
        return None
    start_text, end_text = match.groups()
    if start_text:
        start = int(start_text)
        if start >= size:
            return None
        end = min(int(end_text), size - 1) if end_text else size - 1
        return (start, end) if end >= start else None
    suffix = int(end_text)
    return (max(0, size - suffix), size - 1) if suffix > 0 else None


async def _chunks(file: VerifiedMediaFile, *, start: int, end: int) -> AsyncIterator[bytes]:
    offset = start
    try:
        while offset <= end:
            chunk = await asyncio.to_thread(_read_at, file.fd, min(65536, end - offset + 1), offset)
            if not chunk:
                return
            offset += len(chunk)
            yield chunk
    finally:
        file.close()


async def _read_media(
    media_id: UUID, *, extension: str, download: bool, range_header: str | None,
    current: AuthenticatedSession, sessions: async_sessionmaker[AsyncSession],
) -> StreamingResponse | JSONResponse:
    async with sessions() as db:
        media = await owned_reviewed_media(
            db, owner_id=current.user.id, media_id=media_id,
        )
        if media is None:
            raise AuthFailure(404, "NOT_FOUND", "Animation media not found.")
    try:
        file = await asyncio.to_thread(
            open_verified_media, media, extension=extension, cache=AnimationCache(),
        )
    except MediaUnavailable:
        raise AuthFailure(503, "MEDIA_UNAVAILABLE", "Animation media is unavailable.") from None
    bounds = _range(range_header, file.size) if extension == "mp4" else (0, file.size - 1)
    if bounds is None:
        file.close()
        return JSONResponse(
            status_code=416,
            content={
                "code": "RANGE_NOT_SATISFIABLE", "message": "Requested range is unavailable.",
                "retryable": False,
            },
            headers={"Content-Range": f"bytes */{file.size}", "Cache-Control": "private, no-store"},
        )
    start, end = bounds
    partial = extension == "mp4" and range_header is not None
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": (
            f'{"attachment" if download else "inline"}; filename="animation-{media_id}.{extension}"'
        ),
        "Content-Length": str(end - start + 1),
    }
    if extension == "mp4":
        headers["Accept-Ranges"] = "bytes"
        if partial:
            headers["Content-Range"] = f"bytes {start}-{end}/{file.size}"
    return StreamingResponse(
        _chunks(file, start=start, end=end),
        status_code=206 if partial else 200,
        media_type="video/mp4" if extension == "mp4" else "application/x-subrip",
        headers=headers,
        background=BackgroundTask(file.close),
    )


@router.get("/api/animation-media/{media_id}/mp4", response_model=None)
async def animation_mp4(
    media_id: UUID, download: bool = False,
    range_header: str | None = Header(default=None, alias="Range"),
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> StreamingResponse | JSONResponse:
    return await _read_media(
        media_id, extension="mp4", download=download, range_header=range_header,
        current=current, sessions=sessions,
    )


@router.get("/api/animation-media/{media_id}/srt", response_model=None)
async def animation_srt(
    media_id: UUID, download: bool = False,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> StreamingResponse | JSONResponse:
    return await _read_media(
        media_id, extension="srt", download=download, range_header=None,
        current=current, sessions=sessions,
    )
