"""Shared audited-media row creation for cache hits and leased Worker completion."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.animation import AnimationJob, AnimationMedia, AnimationResourceBinding
from app.services.animation_cache import CachedAnimation

RUNTIME_FIELDS = (
    "source_sha256", "image_digest", "font_digest", "renderer_config_sha256",
    "subtitle_version",
)


async def reviewed_media_row(
    db: AsyncSession, job: AnimationJob, media: CachedAnimation,
) -> AnimationMedia | None:
    """Use one immutable content identity; mismatched existing rows fail closed."""
    values: dict[str, object] = {
        "cache_key": media.cache_key,
        "template_id": job.template_id,
        "template_version": job.template_version,
        "review_rule_version": job.review_rule_version,
        **{field: getattr(job, field) for field in RUNTIME_FIELDS},
        "mp4_sha256": media.mp4_sha256,
        "srt_sha256": media.srt_sha256,
        "mp4_size": media.mp4_path.stat().st_size,
        "srt_size": media.srt_path.stat().st_size,
        "duration_seconds": media.duration_seconds,
        "review_status": "passed",
    }
    await db.execute(
        pg_insert(AnimationMedia).values(**values)
        .on_conflict_do_nothing(index_elements=[AnimationMedia.cache_key])
    )
    record = await db.scalar(select(AnimationMedia).where(
        AnimationMedia.cache_key == media.cache_key,
    ))
    if record is None or any(
        getattr(record, field) != expected for field, expected in values.items()
    ):
        return None
    return record


def bind_media(db: AsyncSession, job: AnimationJob, media: AnimationMedia) -> None:
    db.add(AnimationResourceBinding(
        user_id=job.user_id, job_id=job.id, media_id=media.id,
        learning_unit_id=job.learning_unit_id, scene_id=job.scene_id,
        scene_version=job.scene_version,
    ))
