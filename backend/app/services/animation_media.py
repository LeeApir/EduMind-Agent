"""Owner authorization and safe content-addressed reads for reviewed media."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.animation import AnimationJob, AnimationMedia, AnimationResourceBinding
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_cache import AnimationCache
from app.services.catalog_animation_access import animation_target_approved

MAX_MEDIA_BYTES = 64 * 1024 * 1024
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class MediaUnavailable(ValueError):
    code = "MEDIA_UNAVAILABLE"


@dataclass
class VerifiedMediaFile:
    fd: int
    size: int

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


async def owned_reviewed_media(
    db: AsyncSession, *, owner_id: UUID, media_id: UUID,
) -> AnimationMedia | None:
    """A media row alone grants no permission; require a published owner binding."""
    rows = (await db.execute(
        select(AnimationMedia, AnimationJob)
        .join(AnimationResourceBinding,
              AnimationResourceBinding.media_id == AnimationMedia.id)
        .join(AnimationJob, and_(
            AnimationJob.id == AnimationResourceBinding.job_id,
            AnimationJob.user_id == AnimationResourceBinding.user_id,
            AnimationJob.media_id == AnimationMedia.id,
        ))
        .join(LearningUnit, and_(
            LearningUnit.id == AnimationResourceBinding.learning_unit_id,
            LearningUnit.user_id == AnimationResourceBinding.user_id,
        ))
        .join(LearningScene, and_(
            LearningScene.id == AnimationResourceBinding.scene_id,
            LearningScene.learning_unit_id == LearningUnit.id,
            LearningScene.version == AnimationResourceBinding.scene_version,
        ))
        .where(
            AnimationMedia.id == media_id,
            AnimationMedia.review_status == "passed",
            AnimationResourceBinding.user_id == owner_id,
            AnimationJob.status == "succeeded",
            LearningUnit.status == "ready",
            LearningScene.generation_status == "complete",
            LearningScene.review_status == "passed",
        )
    )).all()
    for media, job in rows:
        if await animation_target_approved(db, owner_id=owner_id, unit_id=job.learning_unit_id,
                scene_id=job.scene_id, scene_version=job.scene_version,
                template_id=job.template_id, template_version=job.template_version):
            return cast(AnimationMedia, media)
    return None


def open_verified_media(
    media: AnimationMedia, *, extension: str, cache: AnimationCache,
) -> VerifiedMediaFile:
    """Open by trusted digest with O_NOFOLLOW; hash the same FD used for response."""
    if extension not in {"mp4", "srt"}:
        raise MediaUnavailable("Media unavailable.")
    digest = media.mp4_sha256 if extension == "mp4" else media.srt_sha256
    expected_size = media.mp4_size if extension == "mp4" else media.srt_size
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise MediaUnavailable("Media unavailable.")
    objects = cache.root / "objects"
    path: Path = objects / f"{digest}.{extension}"
    if cache.root.is_symlink() or objects.is_symlink() or path.is_symlink():
        raise MediaUnavailable("Media unavailable.")
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size != expected_size
            or not 0 < info.st_size <= MAX_MEDIA_BYTES
        ):
            raise MediaUnavailable("Media unavailable.")
        actual = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            actual.update(chunk)
        if actual.hexdigest() != digest:
            raise MediaUnavailable("Media unavailable.")
        return VerifiedMediaFile(fd, info.st_size)
    except (OSError, MediaUnavailable) as error:
        if fd >= 0:
            os.close(fd)
        raise MediaUnavailable("Media unavailable.") from error
