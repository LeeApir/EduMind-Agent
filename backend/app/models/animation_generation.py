"""Bounded API-only preparation receipts; never contain credentials or unreviewed text."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.learning import utc_now


class AnimationPreparation(Base):
    __tablename__ = "animation_preparations"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_animation_preparation_owner_key"),
        UniqueConstraint(
            "user_id",
            "learning_unit_id",
            "scene_id",
            "scene_version",
            "id",
            name="uq_animation_preparation_owner_target",
        ),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["learning_unit_id", "scene_id", "scene_version"],
            ["learning_scenes.learning_unit_id", "learning_scenes.id", "learning_scenes.version"],
        ),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "scene_id", "scene_version", "job_id"],
            [
                "animation_jobs.user_id",
                "animation_jobs.learning_unit_id",
                "animation_jobs.scene_id",
                "animation_jobs.scene_version",
                "animation_jobs.id",
            ],
            name="fk_animation_preparation_job_target",
        ),
        CheckConstraint(
            "generation_attempts BETWEEN 0 AND 3 AND "
            "review_attempts BETWEEN 0 AND generation_attempts",
            name="ck_animation_preparation_attempts",
        ),
        CheckConstraint(
            "stage IN ('reserved','generating','reviewing','compiled',"
            "'handed_off','failed','cancelled')",
            name="ck_animation_preparation_stage",
        ),
        CheckConstraint(
            "stage != 'handed_off' OR job_id IS NOT NULL", name="ck_animation_preparation_handoff"
        ),
        CheckConstraint(
            "deadline > created_at AND deadline <= created_at + interval '180 seconds' "
            "AND deadline <= originating_session_expires_at",
            name="ck_animation_preparation_deadline",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_version: Mapped[int] = mapped_column(nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reference_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    originating_session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    originating_session_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    execution_token: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), default=uuid4, nullable=False
    )
    allow_template_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generation_attempts: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    review_attempts: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved")
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_kind: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    cancel_idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
