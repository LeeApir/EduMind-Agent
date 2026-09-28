"""Private, versioned cache for reviewed public animation template media."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from app.animation_templates.deletion_plan import srt_for_deletion
from app.animation_templates.insertion_plan import srt_for_insertion
from app.services.animation_renderer import (
    IMAGE,
    ROOT,
    RenderedCandidate,
    render_template,
)
from app.services.animation_templates import (
    RuntimeIdentity,
    cache_identity,
    load_template,
    normalize_parameters,
    source_digest,
)

FONT_DIGEST = "9520e535c5093ae57e3e4b0707ee73d3d4b6f42d98ce05139654da991a9bfd6d"
SUBTITLE_VERSION = "srt-v1"
_ALLOWED = frozenset(("linked-list-insertion", "linked-list-deletion"))


class UnsupportedAnimationError(ValueError):
    """The goal has no reviewed P0 animation template; never run arbitrary code."""

    code = "UNSUPPORTED_ANIMATION_TEMPLATE"


@dataclass(frozen=True)
class CachedAnimation:
    cache_key: str
    template_id: str
    template_version: str
    mp4_path: Path
    srt_path: Path
    mp4_sha256: str
    srt_sha256: str
    duration_seconds: float
    cache_hit: bool


def runtime_identity(template_id: str) -> RuntimeIdentity:
    """Bind cache identity to audited source, pinned image/fonts and renderer code."""
    digest = hashlib.sha256()
    for relative in (
        "backend/app/services/animation_renderer.py",
        "backend/app/animation_templates/container_runner.py",
    ):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((ROOT / relative).read_bytes())
        digest.update(b"\0")
    digest.update(IMAGE.encode("ascii"))
    return RuntimeIdentity(
        source_sha256=source_digest(template_id),
        image_digest=IMAGE.split("@", 1)[1],
        font_digest=FONT_DIGEST,
        renderer_config_sha256=digest.hexdigest(),
        subtitle_version=SUBTITLE_VERSION,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class AnimationCache:
    """Internal media resolver; this class does not grant an owner a resource."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        renderer: Callable[..., RenderedCandidate] = render_template,
        runtime_factory: Callable[[str], RuntimeIdentity] = runtime_identity,
    ) -> None:
        self.root = root or ROOT / "data" / "videos" / "cache" / "approved"
        self.renderer = renderer
        self.runtime_factory = runtime_factory

    def _valid_entry(
        self, key: str, template_id: str, template_version: str,
        review_rule_version: str, parameters: dict[str, object], runtime: RuntimeIdentity,
    ) -> CachedAnimation | None:
        metadata_path = self.root / "entries" / f"{key}.json"
        if metadata_path.is_symlink() or not metadata_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict) or (
                metadata.get("cache_key") != key
                or metadata.get("template_id") != template_id
                or metadata.get("template_version") != template_version
                or metadata.get("source_status") != "approved"
                or metadata.get("review_rule_version") != review_rule_version
                or metadata.get("parameters") != parameters
                or metadata.get("runtime") != vars(runtime)
            ):
                return None
            mp4_hash = metadata["mp4_sha256"]
            srt_hash = metadata["srt_sha256"]
            duration = metadata["duration_seconds"]
            if any(
                not isinstance(value, str) or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in (mp4_hash, srt_hash)
            ) or not isinstance(duration, (int, float)) or not 30 <= duration <= 90:
                return None
            if duration != (36 if template_id == "linked-list-insertion" else 42):
                return None
            mp4 = self.root / "objects" / f"{mp4_hash}.mp4"
            srt = self.root / "objects" / f"{srt_hash}.srt"
            if any(path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024
                   for path in (mp4, srt)):
                return None
            if _sha256_file(mp4) != mp4_hash or _sha256_file(srt) != srt_hash:
                return None
            expected_srt = (
                srt_for_insertion() if template_id == "linked-list-insertion"
                else srt_for_deletion()
            )
            if srt.read_text(encoding="utf-8") != expected_srt:
                return None
            return CachedAnimation(key, template_id, template_version, mp4, srt,
                                   mp4_hash, srt_hash, float(duration), True)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            return None

    def _publish_object(self, source: Path, digest: str, extension: str) -> Path:
        if source.is_symlink() or not source.is_file() or _sha256_file(source) != digest:
            raise ValueError("candidate media digest mismatch")
        target = self.root / "objects" / f"{digest}.{extension}"
        if target.exists() or target.is_symlink():
            if not target.is_symlink() and target.is_file() and _sha256_file(target) == digest:
                return target
            quarantine = self.root / "quarantine"
            quarantine.mkdir(exist_ok=True)
            os.replace(target, quarantine / f"{digest}-{uuid.uuid4().hex}.{extension}")
        os.link(source, target)
        target.chmod(0o444)
        return target

    def validate(self, media: CachedAnimation, parameters: dict[str, object]) -> bool:
        """Recheck exact reviewed bytes before a Job obtains an owner binding."""
        spec = load_template(media.template_id, require_executable=True)
        normalized = normalize_parameters(spec, parameters)
        runtime = self.runtime_factory(media.template_id)
        expected_key = cache_identity(spec, normalized, runtime)
        if media.cache_key != expected_key or media.template_version != spec.template_version:
            return False
        entry = self._valid_entry(
            expected_key, media.template_id, spec.template_version,
            spec.review["rule_version"], normalized, runtime,
        )
        return entry is not None and (
            entry.mp4_path == media.mp4_path
            and entry.srt_path == media.srt_path
            and entry.mp4_sha256 == media.mp4_sha256
            and entry.srt_sha256 == media.srt_sha256
        )

    def lookup(self, template_id: str, parameters: Mapping[str, object]) -> CachedAnimation | None:
        """Return only intact reviewed bytes; a request must never render inline."""
        if template_id not in _ALLOWED or self.root.is_symlink():
            return None
        spec = load_template(template_id, require_executable=True)
        normalized = normalize_parameters(spec, parameters)
        runtime = self.runtime_factory(template_id)
        key = cache_identity(spec, normalized, runtime)
        return self._valid_entry(
            key, template_id, spec.template_version, spec.review["rule_version"],
            normalized, runtime,
        )

    def resolve(
        self, template_id: str, parameters: Mapping[str, object],
        *, container_name: str | None = None,
    ) -> CachedAnimation:
        """Hit an audited public asset first; otherwise render only its fixed template."""
        if template_id not in _ALLOWED:
            raise UnsupportedAnimationError("当前目标没有可用的已审核动画模板")
        spec = load_template(template_id, require_executable=True)
        normalized = normalize_parameters(spec, parameters)
        runtime = self.runtime_factory(template_id)
        key = cache_identity(spec, normalized, runtime)
        if self.root.is_symlink():
            raise ValueError("invalid cache directory")
        for directory in ("locks", "entries", "objects", "quarantine", "attempts"):
            path = self.root / directory
            if path.is_symlink():
                raise ValueError("invalid cache directory")
            path.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / "locks" / f"{key}.lock"
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            hit = self._valid_entry(
                key, template_id, spec.template_version, spec.review["rule_version"],
                normalized, runtime,
            )
            if hit is not None:
                return hit
            render_options: dict[str, object] = {"work_root": self.root / "attempts"}
            if container_name is not None:
                render_options["container_name"] = container_name
            candidate = self.renderer(template_id, normalized, **render_options)
            try:
                object_lock = self.root / "locks" / "objects.lock"
                object_descriptor = os.open(
                    object_lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
                )
                try:
                    fcntl.flock(object_descriptor, fcntl.LOCK_EX)
                    mp4 = self._publish_object(candidate.mp4_path, candidate.mp4_sha256, "mp4")
                    srt = self._publish_object(candidate.srt_path, candidate.srt_sha256, "srt")
                finally:
                    fcntl.flock(object_descriptor, fcntl.LOCK_UN)
                    os.close(object_descriptor)
                metadata = {
                    "cache_key": key,
                    "template_id": template_id,
                    "template_version": spec.template_version,
                    "source_status": spec.review["source_status"],
                    "review_rule_version": spec.review["rule_version"],
                    "runtime": vars(runtime),
                    "parameters": normalized,
                    "mp4_sha256": candidate.mp4_sha256,
                    "srt_sha256": candidate.srt_sha256,
                    "duration_seconds": candidate.duration_seconds,
                }
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.root / "entries",
                    prefix=f"{key}-", suffix=".tmp", delete=False,
                ) as temporary:
                    json.dump(metadata, temporary, ensure_ascii=False, sort_keys=True)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                    temporary_path = Path(temporary.name)
                os.replace(temporary_path, self.root / "entries" / f"{key}.json")
                return CachedAnimation(key, template_id, spec.template_version, mp4, srt,
                                       candidate.mp4_sha256, candidate.srt_sha256,
                                       candidate.duration_seconds, False)
            finally:
                candidate.cleanup()
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
