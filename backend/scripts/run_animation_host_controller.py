"""Independent host cleanup each second and expired lease recovery every five seconds."""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.core.database import create_database_engine  # noqa: E402
from app.services.animation_host import cleanup_once  # noqa: E402
from app.services.animation_worker import reclaim_expired_animation_jobs  # noqa: E402


async def run(once: bool) -> None:
    engine = create_database_engine()
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        next_reap = 0.0
        while True:
            try:
                if time.monotonic() >= next_reap:
                    async with asyncio.timeout(1):
                        await reclaim_expired_animation_jobs(sessions, limit=100)
                    next_reap = time.monotonic() + 5
                await cleanup_once(sessions)
            except Exception:
                print("ANIMATION_HOST_CLEANUP_UNCONFIRMED", file=sys.stderr, flush=True)
            if once:
                return
            await asyncio.sleep(1)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    try:
        asyncio.run(run(parser.parse_args().once))
    except KeyboardInterrupt:
        pass
    except Exception:
        print("ANIMATION_HOST_CONTROLLER_UNAVAILABLE", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
