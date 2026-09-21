"""Anonymous cookie authentication and CSRF regression tests."""

import asyncio
import os
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.auth import (
    AuthenticatedSession,
    AuthFailure,
    require_authenticated_session,
    token_hash,
)
from app.core.database import create_database_engine
from app.main import app, auth_failure_handler
from app.models.auth import GuestSessionRecord, User

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    yield TEST_DATABASE_URL


def test_guest_cookie_persists_identity_without_exposing_secret(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/auth/guest", headers={"Origin": "https://testserver"})
        assert response.status_code == 201
        cookie = response.cookies["edumind_session"]
        assert cookie not in response.text
        assert cookie not in str(response.request.url)
        assert cookie not in caplog.text
        assert response.json()["user"]["is_guest"] is True
        assert len(response.json()["csrf_token"]) == 64
        assert response.headers["cache-control"] == "no-store"
        set_cookie = response.headers["set-cookie"].lower()
        assert "secure" in set_cookie
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
        assert "domain=" not in set_cookie
        assert response.json()["user"]["id"] not in set_cookie
        recovered = client.get("/api/auth/session")
        assert recovered.status_code == 200
        assert recovered.json() == response.json()

    with TestClient(app, base_url="https://testserver") as restarted_client:
        restarted = restarted_client.get(
            "/api/auth/session", cookies={"edumind_session": cookie}
        )
        assert restarted.status_code == 200
        assert restarted.json() == response.json()


def test_missing_and_unknown_cookie_are_rejected(database_url: str) -> None:
    with TestClient(app, base_url="https://testserver") as client:
        missing = client.get("/api/auth/session")
        unknown = client.get("/api/auth/session", cookies={"edumind_session": "unknown"})
    assert missing.status_code == 401
    assert unknown.status_code == 401
    assert missing.json()["code"] == "UNAUTHORIZED"


def test_session_is_hashed_and_expiry_enforced(database_url: str) -> None:
    with TestClient(app, base_url="https://testserver") as client:
        created = client.post("/api/auth/guest")
        assert created.status_code == 201
        raw_token = created.cookies["edumind_session"]
        user_id = created.json()["user"]["id"]
        async def check_and_expire() -> None:
            engine = create_database_engine(database_url)
            try:
                async with engine.begin() as connection:
                    saved = await connection.execute(
                        select(GuestSessionRecord.token_hash, User.is_guest, User.email)
                        .join(User, User.id == GuestSessionRecord.user_id)
                        .where(GuestSessionRecord.token_hash == token_hash(raw_token))
                    )
                    row = saved.one()
                    assert row.token_hash != raw_token
                    assert row.is_guest is True
                    assert row.email is None
                    await connection.execute(
                        update(GuestSessionRecord)
                        .where(GuestSessionRecord.token_hash == token_hash(raw_token))
                        .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                    )
            finally:
                await engine.dispose()

        asyncio.run(check_and_expire())
        assert user_id not in raw_token
        expired = client.get("/api/auth/session")
        assert expired.status_code == 401


def test_cross_origin_guest_creation_is_rejected(database_url: str) -> None:
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/auth/guest", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_FAILED"
    assert "set-cookie" not in response.headers


def test_authenticated_writes_require_origin_and_csrf_header(database_url: str) -> None:
    protected = FastAPI()
    protected.add_exception_handler(AuthFailure, auth_failure_handler)  # type: ignore[arg-type]

    @protected.post("/protected")
    async def protected_write(
        current: AuthenticatedSession = Depends(require_authenticated_session),
    ) -> dict[str, str]:
        return {"user_id": str(current.user.id)}

    with TestClient(app, base_url="https://testserver") as client:
        created = client.post("/api/auth/guest")
        token = created.cookies["edumind_session"]
        csrf = created.json()["csrf_token"]
    with TestClient(protected, base_url="https://testserver") as client:
        cookies = {"edumind_session": token}
        missing = client.post("/protected", cookies=cookies)
        invalid = client.post(
            "/protected", cookies=cookies, headers={"X-CSRF-Token": "wrong"}
        )
        foreign = client.post(
            "/protected",
            cookies=cookies,
            headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
        )
        allowed = client.post(
            "/protected",
            cookies=cookies,
            headers={"X-CSRF-Token": csrf, "Origin": "https://testserver"},
        )
    assert [missing.status_code, invalid.status_code, foreign.status_code] == [403, 403, 403]
    assert allowed.status_code == 200
    assert allowed.json()["user_id"] == created.json()["user"]["id"]
