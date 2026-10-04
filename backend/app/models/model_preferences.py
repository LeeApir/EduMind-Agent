"""Four owner/original-session route choices, no secret material."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base


class ModelPreference(Base):
    __tablename__ = "model_preferences"
    __table_args__ = (
        CheckConstraint("version > 0"),
        CheckConstraint("task_profile IN ('fast', 'default', 'quality', 'review')"),
        CheckConstraint("jsonb_typeof(fallbacks) = 'array' AND jsonb_array_length(fallbacks) <= 3"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    task_profile: Mapped[str] = mapped_column(String(20), primary_key=True)
    originating_session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    route: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    fallbacks: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
