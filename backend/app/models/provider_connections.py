"""Owner/session scoped Provider metadata; secrets exist only as envelopes."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base


class ProviderConnection(Base):
    __tablename__ = "provider_connections"
    __table_args__ = (
        CheckConstraint("config_version > 0 AND credential_version > 0"),
        CheckConstraint("credential_mode IN ('none', 'persistent', 'temporary')"),
        CheckConstraint(
            "provider_type IN ('openai-compatible', 'ollama', 'anthropic', 'gemini', 'spark')"
        ),
        CheckConstraint("octet_length(encrypted_api_key) <= 16384"),
        CheckConstraint(
            "encrypted_api_key IS NULL OR (credential_mode = 'persistent' AND NOT deleted)"
        ),
    )
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    originating_session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_local: Mapped[bool] = mapped_column(Boolean, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    credential_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    credential_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    credential_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    encrypted_api_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
