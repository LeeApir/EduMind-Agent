"""Track idempotency for manual profile corrections.

Revision ID: 0006_profile_correction
Revises: 0005_profile_events
Create Date: 2026-09-23
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_profile_correction"
down_revision = "0005_profile_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("student_profiles", sa.Column("idempotency_key", sa.String(128)))
    op.add_column("student_profiles", sa.Column("request_digest", sa.String(64)))
    op.create_unique_constraint(
        "uq_student_profiles_user_idempotency_key",
        "student_profiles",
        ["user_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_student_profiles_user_idempotency_key", "student_profiles", type_="unique"
    )
    op.drop_column("student_profiles", "request_digest")
    op.drop_column("student_profiles", "idempotency_key")
