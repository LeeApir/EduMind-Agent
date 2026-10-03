"""Store only reviewed, immutable multi-perspective results.

Revision ID: 0015_debate_results
Revises: 0014_classroom_receipts
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015_debate_results"
down_revision = "0014_classroom_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "debate_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("learning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scene_key", sa.String(64), nullable=False),
        sa.Column("scene_version", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("candidate_schema_version", sa.String(80), nullable=False),
        sa.Column("candidate_prompt_version", sa.String(80), nullable=False),
        sa.Column("generation_model_id", sa.String(200), nullable=False),
        sa.Column("review_version", sa.String(80), nullable=False),
        sa.Column("review_model_id", sa.String(200), nullable=False),
        sa.Column("correction_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "id", name="uq_debate_results_owner_id"),
        sa.UniqueConstraint("user_id", "operation_id", name="uq_debate_results_owner_operation"),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id"], ["learning_units.user_id", "learning_units.id"],
            name="fk_debate_results_unit_owner", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "operation_id"],
            ["classroom_operations.user_id", "classroom_operations.id"],
            name="fk_debate_results_operation_owner", ondelete="CASCADE",
        ),
        sa.CheckConstraint("scene_version >= 1", name="ck_debate_results_scene_version_positive"),
    )


def downgrade() -> None:
    op.drop_table("debate_results")
