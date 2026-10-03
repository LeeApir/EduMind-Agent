"""Durable owner-scoped animation jobs, replayable events, and private media bindings."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.learning import utc_now


class AnimationMedia(Base):
    """Reviewed shared bytes; this record grants no user permission by itself."""

    __tablename__ = "animation_media"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_animation_media_cache_key"),
        CheckConstraint("review_status = 'passed'", name="ck_animation_media_review_passed"),
        CheckConstraint("duration_seconds BETWEEN 30 AND 90", name="ck_animation_media_duration"),
        CheckConstraint("mp4_size > 0 AND mp4_size <= 67108864",
                        name="ck_animation_media_mp4_size"),
        CheckConstraint("srt_size > 0 AND srt_size <= 67108864",
                        name="ck_animation_media_srt_size"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[str] = mapped_column(String(40), nullable=False)
    review_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    font_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    subtitle_version: Mapped[str] = mapped_column(String(40), nullable=False)
    mp4_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    srt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mp4_size: Mapped[int] = mapped_column(Integer, nullable=False)
    srt_size: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="passed")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnimationJob(Base):
    """PostgreSQL is the sole authority for status, lease and request identity."""

    __tablename__ = "animation_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "action_kind", "idempotency_key",
                         name="uq_animation_job_owner_action_key"),
        UniqueConstraint("user_id", "cancel_idempotency_key",
                         name="uq_animation_job_owner_cancel_key"),
        UniqueConstraint("user_id", "id", name="uq_animation_job_owner_id"),
        UniqueConstraint("user_id", "id", "media_id", name="uq_animation_job_owner_id_media"),
        UniqueConstraint(
            "user_id", "learning_unit_id", "scene_id", "scene_version", "id",
            name="uq_animation_job_owner_target_id",
        ),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id"], ["learning_units.user_id", "learning_units.id"],
            name="fk_animation_job_unit_owner",
        ),
        ForeignKeyConstraint(
            ["learning_unit_id", "scene_id", "scene_version"],
            ["learning_scenes.learning_unit_id", "learning_scenes.id", "learning_scenes.version"],
            name="fk_animation_job_scene_version",
        ),
        ForeignKeyConstraint(
            ["user_id", "retry_of"], ["animation_jobs.user_id", "animation_jobs.id"],
            name="fk_animation_job_retry_owner",
        ),
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')",
                        name="ck_animation_job_status"),
        CheckConstraint("action_kind IN ('request','retry')", name="ck_animation_job_action"),
        CheckConstraint("attempt BETWEEN 0 AND 2", name="ck_animation_job_attempt"),
        CheckConstraint("progress BETWEEN 0 AND 1", name="ck_animation_job_progress"),
        CheckConstraint("last_event_id >= 0", name="ck_animation_job_event_watermark"),
        CheckConstraint("scene_version >= 1", name="ck_animation_job_scene_version"),
        CheckConstraint("status != 'running' OR (lease_token IS NOT NULL AND "
                        "lease_expires_at IS NOT NULL AND attempt >= 1)",
                        name="ck_animation_job_running_lease"),
        CheckConstraint("status != 'succeeded' OR media_id IS NOT NULL",
                        name="ck_animation_job_succeeded_media"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    learning_unit_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    scene_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    scene_version: Mapped[int] = mapped_column(Integer, nullable=False)
    action_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[str] = mapped_column(String(40), nullable=False)
    review_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    font_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    subtitle_version: Mapped[str] = mapped_column(String(40), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_event_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_token: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(default=False, nullable=False)
    cancel_idempotency_key: Mapped[str | None] = mapped_column(String(128))
    retry_of: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    media_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("animation_media.id")
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnimationJobEvent(Base):
    """One immutable, owner-scoped event with a job-local increasing cursor."""

    __tablename__ = "animation_job_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "job_id"], ["animation_jobs.user_id", "animation_jobs.id"],
            name="fk_animation_job_event_owner", ondelete="CASCADE",
        ),
        CheckConstraint("event_id >= 1", name="ck_animation_job_event_id_positive"),
        CheckConstraint(
            "event_type IN ('queued','running','progress','succeeded','failed','cancelled',"
            "'recovered')", name="ck_animation_job_event_type",
        ),
    )

    job_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AnimationResourceBinding(Base):
    """A reviewed media reference is usable only through a matching owner/job target."""

    __tablename__ = "animation_resource_bindings"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_animation_binding_owner_job"),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "scene_id", "scene_version", "job_id"],
            ["animation_jobs.user_id", "animation_jobs.learning_unit_id",
             "animation_jobs.scene_id", "animation_jobs.scene_version", "animation_jobs.id"],
            name="fk_animation_binding_job_target_owner", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "job_id", "media_id"],
            ["animation_jobs.user_id", "animation_jobs.id", "animation_jobs.media_id"],
            name="fk_animation_binding_job_media_owner",
        ),
        CheckConstraint("scene_version >= 1", name="ck_animation_binding_scene_version"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    job_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    media_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    scene_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    scene_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
