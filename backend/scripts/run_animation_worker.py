"""Separate process for PostgreSQL-leased animation work; never run in API lifespan."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.database import create_database_engine  # noqa: E402
from app.services.animation_worker import (  # noqa: E402
    reclaim_expired_animation_jobs,
    run_one_animation_job,
)


async def run(*, once: bool, poll_seconds: float) -> None:
    engine = create_database_engine()
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        while True:
            await reclaim_expired_animation_jobs(sessions)
            job_id = await run_one_animation_job(sessions)
            if job_id is not None:
                print(f"processed animation job {job_id}", flush=True)
            if once:
                return
            if job_id is None:
                await asyncio.sleep(poll_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 30:
        parser.error("poll seconds must be between 0.1 and 30")
    asyncio.run(run(once=args.once, poll_seconds=args.poll_seconds))


if __name__ == "__main__":
    main()
