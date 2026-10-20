"""Durable shared request count, correction pair permits, protected baseline tail."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0033_learning_shared_budget"
down_revision = "0032_plan_check_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("learning_operations", sa.Column("generation_budget_version", sa.String(32)))
    for name in [
        "generation_mapping_count",
        "generation_rebuild_count",
        "generation_tail_remaining",
    ]:
        op.add_column(
            "learning_operations", sa.Column(name, sa.Integer(), nullable=False, server_default="0")
        )
    op.create_check_constraint(
        "learning_budget_counters",
        "learning_operations",
        "generation_mapping_count BETWEEN 0 AND 1 AND generation_rebuild_count BETWEEN 0 AND 1 "
        "AND generation_tail_remaining BETWEEN 0 AND 9",
    )
    op.create_table(
        "learning_correction_permits",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "operation_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("learning_operations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("operation_id", "role", "ordinal"),
        sa.CheckConstraint(
            "role IN ('explanation','code','exercise') "
            "AND ordinal BETWEEN 1 AND 2 AND used BETWEEN 0 AND 2",
            name="correction_permit_bounds",
        ),
    )
    op.create_table(
        "learning_generation_attempts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "operation_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("learning_operations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column(
            "permit_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("learning_correction_permits.id", ondelete="RESTRICT"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("operation_id", "ordinal"),
    )
    op.execute(
        "CREATE TRIGGER immutable_learning_attempt BEFORE UPDATE OR DELETE ON "
        "learning_generation_attempts FOR EACH ROW EXECUTE FUNCTION immutable_plan_check_evidence()"
    )

    op.execute("""CREATE FUNCTION protect_correction_permit() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'correction permit cannot be refunded'; END IF;
      IF (NEW.id,NEW.operation_id,NEW.role,NEW.ordinal,NEW.created_at)
         IS DISTINCT FROM (OLD.id,OLD.operation_id,OLD.role,OLD.ordinal,OLD.created_at)
         OR NEW.used <> OLD.used+1 THEN
         RAISE EXCEPTION 'correction permit only consumes one slot'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute(
        "CREATE TRIGGER protect_permit BEFORE UPDATE OR DELETE ON "
        "learning_correction_permits FOR EACH ROW EXECUTE FUNCTION protect_correction_permit()"
    )


def downgrade():
    op.execute(
        """DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM learning_generation_attempts)
        OR EXISTS(SELECT 1 FROM learning_correction_permits)
        OR EXISTS(SELECT 1 FROM learning_operations WHERE generation_budget_version IS NOT NULL)
        THEN RAISE EXCEPTION 'budget evidence prevents downgrade'; END IF; END $$"""
    )
    op.drop_table("learning_generation_attempts")
    op.drop_table("learning_correction_permits")
    op.execute("DROP FUNCTION protect_correction_permit()")
    op.drop_constraint("learning_budget_counters", "learning_operations", type_="check")
    for name in [
        "generation_tail_remaining",
        "generation_rebuild_count",
        "generation_mapping_count",
        "generation_budget_version",
    ]:
        op.drop_column("learning_operations", name)
