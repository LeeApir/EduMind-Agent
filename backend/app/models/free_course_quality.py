"""Accurate immutable feedback, trusted decisions and append-only visibility facts."""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity
from app.models.free_course_progress import owner_fk


class FreeCourseFeedback(Identity, Base):
    __tablename__ = "free_course_feedback"
    __table_args__ = (
        owner_fk(
            "free_course_versions", "course_version_id", "fk_fc_feedback_manifest", cascade=True
        ),
        owner_fk("free_course_scene_versions", "scene_version_id", "fk_fc_feedback_scene"),
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_feedback_identity"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    course_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    location_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="student")


class FreeCourseQualityDecision(Identity, Base):
    __tablename__ = "free_course_quality_decisions"
    __table_args__ = (
        owner_fk(
            "free_course_versions", "course_version_id", "fk_fc_decision_manifest", cascade=True
        ),
        owner_fk("free_course_scene_versions", "scene_version_id", "fk_fc_decision_scene"),
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_decision_identity"),
        UniqueConstraint("user_id", "decision_key", name="uq_fc_decision_key"),
        CheckConstraint(
            "action IN ('confirm_defect','not_confirmed','decision_correction','restore')",
            name="ck_fc_decision_action",
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    course_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    authority: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    impact_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class FreeCourseVisibilityFact(Identity, Base):
    __tablename__ = "free_course_visibility_facts"
    __table_args__ = (
        owner_fk(
            "free_course_quality_decisions",
            "decision_id",
            "fk_fc_visibility_decision",
            cascade=True,
        ),
        owner_fk("free_course_scene_versions", "scene_version_id", "fk_fc_visibility_scene"),
        CheckConstraint(
            "action IN ('disable','restore') AND scope IN ('scene','exercise')",
            name="ck_fc_visibility_action",
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    anchor_id: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
