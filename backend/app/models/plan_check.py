"""Append-only, owner-bound plan inspection evidence; no publication privileges."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.learning import utc_now


class PlanCheck(Base):
    __tablename__ = "learning_plan_checks"
    __table_args__ = (
        UniqueConstraint("operation_id", "plan_id", "stage"),
        UniqueConstraint("user_id", "learning_unit_id", "operation_id", "plan_id", "id"),
        CheckConstraint("stage IN ('plan_check', 'plan_recheck')", name="plan_check_stage"),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "plan_id"],
            [
                "learning_plan_versions.user_id",
                "learning_plan_versions.learning_unit_id",
                "learning_plan_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "operation_id"],
            [
                "learning_operations.user_id",
                "learning_operations.learning_unit_id",
                "learning_operations.id",
            ],
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    record_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    record: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PlanCheckChild:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    check_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    record_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    record: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def parent_check_constraint() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["user_id", "learning_unit_id", "operation_id", "plan_id", "check_id"],
        [
            "learning_plan_checks." + s
            for s in ["user_id", "learning_unit_id", "operation_id", "plan_id", "id"]
        ],
        ondelete="RESTRICT",
    )


class PlanRebuildEvent(PlanCheckChild, Base):
    __tablename__ = "learning_plan_rebuild_events"
    __table_args__ = (
        parent_check_constraint(),
        Index(
            "uq_plan_rebuild_terminal",
            "operation_id",
            unique=True,
            postgresql_where=text("event_type IN ('completed', 'failed')"),
        ),
        UniqueConstraint("operation_id", "event_type"),
        CheckConstraint(
            "event_type IN ('reserved', 'completed', 'failed')", name="plan_rebuild_event_type"
        ),
    )
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)


class PlanCheckResolution(PlanCheckChild, Base):
    __tablename__ = "learning_plan_check_resolutions"
    __table_args__ = (parent_check_constraint(), UniqueConstraint("user_id", "idempotency_key"))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
