"""Pause our test publisher after genuine broker send, before PG receipt commit."""

import asyncio
import os
import signal
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.services.durable_job_dispatch import publish_dispatch_batch
from app.workers.animation_queue import send_dispatch


async def main():
    engine = create_database_engine()
    try:

        async def sent(claim):
            await send_dispatch(claim)
            Path(os.environ["EDUMIND_TEST_PUBLISH_MARKER"]).write_text(str(claim.message.job_id))
            os.kill(os.getpid(), signal.SIGSTOP)
            raise RuntimeError("Controller must kill the paused publisher")

        await publish_dispatch_batch(
            async_sessionmaker(engine, expire_on_commit=False), sent, limit=1
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
