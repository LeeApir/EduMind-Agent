"""Append-only hybrid review records; no publication privileges."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision = "0027_learning_reviews"
down_revision = "0026_learning_plans"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_review_records",
        *[
            sa.Column(k, pg.UUID(as_uuid=True), primary_key=k == "id", nullable=False)
            for k in ("id", "user_id", "learning_unit_id", "plan_id", "operation_id")
        ],
        sa.Column("target_digest", sa.String(64), nullable=False),
        sa.Column("record", pg.JSONB(), nullable=False),
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
    )
    op.execute(
        "CREATE TRIGGER immutable_review BEFORE UPDATE ON learning_review_records "
        "FOR EACH ROW EXECUTE FUNCTION immutable_learning_plan()"
    )


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM learning_review_records) THEN
       RAISE EXCEPTION 'review data prevents downgrade'; END IF; END $$""")
    op.drop_table("learning_review_records")
