"""Immutable generated exercise versions, raw attempts and assessment exposure facts."""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity
from app.models.free_course_progress import owner_fk


class FreeCourseExerciseVersion(Identity, Base):
    __tablename__ = "free_course_exercise_versions"
    __table_args__ = (
        owner_fk(
            "free_course_scene_versions", "scene_version_id", "fk_fc_exercise_scene", cascade=True
        ),
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_exercise_identity"),
        UniqueConstraint(
            "user_id", "course_id", "scene_version_id", "anchor_id", name="uq_fc_exercise_anchor"
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    exercise_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    anchor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    context_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    assessment_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    question_stem_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)


class FreeCourseAnswerAttempt(Identity, Base):
    __tablename__ = "free_course_attempts_answers"
    __table_args__ = (
        owner_fk(
            "free_course_versions", "course_version_id", "fk_fc_answers_manifest", cascade=True
        ),
        owner_fk("free_course_exercise_versions", "exercise_version_id", "fk_fc_answers_exercise"),
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_answers_identity"),
        UniqueConstraint("user_id", "id", name="uq_fc_answers_owner"),
        CheckConstraint(
            "completeness IN ('incomplete','complete')", name="ck_fc_answers_completeness"
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    course_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    exercise_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    binding_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    answers_json: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    completeness: Mapped[str] = mapped_column(String(16), nullable=False)
    feedback_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    qualification_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class FreeCourseAssessmentExposure(Identity, Base):
    __tablename__ = "free_course_assessment_exposures"
    __table_args__ = (
        owner_fk(
            "free_course_exercise_versions",
            "exercise_version_id",
            "fk_fc_exposure_exercise",
            cascade=True,
        ),
        CheckConstraint("kind IN ('help','solution','first_complete')", name="ck_fc_exposure_kind"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    exercise_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    assessment_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    question_stem_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    binding_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
