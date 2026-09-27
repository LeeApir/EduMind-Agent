"""Persist idempotent, owner-scoped profile behavior summaries.

Revision ID: 0005_profile_events
Revises: 0004_learning_operations
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_profile_events"
down_revision = "0004_learning_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("knowledge_node_id", sa.String(64), nullable=False),
        sa.Column("learning_unit_id", sa.String(64)),
        sa.Column("scene_id", sa.String(64)),
        sa.Column("action", sa.String(30)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_profile_events_user_key"),
        sa.CheckConstraint(
            "event_type IN ('hint_used', 'reexplanation_requested', 'resource_selected', "
            "'explicit_feedback')",
            name="ck_profile_events_event_type",
        ),
    )
    op.create_index("ix_profile_events_user_id", "profile_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_profile_events_user_id", table_name="profile_events")
    op.drop_table("profile_events")
