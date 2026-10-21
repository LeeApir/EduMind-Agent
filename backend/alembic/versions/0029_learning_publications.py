"""Atomic planned unit publication snapshots and withdrawal facts."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision = "0029_learning_publications"
down_revision = "0028_learning_review_cases"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("learning_operations", sa.Column("publication_expectation", pg.JSONB()))
    op.drop_constraint("ck_classroom_operations_status", "classroom_operations")
    op.create_check_constraint(
        "ck_classroom_operations_status",
        "classroom_operations",
        "status IN ('accepted','running','published','failed','cancelled','superseded',"
        "'awaiting_human','rejected')",
    )
    op.add_column(
        "learning_operations",
        sa.Column("generation_call_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "learning_operations", sa.Column("generation_deadline", sa.DateTime(timezone=True))
    )
    op.create_unique_constraint(
        "uq_decision_target", "learning_review_decisions", ["user_id", "learning_unit_id", "id"]
    )
    op.create_table(
        "learning_publications",
        *[
            sa.Column(k, pg.UUID(as_uuid=True), primary_key=k == "id", nullable=False)
            for k in ("id", "user_id", "learning_unit_id", "plan_id", "operation_id")
        ],
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("unit_digest", sa.String(64), nullable=False),
        sa.Column("material", pg.JSONB(), nullable=False),
        sa.Column("review_ids", pg.JSONB(), nullable=False),
        sa.Column("approval_source", sa.String(20), nullable=False),
        sa.Column("decision_id", pg.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "learning_unit_id", "id"),
        sa.UniqueConstraint("user_id", "learning_unit_id", "version"),
        sa.UniqueConstraint("operation_id"),
        sa.CheckConstraint("version>=1"),
        sa.CheckConstraint(
            "(approval_source='auto' AND decision_id IS NULL) OR "
            "(approval_source='human_assisted' AND decision_id IS NOT NULL)"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "plan_id"],
            [
                "learning_plan_versions.user_id",
                "learning_plan_versions.learning_unit_id",
                "learning_plan_versions.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "operation_id"],
            [
                "learning_operations.user_id",
                "learning_operations.learning_unit_id",
                "learning_operations.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "decision_id"],
            [
                "learning_review_decisions.user_id",
                "learning_review_decisions.learning_unit_id",
                "learning_review_decisions.id",
            ],
        ),
    )
    op.create_table(
        "learning_publication_withdrawals",
        sa.Column("publication_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("learning_unit_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "publication_id"],
            [
                "learning_publications.user_id",
                "learning_publications.learning_unit_id",
                "learning_publications.id",
            ],
            ondelete="CASCADE",
        ),
    )
    for table in ("learning_publications", "learning_publication_withdrawals"):
        op.execute(
            f"CREATE TRIGGER immutable_publication BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION immutable_learning_plan()"
        )
    op.add_column("learning_units", sa.Column("current_publication_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_unit_current_publication",
        "learning_units",
        "learning_publications",
        ["user_id", "id", "current_publication_id"],
        ["user_id", "learning_unit_id", "id"],
    )
    op.add_column("classroom_sessions", sa.Column("publication_version", sa.Integer()))


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM learning_publications) THEN
      RAISE EXCEPTION 'publication data prevents downgrade'; END IF; END $$""")
    op.drop_constraint("ck_classroom_operations_status", "classroom_operations")
    op.create_check_constraint(
        "ck_classroom_operations_status",
        "classroom_operations",
        "status IN ('accepted','running','published','failed','cancelled','superseded')",
    )
    op.drop_column("learning_operations", "publication_expectation")
    op.drop_column("learning_operations", "generation_call_count")
    op.drop_column("learning_operations", "generation_deadline")
    op.drop_column("classroom_sessions", "publication_version")
    op.drop_constraint("fk_unit_current_publication", "learning_units")
    op.drop_column("learning_units", "current_publication_id")
    op.drop_table("learning_publication_withdrawals")
    op.drop_table("learning_publications")
    op.drop_constraint("uq_decision_target", "learning_review_decisions")
