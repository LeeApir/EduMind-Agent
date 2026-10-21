"""Freeze explicit teaching selection without inferring any historical node."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0031_teaching_context"
down_revision = "0030_learning_phases"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("learning_operations", sa.Column("teaching_context", pg.JSONB()))
    op.create_check_constraint(
        "ck_operation_teaching_object",
        "learning_operations",
        "teaching_context IS NULL OR jsonb_typeof(teaching_context) = 'object'",
    )
    op.execute("""CREATE FUNCTION protect_teaching_context() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.teaching_context IS NOT NULL AND
             NEW.teaching_context IS DISTINCT FROM OLD.teaching_context THEN
            RAISE EXCEPTION 'immutable teaching context' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END; $$""")
    op.execute("""CREATE TRIGGER immutable_teaching_context BEFORE UPDATE ON learning_operations
        FOR EACH ROW EXECUTE FUNCTION protect_teaching_context()""")


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM learning_operations WHERE teaching_context IS NOT NULL) THEN
        RAISE EXCEPTION 'teaching data prevents downgrade'; END IF; END $$""")
    op.execute("DROP TRIGGER immutable_teaching_context ON learning_operations")
    op.execute("DROP FUNCTION protect_teaching_context()")
    op.drop_constraint("ck_operation_teaching_object", "learning_operations")
    op.drop_column("learning_operations", "teaching_context")
