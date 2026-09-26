"""Persist owner-scoped path command idempotency receipts."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_path_commands"
down_revision = "0008_learning_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_path_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("target_node_id", sa.String(64), nullable=False),
        sa.Column("path_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_path_command_owner_key"),
        sa.ForeignKeyConstraint(
            ["user_id", "target_node_id", "path_version_id"],
            [
                "learning_path_versions.user_id",
                "learning_path_versions.target_node_id",
                "learning_path_versions.id",
            ],
            name="fk_path_command_owner_target_version",
        ),
    )


def downgrade() -> None:
    op.drop_table("learning_path_commands")
