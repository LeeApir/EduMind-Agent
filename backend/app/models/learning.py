"""Versioned profile, learning unit, scene, and resource records."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StudentProfile(Base):
    """A versioned snapshot; unknown dimensions remain null, never invented."""

    __tablename__ = "student_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "version", name="uq_student_profiles_user_version"),
        CheckConstraint("version >= 1", name="ck_student_profiles_version_positive"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    initial_query: Mapped[str | None] = mapped_column(Text)
    professional_background: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    knowledge_base: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    cognitive_style: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    learning_goals: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error_preferences: Mapped[list[object] | None] = mapped_column(JSONB)
    engineering_preference: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    extended_dimensions: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LearningUnit(Base):
    """An internal learning plan owned by one authenticated user."""

    __tablename__ = "learning_units"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_learning_units_version_positive"),
        CheckConstraint("outline_version >= 1", name="ck_learning_units_outline_version_positive"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_point_id: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(200))
    learning_objectives: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    outline: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    outline_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    agent_profiles: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    profile_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    review_summary: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LearningScene(Base):
    """A versioned scene; review state does not imply publication."""

    __tablename__ = "learning_scenes"
    __table_args__ = (
        UniqueConstraint(
            "learning_unit_id", "scene_key", "version", name="uq_learning_scenes_unit_key_version"
        ),
        CheckConstraint("version >= 1", name="ck_learning_scenes_version_positive"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    learning_unit_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("learning_units.id", ondelete="CASCADE"),
        nullable=False,
    )
    scene_key: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_order: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_type: Mapped[str] = mapped_column(String(30), nullable=False)
    input_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generation_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class GeneratedResource(Base):
    """A resource candidate or an immutable published version."""

    __tablename__ = "generated_resources"
    __table_args__ = (
        UniqueConstraint(
            "scene_id", "resource_type", "version", name="uq_generated_resources_scene_type_version"
        ),
        CheckConstraint("version >= 1", name="ck_generated_resources_version_positive"),
        CheckConstraint(
            "review_status IN ('pending', 'passed', 'rejected')",
            name="ck_generated_resources_review_status",
        ),
        CheckConstraint(
            "published_at IS NULL OR review_status = 'passed'",
            name="ck_generated_resources_published_reviewed",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    learning_unit_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("learning_units.id", ondelete="CASCADE"),
        nullable=False,
    )
    scene_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("learning_scenes.id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_point_id: Mapped[str | None] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(500))
    generated_by: Mapped[str | None] = mapped_column(String(50))
    review_score: Mapped[float | None] = mapped_column(Float)
    review_comments: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("generated_resources.id", ondelete="SET NULL")
    )
    generation_metadata: Mapped[dict[str, object] | None] = mapped_column("metadata", JSONB)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
