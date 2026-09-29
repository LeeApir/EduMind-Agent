"""Keep immutable classroom command receipts for idempotent replay.

Revision ID: 0014_classroom_receipts
Revises: 0013_classroom_operations
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014_classroom_receipts"
down_revision = "0013_classroom_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("classroom_operations", sa.Column("result_snapshot", postgresql.JSONB()))
    op.drop_constraint("ck_classroom_operations_kind", "classroom_operations", type_="check")
    op.create_check_constraint(
        "ck_classroom_operations_kind",
        "classroom_operations",
        "kind IN ('create', 'mode', 'control', 'speech', 'reexplanation', 'debate')",
    )


def downgrade() -> None:
    op.execute("UPDATE classroom_operations SET kind = 'mode' WHERE kind = 'create'")
    op.drop_constraint("ck_classroom_operations_kind", "classroom_operations", type_="check")
    op.create_check_constraint(
        "ck_classroom_operations_kind",
        "classroom_operations",
        "kind IN ('mode', 'control', 'speech', 'reexplanation', 'debate')",
    )
    op.drop_column("classroom_operations", "result_snapshot")
