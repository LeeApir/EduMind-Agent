"""Immutable owner-scoped shared teaching plans."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.learning import utc_now


class LearningPlanVersion(Base):
    __tablename__ = "learning_plan_versions"
    __table_args__ = (
        UniqueConstraint("user_id", "learning_unit_id", "version"),
        UniqueConstraint("user_id", "learning_unit_id", "id"),
        UniqueConstraint("learning_unit_id", "id"),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "origin_operation_id"],
            [
                "learning_operations.user_id",
                "learning_operations.learning_unit_id",
                "learning_operations.id",
            ],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    origin_operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    references_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    policy_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    plan_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    plan_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    references_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
