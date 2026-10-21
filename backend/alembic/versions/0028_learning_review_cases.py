"""Immutable human-review cases and decisions, with one active case per unit."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision = "0028_learning_review_cases"
down_revision = "0027_learning_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_review_cases",
        *[
            sa.Column(k, pg.UUID(as_uuid=True), primary_key=k == "id", nullable=False)
            for k in ("id", "user_id", "learning_unit_id", "plan_id", "operation_id")
        ],
        sa.Column("case_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        *[
            sa.Column(k, sa.DateTime(timezone=True), nullable=False)
            for k in ("created_at", "updated_at")
        ],
        sa.UniqueConstraint("user_id", "learning_unit_id", "id"),
        sa.CheckConstraint("state IN ('pending','approved','rejected','invalidated','published')"),
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
    op.create_index(
        "uq_current_learning_review_case",
        "learning_review_cases",
        ["user_id", "learning_unit_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('pending','approved')"),
    )
    op.create_table(
        "learning_review_decisions",
        *[
            sa.Column(k, pg.UUID(as_uuid=True), primary_key=k == "id", nullable=False)
            for k in ("id", "user_id", "learning_unit_id", "case_id")
        ],
        *[
            sa.Column(k, sa.String(128), nullable=False)
            for k in ("reviewer_id", "identity_source", "idempotency_key")
        ],
        sa.Column("case_digest", sa.String(64), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("verdict IN ('approve','reject')"),
        sa.UniqueConstraint("case_id"),
        sa.UniqueConstraint("user_id", "idempotency_key"),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "case_id"],
            [
                "learning_review_cases.user_id",
                "learning_review_cases.learning_unit_id",
                "learning_review_cases.id",
            ],
            ondelete="CASCADE",
        ),
    )
    op.execute(
        "CREATE TRIGGER immutable_decision BEFORE UPDATE ON learning_review_decisions "
        "FOR EACH ROW EXECUTE FUNCTION immutable_learning_plan()"
    )
    op.execute("""CREATE FUNCTION protect_learning_case() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
       IF (to_jsonb(NEW)-ARRAY['state','updated_at']) IS DISTINCT FROM
          (to_jsonb(OLD)-ARRAY['state','updated_at']) OR
          NOT ((OLD.state='pending' AND NEW.state IN ('approved','rejected','invalidated')) OR
               (OLD.state='approved' AND NEW.state IN ('published','invalidated')) OR
               OLD.state=NEW.state) THEN
          RAISE EXCEPTION 'immutable review case' USING ERRCODE='23514'; END IF;
       RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER protect_case BEFORE UPDATE ON learning_review_cases "
        "FOR EACH ROW EXECUTE FUNCTION protect_learning_case()"
    )


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM learning_review_cases) THEN
      RAISE EXCEPTION 'review cases prevent downgrade'; END IF; END $$""")
    op.drop_table("learning_review_decisions")
    op.drop_table("learning_review_cases")
    op.execute("DROP FUNCTION protect_learning_case()")
