"""Owner-bound append-only plan evidence; no generation or publication changes."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0032_plan_check_evidence"
down_revision = "0031_teaching_context"
branch_labels = None
depends_on = None


def upgrade():
    common = ["id", "user_id", "learning_unit_id", "operation_id", "plan_id"]
    op.create_table(
        "learning_plan_checks",
        *[
            sa.Column(k, pg.UUID(as_uuid=True), nullable=False, primary_key=k == "id")
            for k in common
        ],
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column("record_digest", sa.String(64), nullable=False),
        sa.Column("record", pg.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("operation_id", "plan_id", "stage"),
        sa.UniqueConstraint("user_id", "learning_unit_id", "operation_id", "plan_id", "id"),
        sa.CheckConstraint("stage IN ('plan_check', 'plan_recheck')", name="plan_check_stage"),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "plan_id"],
            ["learning_plan_versions." + k for k in ["user_id", "learning_unit_id", "id"]],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "operation_id"],
            ["learning_operations." + k for k in ["user_id", "learning_unit_id", "id"]],
            ondelete="RESTRICT",
        ),
    )
    for table in ["learning_plan_rebuild_events", "learning_plan_check_resolutions"]:
        extra = (
            [
                sa.Column("event_type", sa.String(16), nullable=False),
                sa.UniqueConstraint("operation_id", "event_type"),
                sa.CheckConstraint(
                    "event_type IN ('reserved', 'completed', 'failed')",
                    name="plan_rebuild_event_type",
                ),
            ]
            if table.endswith("events")
            else [
                sa.Column("idempotency_key", sa.String(128), nullable=False),
                sa.UniqueConstraint("user_id", "idempotency_key"),
            ]
        )
        op.create_table(
            table,
            *[
                sa.Column(k, pg.UUID(as_uuid=True), nullable=False, primary_key=k == "id")
                for k in [*common, "check_id"]
            ],
            sa.Column("record_digest", sa.String(64), nullable=False),
            sa.Column("record", pg.JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["user_id", "learning_unit_id", "operation_id", "plan_id", "check_id"],
                [
                    "learning_plan_checks." + k
                    for k in ["user_id", "learning_unit_id", "operation_id", "plan_id", "id"]
                ],
                ondelete="RESTRICT",
            ),
            *extra,
        )
    # One terminal event, whether success or failure. Reservation is separately unique.
    op.create_index(
        "uq_plan_rebuild_terminal",
        "learning_plan_rebuild_events",
        ["operation_id"],
        unique=True,
        postgresql_where=sa.text("event_type IN ('completed', 'failed')"),
    )
    op.execute("""CREATE FUNCTION immutable_plan_check_evidence() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'plan check evidence is append only'; END; $$ LANGUAGE plpgsql""")
    for table in [
        "learning_plan_checks",
        "learning_plan_rebuild_events",
        "learning_plan_check_resolutions",
    ]:
        op.execute(
            f"CREATE TRIGGER immutable_plan_evidence BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION immutable_plan_check_evidence()"
        )


def downgrade():
    for table in [
        "learning_plan_checks",
        "learning_plan_rebuild_events",
        "learning_plan_check_resolutions",
    ]:
        op.execute(
            f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM {table}) THEN "
            "RAISE EXCEPTION 'plan evidence prevents downgrade'; END IF; END $$"
        )
    for table in [
        "learning_plan_check_resolutions",
        "learning_plan_rebuild_events",
        "learning_plan_checks",
    ]:
        op.drop_table(table)
    op.execute("DROP FUNCTION immutable_plan_check_evidence()")
