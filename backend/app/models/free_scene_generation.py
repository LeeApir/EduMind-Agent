"""Append-only scene candidate audit, bound to an exact request and operation fence."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity


class FreeSceneGenerationResult(Identity, Base):
    __tablename__ = "free_course_scene_generation_results"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_scene_gen_identity"),
        CheckConstraint(
            "lease_epoch >= 1 AND (expected_head IS NULL OR expected_head>0)",
            name="ck_fc_scene_gen_epoch",
        ),
        CheckConstraint(
            "input_digest ~ '^[0-9a-f]{64}$' AND "
            "request_digest ~ '^[0-9a-f]{64}$' AND response_digest ~ '^[0-9a-f]{64}$'",
            name="ck_fc_scene_gen_digests",
        ),
        UniqueConstraint(
            "user_id",
            "course_id",
            "operation_id",
            "scene_id",
            "call_key",
            name="uq_fc_scene_gen_call",
        ),
        ForeignKeyConstraint(
            ["user_id", "course_id", "operation_id"],
            [
                "free_course_operations.user_id",
                "free_course_operations.course_id",
                "free_course_operations.id",
            ],
            ondelete="CASCADE",
            name="fk_fc_scene_gen_operation",
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
            name="fk_fc_scene_gen_request",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["user_id", "course_id", "plan_id"],
            ["free_course_plans.user_id", "free_course_plans.course_id", "free_course_plans.id"],
            name="fk_fc_scene_gen_plan",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["user_id", "course_id", "scene_id"],
            ["free_course_scenes.user_id", "free_course_scenes.course_id", "free_course_scenes.id"],
            name="fk_fc_scene_gen_scene",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "(origin_type='model_generation' AND sent_attempts=1) OR "
            "(origin_type='existing_real_candidate_replay' AND sent_attempts=0 "
            "AND usage_json IS NULL)",
            name="ck_fc_scene_gen_sent",
        ),
        CheckConstraint("state IN ('candidate','failed')", name="ck_fc_scene_gen_state"),
        CheckConstraint(
            "(state='candidate' AND reason_code IS NULL) OR "
            "(state='failed' AND reason_code IS NOT NULL AND reason_code IN "
            "('SCHEMA_INVALID','PROVIDER_REJECTED','OUTCOME_UNKNOWN'))",
            name="ck_fc_scene_gen_result",
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
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sent_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    origin_type: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="model_generation"
    )
    usage_json: Mapped[dict[str, int | None] | None] = mapped_column(JSONB(none_as_null=True))
