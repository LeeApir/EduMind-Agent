"""Durable conservative outbound reservations, settlements and two global execution slots."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity
from app.models.free_course_progress import owner_fk


class FreeCourseAttempt(Identity, Base):
    __tablename__ = "free_course_attempts"
    __table_args__ = (
        owner_fk("free_course_operations", "operation_id", "fk_fc_attempt_operation", cascade=True),
        owner_fk("free_course_steps", "step_id", "fk_fc_attempt_step"),
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_attempt_identity"),
        UniqueConstraint("operation_id", "step_id", "purpose", name="uq_fc_attempt_purpose"),
        CheckConstraint(
            "purpose IN ('primary','transport_retry','format_repair')", name="ck_fc_attempt_purpose"
        ),
        CheckConstraint(
            "input_tokens BETWEEN 1 AND 32000 AND output_tokens BETWEEN 1 AND 8000",
            name="ck_fc_attempt_tokens",
        ),
        CheckConstraint("lease_epoch>0 AND fee_micros>=0", name="ck_fc_attempt_reservation"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    step_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_micros: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class FreeCourseSettlement(Identity, Base):
    __tablename__ = "free_course_settlements"
    __table_args__ = (
        owner_fk("free_course_attempts", "attempt_id", "fk_fc_settlement_attempt", cascade=True),
        UniqueConstraint("attempt_id", name="uq_fc_settlement_attempt"),
        CheckConstraint(
            "evidence IN ('complete_response','not_executed','stopped')",
            name="ck_fc_settlement_evidence",
        ),
        CheckConstraint(
            "(input_tokens IS NULL AND output_tokens IS NULL) OR (input_tokens>=0 AND "
            "output_tokens>=0)",
            name="ck_fc_settlement_tokens",
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evidence: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    outcome_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class FreeCourseCapacity(Base):
    __tablename__ = "free_course_capacity"
    __table_args__ = (
        CheckConstraint("slot IN (1,2)", name="ck_fc_capacity_slot"),
        CheckConstraint("state IN ('free','held','quarantined')", name="ck_fc_capacity_state"),
        CheckConstraint(
            "(state='free' AND operation_id IS NULL AND user_id IS NULL AND course_id IS NULL "
            "AND pending_attempt_id IS NULL AND epoch IS NULL AND expires_at IS NULL) OR "
            "(state<>'free' AND operation_id IS NOT NULL AND user_id IS NOT NULL AND "
            "course_id IS NOT NULL AND epoch>0 AND expires_at IS NOT NULL)",
            name="ck_fc_capacity_binding",
        ),
        UniqueConstraint("operation_id", name="uq_fc_capacity_operation"),
        ForeignKeyConstraint(
            ["user_id", "course_id", "operation_id"],
            [
                "free_course_operations.user_id",
                "free_course_operations.course_id",
                "free_course_operations.id",
            ],
            name="fk_fc_capacity_operation",
        ),
    )
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    course_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    operation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    epoch: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_attempt_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class FreeCourseDispatch(Identity, Base):
    __tablename__ = "free_course_dispatches"
    __table_args__ = (
        owner_fk("free_course_attempts", "attempt_id", "fk_fc_dispatch_attempt", cascade=True),
        UniqueConstraint("attempt_id", name="uq_fc_dispatch_attempt"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
