"""Add explicit curated provenance without rewriting generated approval history."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0016_catalog_releases"
down_revision = "0015_debate_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_releases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("package_id", sa.String(80), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        sa.Column("graph_version", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("approval", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="approved"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("package_id", "version", name="uq_catalog_release_version"),
        sa.UniqueConstraint("manifest_digest", name="uq_catalog_release_digest"),
        sa.CheckConstraint("status IN ('approved', 'revoked')", name="ck_catalog_release_status"),
    )
    for table in ("learning_units", "generated_resources"):
        op.add_column(table, sa.Column("catalog_release_id", postgresql.UUID(as_uuid=True)))
        op.create_foreign_key(f"fk_{table}_catalog_release", table, "catalog_releases",
                              ["catalog_release_id"], ["id"])
    op.add_column("generated_resources", sa.Column("origin_type", sa.String(16),
                  nullable=False, server_default="generated"))
    op.add_column("generated_resources", sa.Column("catalog_content_digest", sa.String(64)))
    op.create_check_constraint("ck_generated_resources_origin", "generated_resources",
        "(origin_type = 'generated' AND catalog_release_id IS NULL "
        "AND catalog_content_digest IS NULL) OR (origin_type = 'curated' "
        "AND catalog_release_id IS NOT NULL AND catalog_content_digest IS NOT NULL)")


def downgrade() -> None:
    op.drop_constraint("ck_generated_resources_origin", "generated_resources", type_="check")
    op.drop_column("generated_resources", "catalog_content_digest")
    op.drop_column("generated_resources", "origin_type")
    for table in ("generated_resources", "learning_units"):
        op.drop_constraint(f"fk_{table}_catalog_release", table, type_="foreignkey")
        op.drop_column(table, "catalog_release_id")
    op.drop_table("catalog_releases")
