"""Create classroom sessions, append-only messages, and per-role contexts.

Revision ID: 0012_classroom_sessions
Revises: 0011_animation_cancel_key
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012_classroom_sessions"
down_revision = "0011_animation_cancel_key"
branch_labels = None
depends_on = None


def _owner_column() -> sa.Column:
    return sa.Column(
        "user_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "classroom_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _owner_column(),
        sa.Column("learning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scene_key", sa.String(64), nullable=False),
        sa.Column("scene_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("scene_progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mode", sa.String(20), nullable=False, server_default="focus"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("message_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "enabled_roles",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("detour", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "learning_unit_id", name="uq_classroom_sessions_owner_unit"),
        sa.UniqueConstraint("user_id", "id", name="uq_classroom_sessions_owner_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            name="fk_classroom_sessions_unit_owner",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("mode IN ('focus', 'interactive')", name="ck_classroom_sessions_mode"),
        sa.CheckConstraint("revision >= 1", name="ck_classroom_sessions_revision_positive"),
        sa.CheckConstraint(
            "scene_version >= 1", name="ck_classroom_sessions_scene_version_positive"
        ),
        sa.CheckConstraint(
            "scene_progress >= 0", name="ck_classroom_sessions_scene_progress_nonnegative"
        ),
        sa.CheckConstraint(
            "message_cursor >= 0", name="ck_classroom_sessions_message_cursor_nonnegative"
        ),
    )

    op.create_table(
        "classroom_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        _owner_column(),
        sa.Column("message_cursor", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("session_revision", sa.Integer(), nullable=False),
        sa.Column("scene_key", sa.String(64), nullable=False),
        sa.Column("scene_version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column(
            "resource_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generated_resources.id", ondelete="SET NULL"),
        ),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "session_id", "message_cursor", name="uq_classroom_messages_session_cursor"
        ),
        sa.UniqueConstraint("user_id", "id", name="uq_classroom_messages_owner_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "session_id"],
            ["classroom_sessions.user_id", "classroom_sessions.id"],
            name="fk_classroom_messages_session_owner",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("message_cursor >= 1", name="ck_classroom_messages_cursor_positive"),
        sa.CheckConstraint("session_revision >= 1", name="ck_classroom_messages_revision_positive"),
        sa.CheckConstraint(
            "scene_version >= 1", name="ck_classroom_messages_scene_version_positive"
        ),
        sa.CheckConstraint(
            "role IN ('student', 'tutor', 'beginner', 'advanced', 'system', "
            "'performance', 'engineering', 'academic', 'moderator')",
            name="ck_classroom_messages_role",
        ),
    )

    op.create_table(
        "classroom_role_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _owner_column(),
        sa.Column("learning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("context_kind", sa.String(20), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("scene_key", sa.String(64), nullable=False),
        sa.Column("scene_version", sa.Integer(), nullable=False),
        sa.Column("summary", postgresql.JSONB()),
        sa.Column(
            "message_refs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "user_id", "learning_unit_id", "role", "scene_key", "scene_version",
            name="uq_classroom_role_contexts_owner_unit_role_scene",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            name="fk_classroom_role_contexts_unit_owner",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "context_kind IN ('classroom', 'perspective')",
            name="ck_classroom_role_contexts_kind",
        ),
        sa.CheckConstraint(
            "(context_kind = 'classroom' AND role IN ('tutor', 'beginner', 'advanced')) "
            "OR (context_kind = 'perspective' AND role IN "
            "('performance', 'engineering', 'academic', 'moderator'))",
            name="ck_classroom_role_contexts_role_kind",
        ),
        sa.CheckConstraint(
            "scene_version >= 1", name="ck_classroom_role_contexts_scene_version_positive"
        ),
    )


def downgrade() -> None:
    op.drop_table("classroom_role_contexts")
    op.drop_table("classroom_messages")
    op.drop_table("classroom_sessions")
