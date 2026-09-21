"""Persist versioned profiles, learning scenes, and reviewed resources.

Revision ID: 0003_learning_snapshots
Revises: 0002_auth_sessions
Create Date: 2026-09-17
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_learning_snapshots"
down_revision = "0002_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("initial_query", sa.Text()),
        sa.Column("professional_background", postgresql.JSONB()),
        sa.Column("knowledge_base", postgresql.JSONB()),
        sa.Column("cognitive_style", postgresql.JSONB()),
        sa.Column("learning_goals", postgresql.JSONB()),
        sa.Column("error_preferences", postgresql.JSONB()),
        sa.Column("engineering_preference", postgresql.JSONB()),
        sa.Column("extended_dimensions", postgresql.JSONB()),
        sa.Column("evidence", postgresql.JSONB()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "version", name="uq_student_profiles_user_version"),
        sa.CheckConstraint("version >= 1", name="ck_student_profiles_version_positive"),
    )
    op.create_index("ix_student_profiles_user_id", "student_profiles", ["user_id"])

    op.create_table(
        "learning_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("knowledge_point_id", sa.String(64)),
        sa.Column("title", sa.String(200)),
        sa.Column("learning_objectives", postgresql.JSONB()),
        sa.Column("outline", postgresql.JSONB()),
        sa.Column("outline_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("agent_profiles", postgresql.JSONB()),
        sa.Column("profile_snapshot", postgresql.JSONB()),
        sa.Column("review_summary", postgresql.JSONB()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("version >= 1", name="ck_learning_units_version_positive"),
        sa.CheckConstraint(
            "outline_version >= 1", name="ck_learning_units_outline_version_positive"
        ),
    )
    op.create_index("ix_learning_units_user_id", "learning_units", ["user_id"])

    op.create_table(
        "learning_scenes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "learning_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_units.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scene_key", sa.String(64), nullable=False),
        sa.Column("scene_order", sa.Integer(), nullable=False),
        sa.Column("scene_type", sa.String(30), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("generation_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "learning_unit_id", "scene_key", "version", name="uq_learning_scenes_unit_key_version"
        ),
        sa.CheckConstraint("version >= 1", name="ck_learning_scenes_version_positive"),
    )

    op.create_table(
        "generated_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "learning_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_units.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scene_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_scenes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("knowledge_point_id", sa.String(64)),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("file_url", sa.String(500)),
        sa.Column("generated_by", sa.String(50)),
        sa.Column("review_score", sa.Float()),
        sa.Column("review_comments", postgresql.JSONB()),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generated_resources.id", ondelete="SET NULL"),
        ),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "scene_id", "resource_type", "version", name="uq_generated_resources_scene_type_version"
        ),
        sa.CheckConstraint("version >= 1", name="ck_generated_resources_version_positive"),
        sa.CheckConstraint(
            "review_status IN ('pending', 'passed', 'rejected')",
            name="ck_generated_resources_review_status",
        ),
        sa.CheckConstraint(
            "published_at IS NULL OR review_status = 'passed'",
            name="ck_generated_resources_published_reviewed",
        ),
    )
    op.create_index("ix_generated_resources_user_id", "generated_resources", ["user_id"])
    op.execute(
        """
        CREATE FUNCTION prevent_published_resource_update() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.published_at IS NOT NULL THEN
                RAISE EXCEPTION 'published resources are immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_published_resource_immutable
        BEFORE UPDATE ON generated_resources
        FOR EACH ROW EXECUTE FUNCTION prevent_published_resource_update()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_published_resource_immutable ON generated_resources")
    op.execute("DROP FUNCTION IF EXISTS prevent_published_resource_update()")
    op.drop_index("ix_generated_resources_user_id", table_name="generated_resources")
    op.drop_table("generated_resources")
    op.drop_table("learning_scenes")
    op.drop_index("ix_learning_units_user_id", table_name="learning_units")
    op.drop_table("learning_units")
    op.drop_index("ix_student_profiles_user_id", table_name="student_profiles")
    op.drop_table("student_profiles")
