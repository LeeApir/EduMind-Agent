"""Append-only automatic review audits separate from publication qualification."""

from uuid import UUID

from sqlalchemy import ForeignKeyConstraint, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base


class LearningReviewRecord(Base):
    __tablename__ = "learning_review_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "plan_id"],
            [
                "learning_plan_versions.user_id",
                "learning_plan_versions.learning_unit_id",
                "learning_plan_versions.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "operation_id"],
            [
                "learning_operations.user_id",
                "learning_operations.learning_unit_id",
                "learning_operations.id",
            ],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    target_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    record: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
