"""Loop/process-local, one-operation credentials. No persistence or send permission."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Any
from uuid import UUID

from app.core.credential_crypto import CredentialFailure, serialize_secret

PENDING_SECONDS = 300.0
OPERATION_SECONDS = 180.0
PENDING_PER_SESSION = 4
POLL_SECONDS = 1.0
CHECK_SECONDS = 1.0
ValidityCheck = Callable[[], Awaitable[bool]]


class MemoryOnly:
    def __getstate__(self) -> Any:
        raise TypeError("Temporary credentials cannot be serialized.")


@dataclass(frozen=True)
class TemporaryBinding:
    owner_id: UUID
    session_hash: str = field(repr=False)
    connection_id: UUID
    config_version: int
    operation_id: UUID
    purpose: str
    model_id: str


@dataclass(repr=False)
class _Entry(MemoryOnly):
    binding: TemporaryBinding
    session_deadline: float
    deadline: float
    payload: bytearray = field(repr=False)
    validity: ValidityCheck = field(repr=False)
    active: bool = False
    alive: bool = True
    consumer: asyncio.Task[Any] | None = None
    timer: asyncio.TimerHandle | None = None
    observer: asyncio.Task[None] | None = None


class TemporaryLease(MemoryOnly):
    """Secret access is internal and scoped to the owning operation task."""

    def __init__(self, entry: _Entry) -> None:
        self._entry = entry

    def read_secret(self) -> dict[str, str]:
        entry = self._entry
        if (
            not entry.alive
            or not entry.active
            or asyncio.current_task() is not entry.consumer
            or asyncio.get_running_loop().time() >= entry.deadline
        ):
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        # Caller/HTTP-library copies cannot be cryptographically erased by Python.
        value: dict[str, str] = json.loads(entry.payload)
        return value

    def __repr__(self) -> str:
        return "TemporaryLease(<redacted>)"


class TemporaryCredentialRegistry(MemoryOnly):
    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._entries: dict[str, _Entry] = {}
        self._observers: set[asyncio.Task[None]] = set()
        self._closed = False

    def __repr__(self) -> str:
        return "TemporaryCredentialRegistry(<redacted>)"

    def _assert_loop(self) -> None:
        if self._closed or asyncio.get_running_loop() is not self._loop:
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")

    @staticmethod
    async def _valid(check: ValidityCheck) -> bool:
        async def run_check() -> bool:
            return await check()

        task = asyncio.create_task(run_check())
        task.add_done_callback(TemporaryCredentialRegistry._consume_check)
        try:
            done, _ = await asyncio.wait({task}, timeout=CHECK_SECONDS)
            return bool(task.result()) if done and not task.cancelled() else False
        except Exception:
            # Never log exceptions, which can contain credential or SQL inputs.
            return False
        finally:
            if not task.done():
                # Trigger cancellation on time without waiting for slow DB teardown.
                task.cancel()

    @staticmethod
    def _consume_check(task: asyncio.Task[bool]) -> None:
        if not task.cancelled():
            task.exception()

    def _retire(self, handle: str, entry: _Entry, *, cancel: bool) -> None:
        if not entry.alive:
            return
        entry.alive = False
        self._entries.pop(handle, None)
        entry.payload[:] = b"\x00" * len(entry.payload)
        entry.payload.clear()
        if entry.timer is not None:
            entry.timer.cancel()
            entry.timer = None
        if entry.observer is not None and entry.observer is not asyncio.current_task():
            entry.observer.cancel()
        if cancel and entry.consumer is not None:
            entry.consumer.cancel()
        entry.consumer = None

    def _arm(self, handle: str, entry: _Entry) -> None:
        if entry.timer is not None:
            entry.timer.cancel()
        entry.timer = self._loop.call_later(
            max(0.0, entry.deadline - self._loop.time()),
            lambda: self._retire(handle, entry, cancel=True),
        )

    async def _observe(self, handle: str, entry: _Entry) -> None:
        while entry.alive:
            await asyncio.sleep(POLL_SECONDS)
            if not await self._valid(entry.validity):
                self._retire(handle, entry, cancel=True)
                return

    def _purge(self) -> None:
        for handle, entry in list(self._entries.items()):
            if self._loop.time() >= entry.deadline:
                self._retire(handle, entry, cancel=True)

    async def register(
        self,
        binding: TemporaryBinding,
        secret: Mapping[str, str],
        *,
        session_expires_at: datetime,
        validity: ValidityCheck,
    ) -> str:
        """Only authenticated server code supplies binding and original session expiry."""
        self._assert_loop()
        if (
            binding.config_version < 1
            or binding.purpose not in {"generation", "connection_test", "model_refresh"}
            or not 1 <= len(binding.model_id) <= 200
            or not binding.session_hash
            or session_expires_at.tzinfo is None
        ):
            raise CredentialFailure("VALIDATION_ERROR")
        if not await self._valid(validity):
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        self._assert_loop()
        remaining = (session_expires_at - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise CredentialFailure("CREDENTIAL_EXPIRED")
        self._purge()
        pending = sum(
            not e.active
            and e.binding.owner_id == binding.owner_id
            and e.binding.session_hash == binding.session_hash
            for e in self._entries.values()
        )
        if pending >= PENDING_PER_SESSION:
            raise CredentialFailure("TEMPORARY_CREDENTIAL_LIMIT")
        # No await between checking capacity and publication: atomic on this loop.
        session_deadline = self._loop.time() + remaining
        entry = _Entry(
            binding,
            session_deadline,
            min(session_deadline, self._loop.time() + PENDING_SECONDS),
            bytearray(serialize_secret(secret)),
            validity,
        )
        handle = token_urlsafe(32)
        self._entries[handle] = entry
        self._arm(handle, entry)
        entry.observer = asyncio.create_task(self._observe(handle, entry))
        self._observers.add(entry.observer)
        entry.observer.add_done_callback(self._observers.discard)
        return handle

    @asynccontextmanager
    async def lease(self, handle: str, binding: TemporaryBinding) -> AsyncIterator[TemporaryLease]:
        self._assert_loop()
        self._purge()
        entry = self._entries.get(handle)
        if entry is None or entry.active or entry.binding != binding:
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        if not await self._valid(entry.validity):
            self._retire(handle, entry, cancel=True)
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        self._assert_loop()
        self._purge()
        if self._entries.get(handle) is not entry or entry.active:
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        entry.active = True
        entry.consumer = asyncio.current_task()
        entry.deadline = min(entry.session_deadline, self._loop.time() + OPERATION_SECONDS)
        self._arm(handle, entry)
        try:
            yield TemporaryLease(entry)
        finally:
            self._retire(handle, entry, cancel=False)
            if entry.observer is not None:
                with suppress(asyncio.CancelledError):
                    await entry.observer

    def revoke(self, connection_id: UUID) -> None:
        """Synchronous notification after a same-process connection mutation commits."""
        self._assert_loop()
        for handle, entry in list(self._entries.items()):
            if entry.binding.connection_id == connection_id:
                self._retire(handle, entry, cancel=True)

    async def close(self) -> None:
        """Lifespan shutdown/restart drops pending entries and cancels operations."""
        self._assert_loop()
        self._closed = True
        for handle, entry in list(self._entries.items()):
            self._retire(handle, entry, cancel=True)
        if self._observers:
            await asyncio.gather(*self._observers, return_exceptions=True)
