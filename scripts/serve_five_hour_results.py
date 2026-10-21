"""Loopback-only read-only browser access to one real isolated run result; no generation."""

# ruff: noqa: E402
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from secrets import token_urlsafe
import sys
from uuid import UUID

from run_five_hour_acceptance import (
    PRIVATE,
    authorize,
    isolated_environment,
    verify_database,
    read_json,
    require,
)
from app.core.auth import COOKIE_NAME, token_hash
from app.core.database import create_database_engine
from app.main import app
from app.models.auth import GuestSessionRecord
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker
import uvicorn


def readonly_app(upstream, result, token):
    unit = (result.get("result") or {}).get("learning_unit_id")
    # Failed/pending operations still have a unit in the persisted operation record;
    # only the exact ID, when known, is allowed. The server enforces visibility.
    unit = unit or result.get("learning_unit_id")
    oid = result["operation_id"]
    allowed = {
        "/api/runtime",
        "/api/auth/session",
        "/api/profile/me",
        "/api/graph",
        "/api/mastery",
        "/api/path/current",
        f"/api/learning-operations/{oid}",
    }
    if unit:
        allowed.add(f"/api/learning-units/{unit}")
    wrapper = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @wrapper.middleware("http")
    async def only_reads(request: Request, call_next):
        if request.method != "GET" or (
            request.url.path not in allowed
            and not request.url.path.startswith("/api/graph/node/")
            and request.url.path != "/api/__acceptance/bootstrap"
        ):
            return JSONResponse({"code": "ACCEPTANCE_READ_ONLY"}, status_code=403)
        return await call_next(request)

    @wrapper.get("/api/__acceptance/bootstrap")
    async def bootstrap():
        storage = {"edumind:last-learning-operation": oid}
        if unit and result["course_state"] == "completed":
            storage["edumind:last-learning-unit"] = unit
            storage[f"edumind:publication:{unit}"] = str(
                result["isolated_publication"]["version"]
            )
        payload = json.dumps(storage).replace("<", "\\u003c")
        response = HTMLResponse(
            "<script>sessionStorage.clear();Object.entries("
            + payload
            + ").forEach(([k,v])=>sessionStorage.setItem(k,v));location.href='/';</script>"
        )
        # This is an explicit disposable test session on loopback HTTP only.
        # Production cookie settings and auth implementation remain unchanged.
        response.set_cookie(
            COOKIE_NAME, token, httponly=True, samesite="strict", secure=False
        )
        response.headers["cache-control"] = "no-store"
        return response

    wrapper.mount("/", upstream)
    return wrapper


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=["A01", "A02", "A03", "A04"], required=True)
    args = p.parse_args()
    authorize()
    result = read_json(PRIVATE / args.case / "result.json")
    env = isolated_environment()
    url = env["EDUMIND_DATABASE_URL"]
    asyncio.run(verify_database(url))
    for name in list(os.environ):
        if name.startswith(("EDUMIND_PROVIDER", "EDUMIND_REVIEW_CANDIDATE")):
            del os.environ[name]
    os.environ["EDUMIND_DATABASE_URL"] = url
    os.environ["EDUMIND_PRODUCT_MODE"] = "dynamic"
    token = token_urlsafe(32)

    async def session(create):
        engine = create_database_engine(url)
        try:
            async with async_sessionmaker(engine)() as db:
                if create:
                    now = datetime.now(timezone.utc)
                    db.add(
                        GuestSessionRecord(
                            token_hash=token_hash(token),
                            user_id=UUID(result["owner_id"]),
                            created_at=now,
                            expires_at=now + timedelta(hours=1),
                        )
                    )
                else:
                    await db.execute(
                        delete(GuestSessionRecord).where(
                            GuestSessionRecord.token_hash == token_hash(token)
                        )
                    )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(session(True))
    try:
        require(
            result["production_publish_performed"] is False, "ISOLATED_RESULT_REQUIRED"
        )
        uvicorn.run(
            readonly_app(app, result, token),
            host="127.0.0.1",
            port=18179,
            access_log=False,
            log_level="warning",
        )
    finally:
        asyncio.run(session(False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Read-only isolated browser server failed closed.", file=sys.stderr)
        sys.exit(1)
