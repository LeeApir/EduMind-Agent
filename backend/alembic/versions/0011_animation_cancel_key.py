"""Remember the owner-scoped cancellation key on its immutable job receipt."""

import sqlalchemy as sa

from alembic import op

revision = "0011_animation_cancel_key"
down_revision = "0010_animation_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("animation_jobs", sa.Column("cancel_idempotency_key", sa.String(128)))
    op.create_unique_constraint(
        "uq_animation_job_owner_cancel_key", "animation_jobs",
        ["user_id", "cancel_idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_animation_job_owner_cancel_key", "animation_jobs", type_="unique")
    op.drop_column("animation_jobs", "cancel_idempotency_key")
