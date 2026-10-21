"""Owner-bound immutable review case payloads and append-only human decisions."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.learning import utc_now


class LearningReviewCase(Base):
    __tablename__ = "learning_review_cases"
    __table_args__ = (
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
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LearningReviewDecision(Base):
    __tablename__ = "learning_review_decisions"
    __table_args__ = (
        UniqueConstraint("case_id"),
        UniqueConstraint("user_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "case_id"],
            [
                "learning_review_cases.user_id",
                "learning_review_cases.learning_unit_id",
                "learning_review_cases.id",
            ],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    identity_source: Mapped[str] = mapped_column(String(128), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
