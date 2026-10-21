"""Durable generation phase and public review summary, without private content."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision = "0030_learning_phases"
down_revision = "0029_learning_publications"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("learning_operations", sa.Column("phase", sa.String(32)))
    op.add_column("learning_operations", sa.Column("review_summary", pg.JSONB()))


def downgrade():
    op.drop_column("learning_operations", "review_summary")
    op.drop_column("learning_operations", "phase")
