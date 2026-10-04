"""Owner-scoped four task profiles with explicit versioned routes and fallback consent."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0020_model_preferences"
down_revision = "0019_provider_model_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_preferences",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("task_profile", sa.String(20), primary_key=True),
        sa.Column("originating_session_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("route", postgresql.JSONB(), nullable=False),
        sa.Column("fallbacks", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("version > 0"),
        sa.CheckConstraint("task_profile IN ('fast', 'default', 'quality', 'review')"),
        sa.CheckConstraint(
            "jsonb_typeof(fallbacks) = 'array' AND jsonb_array_length(fallbacks) <= 3"
        ),
    )


def downgrade() -> None:
    op.drop_table("model_preferences")
