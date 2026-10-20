"""Read existing isolated results in the built UI; every write endpoint is blocked."""

# ruff: noqa: E402
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from secrets import token_urlsafe
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_catalog_db_tests as isolated
from acceptance_support.five_hour_runtime import (
    private_directory,
    read_json,
    require,
    write_once,
)

PRIVATE = ROOT / "local-materials/phase-1-browser-evidence-r01"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", choices=["pending", "rejected", "published"], required=True
    )
    parser.add_argument("--attempt", default="r01", choices=["r01", "r02"])
    args = parser.parse_args()
    isolated.CONTAINER = "edumind-phase1-t037-pg"
    database = (
        "edumind_catalog_a01_a02_fix_r01"
        if args.case == "published"
        else "edumind_catalog_five_hour_r01"
    )
    env = isolated.test_environment(database)
    for key in list(os.environ):
        if key.startswith(
            ("EDUMIND_PROVIDER", "EDUMIND_GENERATION", "EDUMIND_REVIEW_CANDIDATE")
        ):
            del os.environ[key]
    os.environ["EDUMIND_DATABASE_URL"] = env["EDUMIND_DATABASE_URL"]
    os.environ["EDUMIND_PRODUCT_MODE"] = "dynamic"
    from app.core.auth import token_hash
    from app.core.database import create_database_engine
    from app.main import app
    from app.models.auth import GuestSessionRecord
    from fastapi.responses import FileResponse, JSONResponse
    from sqlalchemy import text, delete
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from serve_five_hour_results import readonly_app
    import uvicorn

    token = token_urlsafe(32)
    directory = private_directory(PRIVATE / (args.case + "-" + args.attempt))

    async def session(create, result=None):
        engine = create_database_engine(env["EDUMIND_DATABASE_URL"])
        try:
            async with async_sessionmaker(engine)() as db:
                if create:
                    if args.case == "published":
                        row = (
                            await db.execute(
                                text("""select o.id,o.user_id,o.learning_unit_id,p.version,p.unit_digest
                          from learning_operations o join learning_publications p on p.operation_id=o.id
                          where o.status='completed' and p.approval_source='auto'
                          and not exists(select 1 from learning_publication_withdrawals w where w.publication_id=p.id)
                          and p.version=(select max(p2.version) from learning_publications p2 where p2.learning_unit_id=p.learning_unit_id)
                          order by p.created_at desc limit 1""")
                            )
                        ).one()
                        result = dict(
                            operation_id=str(row[0]),
                            owner_id=str(row[1]),
                            learning_unit_id=str(row[2]),
                            course_state="completed",
                            isolated_publication=dict(
                                version=row[3], unit_digest=row[4]
                            ),
                            production_publish_performed=False,
                            source="existing scripted PG auto publication; NOT actual LLM success",
                        )
                    else:
                        case = "A01" if args.case == "pending" else "A02"
                        path = (
                            ROOT
                            / "local-materials/phase-1-five-hour-remaining-six-r01"
                            / case
                            / "result.json"
                        )
                        result = read_json(path)
                        recorded = (
                            await db.execute(
                                text(
                                    "select status,user_id,learning_unit_id from learning_operations where id=:id"
                                ),
                                dict(id=UUID(result["operation_id"])),
                            )
                        ).one()
                        require(
                            str(recorded[0]) == result["course_state"]
                            and str(recorded[1]) == result["owner_id"]
                            and str(recorded[2]) == result["learning_unit_id"],
                            "STORED_RESULT_CHANGED",
                        )
                        result["source"] = (
                            "actual previous live generation; no regeneration"
                        )
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
                return result
        finally:
            await engine.dispose()

    result = asyncio.run(session(True))
    info = {
        k: result[k]
        for k in [
            "operation_id",
            "owner_id",
            "learning_unit_id",
            "course_state",
            "source",
        ]
    }
    info["version"] = (result.get("isolated_publication") or {}).get("version", 1)
    info["database"] = database
    write_once(directory / "server-info.json", info)
    wrapper = readonly_app(app, result, token)
    dist = (ROOT / "web/dist").resolve()

    @wrapper.middleware("http")
    async def built_ui(request, call_next):
        if request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.method != "GET":
            return JSONResponse({"code": "ACCEPTANCE_READ_ONLY"}, status_code=403)
        path = (dist / request.url.path.lstrip("/")).resolve()
        if not path.is_relative_to(dist):
            return JSONResponse({}, status_code=404)
        return FileResponse(path if path.is_file() else dist / "index.html")

    try:
        uvicorn.run(
            wrapper, host="127.0.0.1", port=18179, access_log=False, log_level="warning"
        )
    finally:
        asyncio.run(session(False))
        write_once(
            directory / "session-cleanup.json",
            dict(disposable_session_deleted=True, provider_calls=0),
        )


if __name__ == "__main__":
    main()
