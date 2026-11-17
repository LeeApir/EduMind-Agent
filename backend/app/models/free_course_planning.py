"""Append-only planning audit, bound to an exact request and operation fence."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity


class FreeCoursePlanningResult(Identity, Base):
    __tablename__ = "free_course_planning_results"
    __table_args__ = (
        CheckConstraint(
            "lease_epoch >= 1 AND (expected_head IS NULL OR expected_head>0)",
            name="ck_fc_planning_epoch",
        ),
        CheckConstraint(
            "input_digest ~ '^[0-9a-f]{64}$' AND "
            "request_digest ~ '^[0-9a-f]{64}$' AND response_digest ~ '^[0-9a-f]{64}$'",
            name="ck_fc_planning_digests",
        ),
        UniqueConstraint(
            "user_id", "course_id", "operation_id", "call_key", name="uq_fc_planning_call"
        ),
        ForeignKeyConstraint(
            ["user_id", "course_id", "operation_id"],
            [
                "free_course_operations.user_id",
                "free_course_operations.course_id",
                "free_course_operations.id",
            ],
            ondelete="CASCADE",
            name="fk_fc_planning_operation",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["user_id", "course_id", "request_id"],
            [
                "free_course_requests.user_id",
                "free_course_requests.course_id",
                "free_course_requests.id",
            ],
            name="fk_fc_planning_request",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["user_id", "course_id", "plan_id"],
            ["free_course_plans.user_id", "free_course_plans.course_id", "free_course_plans.id"],
            name="fk_fc_planning_plan",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "state IN ('ready','needs_clarification','failed')", name="ck_fc_planning_state"
        ),
        CheckConstraint(
            "(state='ready' AND plan_id IS NOT NULL AND reason_code IS NULL) OR "
            "(state='needs_clarification' AND plan_id IS NULL AND reason_code IS NULL) OR "
            "(state='failed' AND plan_id IS NULL AND reason_code IS NOT NULL AND reason_code IN "
            "('SCHEMA_INVALID','PROVIDER_REJECTED','OUTCOME_UNKNOWN'))",
            name="ck_fc_planning_result",
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    call_key: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_head: Mapped[int | None] = mapped_column(Integer)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    response_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    response_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    plan_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
