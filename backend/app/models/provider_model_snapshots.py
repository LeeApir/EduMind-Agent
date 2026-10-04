"""One sanitized model-list snapshot per connection, bound to its config version."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base


class ProviderModelSnapshot(Base):
    __tablename__ = "provider_model_snapshots"
    __table_args__ = (
        CheckConstraint("config_version > 0"),
        CheckConstraint("jsonb_typeof(models) = 'array' AND jsonb_array_length(models) <= 1000"),
    )
    connection_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("provider_connections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    models: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
