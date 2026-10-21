"""Single trusted host controller. PG row locks and token host locks never overlap."""

import asyncio
import fcntl
import logging
import os
import re
import time
from collections.abc import Awaitable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.animation import AnimationJobAttempt
from app.services.animation_attempts import launch_valid, transition
from app.services.animation_renderer import ROOT, RenderError, _docker

T = TypeVar("T")
logger = logging.getLogger(__name__)


@contextmanager
def token_lock(token: UUID) -> Iterator[None]:
    root = Path(os.getenv("EDUMIND_RENDER_LOCK_ROOT", str(ROOT / "data/videos/cache/host-locks")))
    if root.is_symlink():
        raise RenderError("RENDER_UNAVAILABLE")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(root / f"{token.hex}.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + 1
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RenderError("RENDER_UNAVAILABLE") from None
                time.sleep(0.02)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def inventory() -> tuple[str, ...]:
    result = _docker(
        ["ps", "-a", "--filter", "name=^edumind-render-", "--format", "{{.Names}}"],
        timeout=1,
        check=True,
    )
    if len(result.stdout) > 16384:
        raise RenderError("RENDER_INVENTORY_UNAVAILABLE")
    names = result.stdout.decode("ascii").splitlines()
    if len(names) > 100:
        raise RenderError("RENDER_INVENTORY_UNAVAILABLE")
    return tuple(names)


def token_of(name: str) -> UUID | None:
    if re.fullmatch(r"edumind-render-[0-9a-f]{32}", name):
        return UUID(name.removeprefix("edumind-render-"))
    return None


class RenderHost:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        token: UUID,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.sessions, self.token, self.loop = sessions, token, loop
        self.name = f"edumind-render-{token.hex}"

    def query(self, operation: Awaitable[T]) -> T:
        future = asyncio.run_coroutine_threadsafe(operation, self.loop)
        try:
            return future.result(timeout=1)
        except Exception:
            future.cancel()
            raise RenderError("RENDER_LEASE_UNAVAILABLE") from None

    def launch(self, command: list[str]) -> str:
        if not self.query(transition(self.sessions, self.token, "starting")):
            raise RenderError("RENDER_LEASE_LOST")
        try:
            with token_lock(self.token):
                if not self.query(launch_valid(self.sessions, self.token)):
                    raise RenderError("RENDER_LEASE_LOST")
                started = _docker(command, timeout=3, check=True).stdout.decode("ascii").strip()
            if not self.query(transition(self.sessions, self.token, "started")):
                raise RenderError("RENDER_LEASE_LOST")
            if not self.query(launch_valid(self.sessions, self.token)):
                raise RenderError("RENDER_LEASE_LOST")
            return started
        except Exception:
            self.stop()
            raise

    def stop(self) -> bool:
        try:
            if not self.query(transition(self.sessions, self.token, "cleanup_requested")):
                return False
        except RenderError:
            # A trusted current attempt may be killed during DB outage. Evidence
            # cannot be marked complete until the DB returns and absence is verified.
            pass
        try:
            with token_lock(self.token):
                _docker(["rm", "-f", self.name], timeout=2)
                if self.name in inventory():
                    return False
            return self.query(transition(self.sessions, self.token, "absent"))
        except RenderError:
            logger.warning("RENDER_CLEANUP_UNCONFIRMED token=%s", self.token)
            return False


async def cleanup_once(sessions: async_sessionmaker[AsyncSession]) -> int:
    names = await asyncio.to_thread(inventory)
    observed = {token for name in names if (token := token_of(name)) is not None}
    async with sessions() as db:
        known = set(
            (
                await db.scalars(
                    select(AnimationJobAttempt.token).where(AnimationJobAttempt.token.in_(observed))
                )
            ).all()
        )
        pending = set(
            (
                await db.scalars(
                    select(AnimationJobAttempt.token)
                    .where(AnimationJobAttempt.launch_state == "cleanup_requested")
                    .limit(100)
                )
            ).all()
        )
    if observed - known or any(token_of(name) is None for name in names):
        logger.warning("UNTRACKED_RENDER_CONTAINER_REQUIRES_DRAIN")

    # Always revisit visible containers, even if the ledger previously said absent.
    async def invalid(token: UUID) -> UUID | None:
        try:
            async with asyncio.timeout(1):
                return token if not await launch_valid(sessions, token) else None
        except Exception:
            logger.warning("RENDER_LEASE_CHECK_UNCONFIRMED token=%s", token)
            return None

    checked = await asyncio.gather(*(invalid(token) for token in known))
    pending.update(token for token in checked if token is not None)

    async def stop(token: UUID) -> bool:
        controller = RenderHost(sessions, token, asyncio.get_running_loop())
        return await asyncio.to_thread(controller.stop)

    results = await asyncio.gather(*(stop(token) for token in pending))
    return sum(results)


async def require_known_inventory(sessions: async_sessionmaker[AsyncSession]) -> None:
    names = await asyncio.to_thread(inventory)
    async with sessions() as db:
        for name in names:
            token = token_of(name)
            if token is None or await db.get(AnimationJobAttempt, token) is None:
                raise RenderError("UNTRACKED_RENDER_CONTAINER_REQUIRES_DRAIN")
