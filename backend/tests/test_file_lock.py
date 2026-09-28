"""Portable exclusive lock round-trip on the host platform (flock or msvcrt)."""

import os
import tempfile

from app.services.file_lock import lock_exclusive, unlock


def test_lock_exclusive_and_unlock_round_trip() -> None:
    with tempfile.TemporaryDirectory() as directory:
        lock_path = os.path.join(directory, "unit.lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            lock_exclusive(fd)
            # msvcrt byte-range locks need at least one byte to target.
            assert os.fstat(fd).st_size >= 1
            unlock(fd)
        finally:
            os.close(fd)
