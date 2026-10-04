"""Asynchronous PostgreSQL connection utilities."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from os import getenv

from fastapi import FastAPI, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import ConfigurationError
from app.core.temporary_credentials import TemporaryCredentialRegistry


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
    return create_async_engine(
        database_url or get_database_url(), pool_pre_ping=True, hide_parameters=True
    )


async def check_database_connection(database_url: str | None = None) -> None:
    """Run a minimal connectivity probe without modifying database state."""
    engine = create_database_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


@dataclass
class DatabaseRuntime:
    """One loop/lifespan owns its pool; sessions and transactions remain request-local."""

    engine: AsyncEngine | None = None
    factory: async_sessionmaker[AsyncSession] | None = None
    credential_cleanup_task: asyncio.Task[None] | None = None
    temporary_credentials: TemporaryCredentialRegistry | None = None

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        # No await between creation and publication, so first concurrent calls cannot race.
        if self.factory is None:
            self.engine = create_database_engine()
            self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
            from app.core.credential_cleanup import cleanup_loop

            self.credential_cleanup_task = asyncio.create_task(cleanup_loop(self.factory))
        return self.factory


@asynccontextmanager
async def database_lifespan(_app: FastAPI) -> AsyncIterator[dict[str, DatabaseRuntime]]:
    """Lazy DB configuration keeps /health usable without a configured database."""
    runtime = DatabaseRuntime(temporary_credentials=TemporaryCredentialRegistry())
    try:
        # ASGI copies this lifespan state into each request on the owning loop.
        # app.state alone is unsafe when embedded hosts have multiple lifespan loops.
        yield {"database_runtime": runtime}
    finally:
        if runtime.temporary_credentials is not None:
            await runtime.temporary_credentials.close()
        if runtime.credential_cleanup_task is not None:
            runtime.credential_cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await runtime.credential_cleanup_task
        if runtime.engine is not None:
            await runtime.engine.dispose()


async def database_session_factory(
    request: Request,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Reuse the application pool, never a session or owner-scoped transaction."""
    runtime = getattr(request.state, "database_runtime", None)
    if isinstance(runtime, DatabaseRuntime):
        yield runtime.session_factory()
        return
    # Embedded callers without ASGI lifespan retain the isolated per-request fallback.
    # Real Uvicorn always runs lifespan; do not cache engines across unrelated test loops.
    engine = create_database_engine()
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
