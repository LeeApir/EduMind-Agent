"""Compatible pg_poll/celery routing and transactional animation outbox (ADR-0009)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0021_animation_dispatch"
down_revision = "0020_model_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "animation_jobs",
        sa.Column("dispatch_backend", sa.String(16), nullable=False, server_default="pg_poll"),
    )
    op.add_column(
        "animation_jobs",
        sa.Column("dispatch_epoch", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_animation_job_dispatch_backend",
        "animation_jobs",
        "dispatch_backend IN ('pg_poll','celery')",
    )
    op.create_check_constraint(
        "ck_animation_job_dispatch_epoch", "animation_jobs", "dispatch_epoch >= 1"
    )
    op.create_table(
        "animation_dispatch_outbox",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("animation_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dispatch_epoch", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("task_name", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("publisher_token", pg.UUID(as_uuid=True)),
        sa.Column("publisher_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_sent_at", sa.DateTime(timezone=True)),
        sa.Column("transport_attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(32)),
        sa.UniqueConstraint("job_id", "dispatch_epoch", name="uq_animation_dispatch_job_epoch"),
        sa.CheckConstraint("dispatch_epoch >= 1", name="ck_animation_dispatch_epoch"),
        sa.CheckConstraint(
            "schema_version = 1 AND task_name = 'edumind.render_animation.v1'",
            name="ck_animation_dispatch_protocol",
        ),
        sa.CheckConstraint(
            "state IN ('pending','sending','sent','obsolete')", name="ck_animation_dispatch_state"
        ),
        sa.CheckConstraint("transport_attempts >= 0", name="ck_animation_dispatch_attempts"),
        sa.CheckConstraint(
            "(state = 'sending') = (publisher_token IS NOT NULL AND "
            "publisher_expires_at IS NOT NULL)",
            name="ck_animation_dispatch_lease",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code = 'BROKER_UNAVAILABLE'",
            name="ck_animation_dispatch_error",
        ),
    )
    op.create_index(
        "ix_animation_dispatch_due", "animation_dispatch_outbox", ["state", "next_attempt_at"]
    )


def downgrade() -> None:
    # Development schema rollback only; operational rollback preserves all accepted Jobs.
    connection = op.get_bind()
    active = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM animation_jobs "
            "WHERE dispatch_backend = 'celery' AND status IN ('queued','running'))"
        )
    )
    if active:
        raise RuntimeError("ACTIVE_CELERY_JOBS_REQUIRE_OPERATIONAL_ROLLBACK")
    op.drop_table("animation_dispatch_outbox")
    op.drop_constraint("ck_animation_job_dispatch_epoch", "animation_jobs", type_="check")
    op.drop_constraint("ck_animation_job_dispatch_backend", "animation_jobs", type_="check")
    op.drop_column("animation_jobs", "dispatch_epoch")
    op.drop_column("animation_jobs", "dispatch_backend")
