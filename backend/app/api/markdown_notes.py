"""Cookie-protected, read-only Markdown download of reviewed learning notes."""

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.database import database_session_factory
from app.services.markdown_notes import NotesNotFound, build_markdown_notes

router = APIRouter(tags=["Export"])


@router.get("/api/learning-units/{unit_id}/notes.md")
async def download_markdown_notes(
    unit_id: UUID,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    sessions: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> Response:
    async with sessions() as db:
        try:
            notes = await build_markdown_notes(db, owner_id=current.user.id, unit_id=unit_id)
        except NotesNotFound:
            raise AuthFailure(404, "NOT_FOUND", "Learning notes not found.") from None
    return Response(
        content=notes.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="learning-notes-{unit_id}.md"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
