"""Session bounded encrypted Provider connections (ADR-0008)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018_provider_connections"
down_revision = "0017_catalog_immutability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("originating_session_hash", sa.String(64), nullable=False),
        sa.Column("provider_type", sa.String(40), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("is_local", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("credential_mode", sa.String(20), nullable=False),
        sa.Column("credential_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("credential_key_id", sa.String(64), nullable=True),
        sa.Column("encrypted_api_key", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("config_version > 0 AND credential_version > 0"),
        sa.CheckConstraint("credential_mode IN ('none', 'persistent', 'temporary')"),
        sa.CheckConstraint(
            "provider_type IN ('openai-compatible', 'ollama', 'anthropic', 'gemini', 'spark')"
        ),
        sa.CheckConstraint("octet_length(encrypted_api_key) <= 16384"),
        sa.CheckConstraint(
            "encrypted_api_key IS NULL OR (credential_mode = 'persistent' AND NOT deleted)"
        ),
    )
    op.create_index("ix_provider_connections_user_id", "provider_connections", ["user_id"])
    op.create_index(
        "ix_provider_connections_expiry",
        "provider_connections",
        ["credential_expires_at"],
        postgresql_where=sa.text("encrypted_api_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("provider_connections")
