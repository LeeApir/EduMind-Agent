"""Private per-owner immutable media bytes; qualification and access remain PG responsibilities."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from uuid import UUID

from app.agents.animation_dsl_review import digest
from app.services.animation_cache import AnimationCache
from app.services.animation_dsl_compiler import CompiledDSL
from app.services.animation_renderer import RenderedCandidate, RenderError
from app.services.file_lock import lock_exclusive, unlock

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_MAX = 64 * 1024 * 1024


@dataclass(frozen=True)
class PrivateDSLMedia:
    cache_key: str
    mp4_path: Path
    srt_path: Path
    mp4_sha256: str
    srt_sha256: str
    duration_seconds: float


def owner_namespace(owner: UUID) -> str:
    if not isinstance(owner, UUID):
        raise RenderError("DSL_MEDIA_INVALID")
    return digest({"private_dsl_owner_v1": str(owner)})


def private_dsl_root(base: Path, owner: UUID) -> Path:
    root = base / "dsl" / owner_namespace(owner)
    if any(path.is_symlink() for path in (base, base / "dsl", root)):
        raise RenderError("DSL_MEDIA_INVALID")
    return root


def _bytes(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | _NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= _MAX:
            raise RenderError("DSL_MEDIA_INVALID")
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            data = stream.read(_MAX + 1)
        if len(data) != info.st_size:
            raise RenderError("DSL_MEDIA_INVALID")
        return data
    finally:
        os.close(descriptor)


class AnimationDSLMediaCache:
    def __init__(self, base: Path | None = None):
        self.base = base or AnimationCache().root

    def _directory(self, owner: UUID) -> Path:
        root = private_dsl_root(self.base, owner)
        for path in (
            self.base,
            self.base / "dsl",
            root,
            root / "locks",
            root / "entries",
            root / "objects",
        ):
            if path.is_symlink():
                raise RenderError("DSL_MEDIA_INVALID")
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return root

    @contextmanager
    def lock(self, owner: UUID, key: str) -> Iterator[None]:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise RenderError("DSL_MEDIA_INVALID")
        root = self._directory(owner)
        namespace_descriptor = os.open(
            root / "locks" / "namespace.lock", os.O_CREAT | os.O_RDWR | _NOFOLLOW, 0o600
        )
        try:
            descriptor = os.open(
                root / "locks" / f"{key}.lock", os.O_CREAT | os.O_RDWR | _NOFOLLOW, 0o600
            )
        except BaseException:
            os.close(namespace_descriptor)
            raise
        try:
            # Objects can be shared by several keys inside this private owner namespace.
            # GC and publishers serialize namespace -> key, never reverse-lock PG rows.
            lock_exclusive(namespace_descriptor)
            lock_exclusive(descriptor)
            yield
        finally:
            unlock(descriptor)
            os.close(descriptor)
            unlock(namespace_descriptor)
            os.close(namespace_descriptor)

    def lookup(self, owner: UUID, key: str, compiled: CompiledDSL) -> PrivateDSLMedia | None:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            return None
        try:
            root = private_dsl_root(self.base, owner)
            if any((root / name).is_symlink() for name in ("entries", "objects")):
                return None
            path = root / "entries" / f"{key}.json"
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2048:
                return None
            value = json.loads(path.read_bytes())
            if (
                type(value) is not dict
                or set(value)
                != {"key", "compiler_identity", "mp4_sha256", "srt_sha256", "duration_seconds"}
                or value["key"] != key
                or value["compiler_identity"] != compiled.identity_sha256
            ):
                return None
            mp4_hash, srt_hash = value["mp4_sha256"], value["srt_sha256"]
            if any(
                type(v) is not str or not re.fullmatch(r"[0-9a-f]{64}", v)
                for v in (mp4_hash, srt_hash)
            ):
                return None
            mp4, srt = root / "objects" / f"{mp4_hash}.mp4", root / "objects" / f"{srt_hash}.srt"
            mp4_bytes, srt_bytes = _bytes(mp4), _bytes(srt)
            duration = value["duration_seconds"]
            if (
                hashlib.sha256(mp4_bytes).hexdigest() != mp4_hash
                or hashlib.sha256(srt_bytes).hexdigest() != srt_hash
                or srt_hash != compiled.subtitles_sha256
                or srt_bytes != compiled.subtitles.encode("utf-8")
                or type(duration) not in (int, float)
                or not 30 <= duration <= 90
                or abs(duration - compiled.validated.duration_ms / 1000) > 1 / 15 + 1e-6
            ):
                return None
            return PrivateDSLMedia(key, mp4, srt, mp4_hash, srt_hash, float(duration))
        except (OSError, ValueError, TypeError, KeyError, RenderError):
            return None

    def publish_locked(
        self,
        owner: UUID,
        key: str,
        compiled: CompiledDSL,
        candidate: RenderedCandidate,
    ) -> PrivateDSLMedia:
        """Caller holds qualification then cache lock; published entries are immutable."""
        hit = self.lookup(owner, key, compiled)
        if hit is not None:
            return hit
        root = self._directory(owner)
        entry = root / "entries" / f"{key}.json"
        if entry.exists() or entry.is_symlink():
            raise RenderError(
                "DSL_MEDIA_INVALID"
            )  # Corruption never silently changes old identity.
        mp4, srt = _bytes(candidate.mp4_path), _bytes(candidate.srt_path)
        if (
            hashlib.sha256(mp4).hexdigest() != candidate.mp4_sha256
            or hashlib.sha256(srt).hexdigest() != candidate.srt_sha256
            or srt != compiled.subtitles.encode("utf-8")
            or candidate.srt_sha256 != compiled.subtitles_sha256
            or not 30 <= candidate.duration_seconds <= 90
            or abs(candidate.duration_seconds - compiled.validated.duration_ms / 1000)
            > 1 / 15 + 1e-6
        ):
            raise RenderError("DSL_MEDIA_INVALID")
        for data, hash_value, extension in (
            (mp4, candidate.mp4_sha256, "mp4"),
            (srt, candidate.srt_sha256, "srt"),
        ):
            target = root / "objects" / f"{hash_value}.{extension}"
            if target.exists() or target.is_symlink():
                if hashlib.sha256(_bytes(target)).hexdigest() != hash_value:
                    raise RenderError("DSL_MEDIA_INVALID")
                continue
            self._write_once(target, data)
        value = json.dumps(
            {
                "key": key,
                "compiler_identity": compiled.identity_sha256,
                "mp4_sha256": candidate.mp4_sha256,
                "srt_sha256": candidate.srt_sha256,
                "duration_seconds": candidate.duration_seconds,
            },
            sort_keys=True,
        ).encode()
        self._write_once(entry, value)
        result = self.lookup(owner, key, compiled)
        if result is None:
            raise RenderError("DSL_MEDIA_INVALID")
        return result

    @staticmethod
    def _write_once(target: Path, data: bytes) -> None:
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                temporary_path = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.chmod(0o444)
            os.link(temporary_path, target)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
