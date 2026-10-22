"""Durable snapshot write fences and idempotent receipts; no scheduler or Provider."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity


class FreeCourseOperation(Identity, Base):
    __tablename__ = "free_course_operations"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_operation_identity"),
        ForeignKeyConstraint(
            ["user_id", "course_id", "request_id"],
            [
                "free_course_requests.user_id",
                "free_course_requests.course_id",
                "free_course_requests.id",
            ],
            name="fk_fc_operation_request",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "kind IN ('create','clarify','resume','adjust_outline','revise_scene','tutor_turn')",
            name="ck_fc_operation_kind",
        ),
        CheckConstraint(
            "state IN ('queued','running','cancel_requested','succeeded',"
            "'partially_succeeded','awaiting_clarification','failed','cancelled',"
            "'timed_out')",
            name="ck_fc_operation_state",
        ),
        CheckConstraint(
            "lease_epoch >= 0 AND (base_head_version IS NULL OR base_head_version>0)",
            name="ck_fc_operation_versions",
        ),
        Index(
            "uq_fc_operation_owner_active",
            "user_id",
            unique=True,
            postgresql_where="state IN ('queued','running','cancel_requested')",
        ),
        Index(
            "uq_fc_operation_course_active",
            "course_id",
            unique=True,
            postgresql_where="state IN ('queued','running','cancel_requested')",
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    base_head_version: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="queued")
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now() + interval '600 seconds'"),
    )
    config_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    policy_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FreeCourseReceipt(Base):
    __tablename__ = "free_course_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["free_courses.user_id", "free_courses.id"],
            ondelete="CASCADE",
            name="fk_fc_receipt_course",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("request_digest ~ '^[0-9a-f]{64}$'", name="ck_fc_receipt_digest"),
        CheckConstraint("status_code BETWEEN 200 AND 299", name="ck_fc_receipt_status"),
    )
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    route: Mapped[str] = mapped_column(String(256), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
