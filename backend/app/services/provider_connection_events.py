"""Loop-local post-commit revocation hints; PostgreSQL remains authoritative."""

import asyncio
import weakref
from collections.abc import Callable
from uuid import UUID

_Listeners = set[Callable[[UUID], None]]
_LISTENERS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _Listeners] = (
    weakref.WeakKeyDictionary()
)


def subscribe(listener: Callable[[UUID], None]) -> Callable[[], None]:
    loop = asyncio.get_running_loop()
    listeners = _LISTENERS.setdefault(loop, set())
    listeners.add(listener)
    return lambda: listeners.discard(listener)


def notify(connection_id: UUID) -> None:
    for listener in tuple(_LISTENERS.get(asyncio.get_running_loop(), ())):
        listener(connection_id)
