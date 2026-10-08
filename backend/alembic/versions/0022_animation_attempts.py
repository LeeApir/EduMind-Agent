"""Persistent render attempts and cleanup tokens (accepted ADR-0009)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0022_animation_attempts"
down_revision = "0021_animation_dispatch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "animation_job_attempts",
        sa.Column("token", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("animation_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("dispatch_backend", sa.String(16), nullable=False),
        sa.Column("dispatch_epoch", sa.Integer(), nullable=False),
        sa.Column("launch_state", sa.String(24), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("cleanup_requested_at", sa.DateTime(timezone=True)),
        sa.Column("cleanup_done_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("job_id", "attempt", name="uq_animation_attempt_number"),
        sa.CheckConstraint("attempt BETWEEN 1 AND 2", name="ck_animation_attempt_number"),
        sa.CheckConstraint("dispatch_epoch > 0", name="ck_animation_attempt_epoch"),
        sa.CheckConstraint(
            "dispatch_backend IN ('pg_poll','celery')", name="ck_animation_attempt_backend"
        ),
        sa.CheckConstraint(
            "launch_state IN ('prepared','starting','started','cleanup_requested','absent')",
            name="ck_animation_attempt_state",
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO animation_job_attempts "
            "(token,job_id,attempt,dispatch_backend,dispatch_epoch,launch_state) "
            "SELECT lease_token,id,attempt,dispatch_backend,dispatch_epoch,'starting' "
            "FROM animation_jobs WHERE status='running'"
        )
    )


def downgrade() -> None:
    active = op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM animation_jobs WHERE status='running')")
    )
    if active:
        raise RuntimeError("ACTIVE_RENDER_LEASES_REQUIRE_DRAIN")
    op.drop_table("animation_job_attempts")
