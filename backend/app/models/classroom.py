"""Persistent classroom session, append-only messages, and per-role context.

The classroom is owner-scoped progress inside an existing learning unit; it is
not a second source of mastery or a second set of users. Temporary stream tokens
are deliberately absent: only committed messages are persisted and replayed.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.learning import utc_now


class ClassroomSession(Base):
    """At most one current classroom per owner + learning unit."""

    __tablename__ = "classroom_sessions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "learning_unit_id", name="uq_classroom_sessions_owner_unit"
        ),
        UniqueConstraint("user_id", "id", name="uq_classroom_sessions_owner_id"),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            name="fk_classroom_sessions_unit_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint("mode IN ('focus', 'interactive')", name="ck_classroom_sessions_mode"),
        CheckConstraint("revision >= 1", name="ck_classroom_sessions_revision_positive"),
        CheckConstraint(
            "scene_version >= 1", name="ck_classroom_sessions_scene_version_positive"
        ),
        CheckConstraint(
            "scene_progress >= 0", name="ck_classroom_sessions_scene_progress_nonnegative"
        ),
        CheckConstraint(
            "message_cursor >= 0", name="ck_classroom_sessions_message_cursor_nonnegative"
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    learning_unit_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    scene_key: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scene_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="focus")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    message_cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled_roles: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    generation_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detour: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ClassroomOperation(Base):
    """Owner-scoped idempotency record for one classroom write command.

    Mode/control commands resolve synchronously to ``published``; streaming
    commands (speech/reexplanation/debate) move through ``accepted``/``running``
    to a terminal status. Only streaming kinds are ever surfaced through the
    public ``GET /api/classroom-operations`` read model.
    """

    __tablename__ = "classroom_operations"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_classroom_operations_owner_key"
        ),
        UniqueConstraint("user_id", "id", name="uq_classroom_operations_owner_id"),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            name="fk_classroom_operations_unit_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "kind IN ('create', 'mode', 'control', 'speech', 'reexplanation', 'debate')",
            name="ck_classroom_operations_kind",
        ),
        CheckConstraint(
            "status IN ('accepted', 'running', 'published', 'failed', 'cancelled', "
            "'superseded')",
            name="ck_classroom_operations_status",
        ),
        CheckConstraint(
            "base_revision >= 1", name="ck_classroom_operations_base_revision_positive"
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    learning_unit_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    result_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    result_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="accepted")
    error: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ClassroomMessage(Base):
    """An append-only committed message with a per-session increasing cursor."""

    __tablename__ = "classroom_messages"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "message_cursor", name="uq_classroom_messages_session_cursor"
        ),
        UniqueConstraint("user_id", "id", name="uq_classroom_messages_owner_id"),
        ForeignKeyConstraint(
            ["user_id", "session_id"],
            ["classroom_sessions.user_id", "classroom_sessions.id"],
            name="fk_classroom_messages_session_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint("message_cursor >= 1", name="ck_classroom_messages_cursor_positive"),
        CheckConstraint(
            "session_revision >= 1", name="ck_classroom_messages_revision_positive"
        ),
        CheckConstraint(
            "scene_version >= 1", name="ck_classroom_messages_scene_version_positive"
        ),
        CheckConstraint(
            "role IN ('student', 'tutor', 'beginner', 'advanced', 'system', "
            "'performance', 'engineering', 'academic', 'moderator')",
            name="ck_classroom_messages_role",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    message_cursor: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    session_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_key: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_version: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    resource_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("generated_resources.id", ondelete="SET NULL")
    )
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ClassroomRoleContext(Base):
    """Sanitized per-role summary plus limited recent message references.

    Classroom roles (tutor/beginner/advanced) and debate perspectives
    (performance/engineering/academic/moderator) are stored separately via
    ``context_kind`` so their responsibilities never share one context record.
    """

    __tablename__ = "classroom_role_contexts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "learning_unit_id", "role", "scene_key", "scene_version",
            name="uq_classroom_role_contexts_owner_unit_role_scene",
        ),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            name="fk_classroom_role_contexts_unit_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "context_kind IN ('classroom', 'perspective')",
            name="ck_classroom_role_contexts_kind",
        ),
        CheckConstraint(
            "(context_kind = 'classroom' AND role IN ('tutor', 'beginner', 'advanced')) "
            "OR (context_kind = 'perspective' AND role IN "
            "('performance', 'engineering', 'academic', 'moderator'))",
            name="ck_classroom_role_contexts_role_kind",
        ),
        CheckConstraint(
            "scene_version >= 1", name="ck_classroom_role_contexts_scene_version_positive"
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    learning_unit_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    context_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    scene_key: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_version: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    message_refs: Mapped[list[object]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
