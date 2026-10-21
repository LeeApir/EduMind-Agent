"""Immutable planned publication snapshots and append-only withdrawal facts."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.learning import utc_now


class LearningPublication(Base):
    __tablename__ = "learning_publications"
    __table_args__ = (
        UniqueConstraint("user_id", "learning_unit_id", "version"),
        UniqueConstraint("user_id", "learning_unit_id", "id"),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "plan_id"],
            [
                "learning_plan_versions.user_id",
                "learning_plan_versions.learning_unit_id",
                "learning_plan_versions.id",
            ],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    material: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    review_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    approval_source: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LearningPublicationWithdrawal(Base):
    __tablename__ = "learning_publication_withdrawals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "publication_id"],
            [
                "learning_publications.user_id",
                "learning_publications.learning_unit_id",
                "learning_publications.id",
            ],
            ondelete="CASCADE",
        ),
    )
    publication_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
