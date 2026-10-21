"""Explicit outbox publisher/reconciler process, separate from API and render Worker."""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.core.database import create_database_engine  # noqa: E402
from app.services.durable_job_dispatch import (  # noqa: E402
    publish_dispatch_batch,
    reconcile_dispatches,
)
from app.workers.animation_queue import create_queue_app, send_dispatch  # noqa: E402


async def run(once: bool) -> None:
    # Fail closed before claiming if the private broker configuration is absent.
    app = create_queue_app()
    app.close()
    engine = create_database_engine()
    next_reconcile = 0.0
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        while True:
            if time.monotonic() >= next_reconcile:
                await reconcile_dispatches(sessions)
                next_reconcile = time.monotonic() + 30
            await publish_dispatch_batch(sessions, send_dispatch, limit=1)
            if once:
                return
            await asyncio.sleep(1)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.once))
    except KeyboardInterrupt:
        pass
    except Exception:
        # DB/broker DSNs and raw traceback are never operational output.
        print("ANIMATION_DISPATCHER_UNAVAILABLE", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
