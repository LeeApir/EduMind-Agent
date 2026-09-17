"""Anonymous authentication API."""

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import (
    COOKIE_NAME,
    SESSION_LIFETIME_SECONDS,
    AuthenticatedSession,
    csrf_for_token,
    require_authenticated_session,
    token_hash,
    verify_origin,
)
from app.core.database import database_session_factory
from app.models.auth import GuestSessionRecord, User

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def session_payload(session: AuthenticatedSession) -> dict[str, object]:
    """Return non-secret identity and an in-memory CSRF token."""
    return {
        "user": {"id": str(session.user.id), "is_guest": session.user.is_guest},
        "csrf_token": session.csrf_token,
        "expires_at": session.record.expires_at.isoformat(),
    }


@router.post("/guest", status_code=201)
async def create_guest_session(
    request: Request,
    response: Response,
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> dict[str, object]:
    """Create an anonymous user and durable server-side session in one transaction."""
    verify_origin(request)
    now = datetime.now(timezone.utc)
    token = token_urlsafe(32)
    user = User(is_guest=True, email=None, password_hash=None)
    async with session_factory() as db:
        db.add(user)
        await db.flush()
        record = GuestSessionRecord(
            token_hash=token_hash(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(seconds=SESSION_LIFETIME_SECONDS),
        )
        db.add(record)
        await db.commit()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_LIFETIME_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return session_payload(
        AuthenticatedSession(user=user, record=record, csrf_token=csrf_for_token(token))
    )


@router.get("/session")
async def get_current_session(
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
) -> dict[str, object]:
    """Recover identity and the CSRF token after a page reload."""
    response.headers["Cache-Control"] = "no-store"
    return session_payload(current)
