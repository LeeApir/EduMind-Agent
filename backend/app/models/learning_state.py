"""Owner-scoped evidence, mastery revisions, and path versions for MVP 0.2."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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


class LearningEvidence(Base):
    """Append-only observed fact; derived mastery and path state are separate."""

    __tablename__ = "learning_evidence"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_learning_evidence_user_key"),
        UniqueConstraint("user_id", "id", name="uq_learning_evidence_user_id"),
        ForeignKeyConstraint(
            ["user_id", "corrects_evidence_id"],
            ["learning_evidence.user_id", "learning_evidence.id"],
            name="fk_learning_evidence_corrects_owner",
        ),
        CheckConstraint("schema_version >= 1", name="ck_learning_evidence_schema_positive"),
        CheckConstraint(
            "resource_version IS NULL OR resource_version >= 1",
            name="ck_learning_evidence_resource_version_positive",
        ),
        CheckConstraint(
            "evidence_type IN ('quiz_attempt', 'hint_used', 'reexplanation_requested', "
            "'resource_selected', 'explicit_feedback')",
            name="ck_learning_evidence_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    knowledge_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    learning_unit_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("learning_units.id")
    )
    scene_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("learning_scenes.id")
    )
    resource_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("generated_resources.id")
    )
    resource_version: Mapped[int | None] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    corrects_evidence_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NodeMasteryRevision(Base):
    """Immutable result of one deterministic mastery-rule application."""

    __tablename__ = "node_mastery_revisions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "knowledge_node_id", "revision", name="uq_node_mastery_owner_node_revision"
        ),
        UniqueConstraint(
            "user_id", "knowledge_node_id", "id", name="uq_node_mastery_owner_node_id"
        ),
        ForeignKeyConstraint(
            ["user_id", "evidence_id"],
            ["learning_evidence.user_id", "learning_evidence.id"],
            name="fk_node_mastery_evidence_owner",
        ),
        ForeignKeyConstraint(
            ["user_id", "knowledge_node_id", "recomputed_from_id"],
            [
                "node_mastery_revisions.user_id",
                "node_mastery_revisions.knowledge_node_id",
                "node_mastery_revisions.id",
            ],
            name="fk_node_mastery_recomputed_owner_node",
        ),
        CheckConstraint("revision >= 1", name="ck_node_mastery_revision_positive"),
        CheckConstraint(
            "previous_score BETWEEN 0 AND 1", name="ck_node_mastery_previous_score_range"
        ),
        CheckConstraint("score BETWEEN 0 AND 1", name="ck_node_mastery_revision_score_range"),
        CheckConstraint(
            "status IN ('unseen', 'learning', 'weak', 'mastered')",
            name="ck_node_mastery_revision_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_score: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    recomputed_from_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    evidence_summary: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NodeMasteryCurrent(Base):
    """Replaceable owner + node projection pointing at an immutable revision."""

    __tablename__ = "node_mastery_current"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "knowledge_node_id", "revision_id"],
            [
                "node_mastery_revisions.user_id",
                "node_mastery_revisions.knowledge_node_id",
                "node_mastery_revisions.id",
            ],
            name="fk_node_mastery_current_owner_node_revision",
        ),
        CheckConstraint("revision >= 1", name="ck_node_mastery_current_revision_positive"),
        CheckConstraint("score BETWEEN 0 AND 1", name="ck_node_mastery_current_score_range"),
        CheckConstraint(
            "status IN ('unseen', 'learning', 'weak', 'mastered')",
            name="ck_node_mastery_current_status",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LearningPathVersion(Base):
    """Immutable explanation and input watermark for one target-node plan."""

    __tablename__ = "learning_path_versions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "target_node_id", "version", name="uq_learning_path_owner_target_version"
        ),
        UniqueConstraint(
            "user_id", "target_node_id", "id", name="uq_learning_path_owner_target_id"
        ),
        ForeignKeyConstraint(
            ["user_id", "target_node_id", "previous_path_id"],
            [
                "learning_path_versions.user_id",
                "learning_path_versions.target_node_id",
                "learning_path_versions.id",
            ],
            name="fk_learning_path_previous_owner_target",
        ),
        CheckConstraint("version >= 1", name="ck_learning_path_version_positive"),
        CheckConstraint("profile_version >= 1", name="ck_learning_path_profile_version_positive"),
        CheckConstraint(
            "mastery_revision_watermark >= 0", name="ck_learning_path_watermark_nonnegative"
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    graph_version: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    mastery_revision_watermark: Mapped[int] = mapped_column(Integer, nullable=False)
    planner_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    nodes: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    current_node_id: Mapped[str | None] = mapped_column(String(64))
    prerequisite_node_ids: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    next_node_id: Mapped[str | None] = mapped_column(String(64))
    reasons: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    previous_path_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LearningPathCurrent(Base):
    """Current plan pointer plus durable repair flag after a mastery change."""

    __tablename__ = "learning_path_current"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "target_node_id", "path_version_id"],
            [
                "learning_path_versions.user_id",
                "learning_path_versions.target_node_id",
                "learning_path_versions.id",
            ],
            name="fk_learning_path_current_owner_target_version",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    target_node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    path_version_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    replan_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LearningPathCommand(Base):
    """Durable owner-scoped request key pointing at its original immutable result."""

    __tablename__ = "learning_path_commands"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_path_command_owner_key"),
        ForeignKeyConstraint(
            ["user_id", "target_node_id", "path_version_id"],
            [
                "learning_path_versions.user_id",
                "learning_path_versions.target_node_id",
                "learning_path_versions.id",
            ],
            name="fk_path_command_owner_target_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    target_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    path_version_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
