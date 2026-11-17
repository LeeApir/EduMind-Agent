"""Persist explicit operation lineage as new append-only facts; retain old operation schema."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0042_free_course_recovery"
down_revision = "0041_free_course_scheduler"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "free_course_operation_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_operation_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "course_id", "operation_id"],
            [
                "free_course_operations.user_id",
                "free_course_operations.course_id",
                "free_course_operations.id",
            ],
            name="fk_fc_source_operation",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "course_id", "source_operation_id"],
            [
                "free_course_operations.user_id",
                "free_course_operations.course_id",
                "free_course_operations.id",
            ],
            name="fk_fc_source_parent",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint("operation_id", name="uq_fc_operation_source"),
        sa.CheckConstraint("operation_id<>source_operation_id", name="ck_fc_source_distinct"),
    )
    op.execute(
        "CREATE TRIGGER fc_source_immutable BEFORE UPDATE OR DELETE ON "
        "free_course_operation_sources FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM free_course_operation_sources) THEN
        RAISE EXCEPTION 'recovery lineage prevents downgrade';
      END IF;
    END $$""")
    op.drop_table("free_course_operation_sources")
