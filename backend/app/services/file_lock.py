"""Portable exclusive file lock: flock on POSIX, msvcrt byte-range on Windows.

The animation cache serializes rendering and object publication across the API
and worker processes with an exclusive lock on a lock file. ``fcntl.flock`` is
POSIX-only, so Windows uses ``msvcrt.locking`` over one guaranteed byte instead.
"""

from __future__ import annotations

import os
from importlib import import_module


def _ensure_lockable(fd: int) -> None:
    """Grow an empty lock file to one byte so a byte-range lock has a target."""
    os.lseek(fd, 0, os.SEEK_END)
    if os.fstat(fd).st_size == 0:
        os.write(fd, b"\0")
    os.lseek(fd, 0, os.SEEK_SET)


def lock_exclusive(fd: int) -> None:
    """Acquire a blocking exclusive lock on the open descriptor ``fd``."""
    if os.name == "nt":  # pragma: no cover - Windows byte-range lock
        msvcrt = import_module("msvcrt")
        _ensure_lockable(fd)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX)


def unlock(fd: int) -> None:
    """Release the exclusive lock previously taken with :func:`lock_exclusive`."""
    if os.name == "nt":  # pragma: no cover - Windows byte-range lock
        msvcrt = import_module("msvcrt")
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)
