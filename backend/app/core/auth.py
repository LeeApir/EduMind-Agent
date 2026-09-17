"""Opaque cookie authentication and CSRF checks."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import database_session_factory
from app.models.auth import GuestSessionRecord, User

COOKIE_NAME = "edumind_session"
SESSION_LIFETIME_SECONDS = 2 * 60 * 60
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AuthFailure(Exception):
    """Safe, structured authentication failure without secret material."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    user: User
    record: GuestSessionRecord
    csrf_token: str


def token_hash(token: str) -> str:
    """Hash a bearer secret with domain separation before database lookup."""
    return sha256(b"edumind-session:" + token.encode("utf-8")).hexdigest()


def csrf_for_token(token: str) -> str:
    """Derive a separate token so page reload can recover it without storing plaintext."""
    return sha256(b"edumind-csrf:" + token.encode("utf-8")).hexdigest()


def verify_origin(request: Request) -> None:
    """Reject browser requests from another origin, including same-site subdomains."""
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise AuthFailure(403, "CSRF_FAILED", "Cross-origin request rejected.")
    origin = request.headers.get("origin")
    if origin is None:
        return
    parsed = urlsplit(origin)
    expected = urlsplit(str(request.base_url))
    if (
        not parsed.scheme
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (parsed.scheme, parsed.netloc) != (expected.scheme, expected.netloc)
    ):
        raise AuthFailure(403, "CSRF_FAILED", "Cross-origin request rejected.")


def verify_csrf(request: Request, session_token: str) -> None:
    """Require a non-simple header on every authenticated write request."""
    if request.method not in UNSAFE_METHODS:
        return
    verify_origin(request)
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied or not compare_digest(supplied, csrf_for_token(session_token)):
        raise AuthFailure(403, "CSRF_FAILED", "CSRF token missing or invalid.")


async def require_authenticated_session(
    request: Request,
    session_factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> AuthenticatedSession:
    """Resolve current user from a valid, unexpired database-backed cookie."""
    session_token = request.cookies.get(COOKIE_NAME)
    if not session_token:
        raise AuthFailure(401, "UNAUTHORIZED", "Session missing or expired.")
    async with session_factory() as db:
        result = await db.execute(
            select(GuestSessionRecord, User)
            .join(User, User.id == GuestSessionRecord.user_id)
            .where(GuestSessionRecord.token_hash == token_hash(session_token))
        )
        row = result.one_or_none()
    if row is None or row[0].expires_at <= datetime.now(timezone.utc):
        raise AuthFailure(401, "UNAUTHORIZED", "Session missing or expired.")
    verify_csrf(request, session_token)
    return AuthenticatedSession(
        user=row[1], record=row[0], csrf_token=csrf_for_token(session_token)
    )
