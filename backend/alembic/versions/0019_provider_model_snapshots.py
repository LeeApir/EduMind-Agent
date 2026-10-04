"""Version-bound sanitized model cache; no credentials or raw upstream metadata."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0019_provider_model_snapshots"
down_revision = "0018_provider_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_model_snapshots",
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provider_connections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("models", postgresql.JSONB(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("config_version > 0"),
        sa.CheckConstraint("jsonb_typeof(models) = 'array' AND jsonb_array_length(models) <= 1000"),
    )


def downgrade() -> None:
    op.drop_table("provider_model_snapshots")
