"""T107 local development CLI. Existing candidates only; no generation transport."""

import argparse
import asyncio
import ipaddress
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]


def forbidden(*_args, **_kwargs):
    raise RuntimeError("HEAD_REPLAY_PROVIDER_FORBIDDEN")


def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        host = (
            args[1][0]
            if event == "socket.connect" and isinstance(args[1], tuple)
            else args[0]
            if event == "socket.getaddrinfo"
            else None
        )
        if (
            host is not None
            and host != "localhost"
            and not ipaddress.ip_address(host).is_loopback
        ):
            raise RuntimeError("HEAD_REPLAY_EXTERNAL_NETWORK_FORBIDDEN")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--serve", action="store_true")
    group.add_argument("--import-case", choices=["C01", "C02"])
    parser.add_argument("--owner", type=UUID)
    args = parser.parse_args()
    from app.core import provider_factory
    from app.services.head_course_replay import require_development_database

    require_development_database()
    if any(
        k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL")) for k in os.environ
    ):
        parser.error(
            "Use a clean development environment without Provider configuration"
        )
    provider_factory.build_default_provider_gateway = forbidden
    provider_factory.build_server_provider_gateway = forbidden
    sys.addaudithook(audit)
    if args.serve:
        if os.environ.get("EDUMIND_PRODUCT_MODE") != "dynamic":
            parser.error("Explicit isolated development dynamic mode required")
        import uvicorn
        from fastapi.responses import JSONResponse
        from app.main import app

        @app.middleware("http")
        async def local_replay_only(request, call_next):
            path = request.url.path
            if request.method == "POST" and (
                path == "/api/free-courses"
                or path.endswith(("/operations", "/tutor-turns"))
            ):
                return JSONResponse(
                    {"code": "HEAD_REPLAY_GENERATION_DISABLED"}, status_code=409
                )
            return await call_next(request)

        uvicorn.run(app, host="127.0.0.1", port=8177, access_log=False)
    else:
        if args.owner is None:
            parser.error("--owner must be an existing browser session owner")
        from app.core.database import create_database_engine
        from app.services.head_course_replay import import_course
        from sqlalchemy.ext.asyncio import AsyncSession

        async def run():
            engine = create_database_engine()
            try:
                async with AsyncSession(engine, expire_on_commit=False) as db:
                    try:
                        result = await import_course(db, args.owner, args.import_case)
                        await db.commit()
                        record = dict(status="accepted", result=result)
                    except Exception as error:
                        await db.rollback()
                        record = dict(
                            status="rejected",
                            code=getattr(error, "code", type(error).__name__),
                        )
                        raise
                    finally:
                        audit_path = Path("/tmp/edumind-t107/import-audit.jsonl")
                        audit_path.parent.mkdir(exist_ok=True)
                        with audit_path.open("a") as handle:
                            handle.write(
                                json.dumps(
                                    dict(
                                        at=datetime.now(timezone.utc).isoformat(),
                                        owner=str(args.owner),
                                        slot=args.import_case,
                                        provider_calls=0,
                                        **record,
                                    )
                                )
                                + "\n"
                            )
                        audit_path.chmod(0o600)
                    print(json.dumps(result))
            finally:
                await engine.dispose()

        asyncio.run(run())


if __name__ == "__main__":
    main()
