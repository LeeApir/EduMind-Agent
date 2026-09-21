"""Persist idempotent and recoverable learning operations.

Revision ID: 0004_learning_operations
Revises: 0003_learning_snapshots
Create Date: 2026-09-18
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_learning_operations"
down_revision = "0003_learning_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("preferred_language", sa.String(32), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="accepted"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "learning_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_units.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "scene_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learning_scenes.id", ondelete="SET NULL"),
        ),
        sa.Column("published_scene_version", sa.Integer()),
        sa.Column("error", postgresql.JSONB()),
        sa.Column("canceled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_learning_operations_user_key"),
        sa.CheckConstraint("attempt >= 1", name="ck_learning_operations_attempt_positive"),
    )
    op.create_index("ix_learning_operations_user_id", "learning_operations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_learning_operations_user_id", table_name="learning_operations")
    op.drop_table("learning_operations")
