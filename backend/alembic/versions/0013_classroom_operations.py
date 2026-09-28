"""Create owner-scoped classroom operation idempotency records.

Revision ID: 0013_classroom_operations
Revises: 0012_classroom_sessions
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013_classroom_operations"
down_revision = "0012_classroom_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classroom_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("learning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("result_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="accepted"),
        sa.Column("error", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_classroom_operations_owner_key"),
        sa.UniqueConstraint("user_id", "id", name="uq_classroom_operations_owner_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            name="fk_classroom_operations_unit_owner",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('mode', 'control', 'speech', 'reexplanation', 'debate')",
            name="ck_classroom_operations_kind",
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'running', 'published', 'failed', 'cancelled', "
            "'superseded')",
            name="ck_classroom_operations_status",
        ),
        sa.CheckConstraint(
            "base_revision >= 1", name="ck_classroom_operations_base_revision_positive"
        ),
    )


def downgrade() -> None:
    op.drop_table("classroom_operations")
