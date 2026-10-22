"""Append-only deterministic validation facts, separate from original candidates/reviews."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity


class FreeSceneValidation(Identity, Base):
    __tablename__ = "free_course_scene_validations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "course_id", "generation_result_id"],
            [
                "free_course_scene_generation_results.user_id",
                "free_course_scene_generation_results.course_id",
                "free_course_scene_generation_results.id",
            ],
            name="fk_fc_validation_candidate",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "user_id",
            "course_id",
            "generation_result_id",
            "rule_version",
            name="uq_fc_validation_rule",
        ),
        CheckConstraint("state IN ('accepted','rejected')", name="ck_fc_validation_state"),
        CheckConstraint("raw_digest ~ '^[0-9a-f]{64}$'", name="ck_fc_validation_raw"),
        CheckConstraint(
            "(state='accepted' AND reason_code IS NULL AND cleaned_digest IS NOT NULL "
            "AND cleaned_digest ~ '^[0-9a-f]{64}$' AND cleaned_json IS NOT NULL "
            "AND jsonb_typeof(cleaned_json)='object') OR "
            "(state='rejected' AND reason_code IS NOT NULL AND cleaned_digest IS NULL "
            "AND (cleaned_json IS NULL OR jsonb_typeof(cleaned_json)='null'))",
            name="ck_fc_validation_result",
        ),
        CheckConstraint("jsonb_typeof(findings)='array'", name="ck_fc_validation_findings"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    generation_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    findings: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    raw_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    cleaned_digest: Mapped[str | None] = mapped_column(String(64))
    cleaned_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
