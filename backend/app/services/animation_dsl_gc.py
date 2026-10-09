"""Explicit bounded private-cache maintenance: preserve formal rows and active render intents."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.animation import AnimationJob, AnimationMedia
from app.services.animation_dsl_media_cache import AnimationDSLMediaCache, private_dsl_root
from app.services.animation_dsl_publication import private_cache_lock


async def collect_private_dsl_orphans(
    sessions: async_sessionmaker[AsyncSession],
    cache: AnimationDSLMediaCache,
    *,
    owner: UUID,
    key: str,
) -> int:
    """One operator-supplied server owner/key; no HTTP endpoint or learning-data TTL."""
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise ValueError("INVALID_CACHE_IDENTITY")
    async with private_cache_lock(cache, owner, key):
        # Deliberately non-locking: publisher lock order is Job/qualification -> cache.
        async with sessions() as db:
            rows = (
                await db.scalars(
                    select(AnimationMedia).where(
                        AnimationMedia.user_id == owner, AnimationMedia.render_kind == "dsl"
                    )
                )
            ).all()
            jobs = (
                await db.scalars(
                    select(AnimationJob).where(
                        AnimationJob.user_id == owner,
                        AnimationJob.render_kind == "dsl",
                        AnimationJob.status.in_(("queued", "running")),
                        AnimationJob.cancel_requested.is_(False),
                    )
                )
            ).all()
        if any(row.cache_key == key for row in rows) or any(job.cache_key == key for job in jobs):
            return 0
        protected = {row.mp4_sha256 for row in rows} | {row.srt_sha256 for row in rows}
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp()

        def collect() -> int:
            root = private_dsl_root(cache.base, owner)
            entries, objects = root / "entries", root / "objects"
            if entries.is_symlink() or objects.is_symlink():
                return 0
            removed = 0
            entry = entries / f"{key}.json"
            if entry.is_file() and not entry.is_symlink() and entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
            # Conservatively keep all objects while any owner render is pending. Its future
            # content hashes are unknown until rendering finishes.
            if jobs:
                return removed
            for descriptor in entries.glob("*.json"):
                if descriptor.is_symlink() or descriptor.stat().st_size > 2048:
                    return removed
                try:
                    value = json.loads(descriptor.read_bytes())
                    protected.update((value["mp4_sha256"], value["srt_sha256"]))
                except (ValueError, KeyError, TypeError, OSError):
                    return removed  # Damaged metadata never licenses deleting unknown bytes.
            for path in objects.iterdir():
                if path.is_symlink() or not path.is_file() or path.stat().st_mtime >= cutoff:
                    continue
                if path.stem not in protected:
                    path.unlink()
                    removed += 1
            return removed

        return await asyncio.to_thread(collect)
