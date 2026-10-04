"""One lazy cleanup loop per database runtime, without loading any secrets."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.provider_connections import clean_expired_credentials

logger = logging.getLogger(__name__)


async def cleanup_loop(factory: async_sessionmaker[AsyncSession]) -> None:
    while True:
        try:
            while await clean_expired_credentials(factory) == 100:
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception:
            # SQL/driver exception text and parameters must never enter logs.
            logger.warning("Provider credential cleanup unavailable.")
        await asyncio.sleep(60)
