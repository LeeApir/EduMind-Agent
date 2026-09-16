"""Asynchronous PostgreSQL connection utilities."""

from collections.abc import AsyncIterator
from os import getenv

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import ConfigurationError


def get_database_url() -> str:
    """Return the async PostgreSQL URL without leaking it in errors or logs."""
    database_url = getenv("EDUMIND_DATABASE_URL")
    if not database_url:
        raise ConfigurationError(
            "Missing required database configuration: EDUMIND_DATABASE_URL. "
            "Set a postgresql+asyncpg URL before using persistent learning data."
        )
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ConfigurationError("EDUMIND_DATABASE_URL must use the postgresql+asyncpg scheme.")
    return database_url


def create_database_engine(database_url: str | None = None) -> AsyncEngine:
    """Create an engine for an explicit test URL or the server environment URL."""
    return create_async_engine(database_url or get_database_url(), pool_pre_ping=True)


async def check_database_connection(database_url: str | None = None) -> None:
    """Run a minimal connectivity probe without modifying database state."""
    engine = create_database_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def database_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Provide a session factory for API dependencies after configuration succeeds."""
    yield async_sessionmaker(create_database_engine(), expire_on_commit=False)
