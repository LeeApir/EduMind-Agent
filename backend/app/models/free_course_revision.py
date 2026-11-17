"""Private immutable revision requests, plan bindings and staged scene provenance."""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity
from app.models.free_course_progress import owner_fk


class FreeCourseRevision(Identity, Base):
    __tablename__ = "free_course_revisions"
    __table_args__ = (
        owner_fk(
            "free_course_operations", "operation_id", "fk_fc_revision_operation", cascade=True
        ),
        UniqueConstraint("operation_id", name="uq_fc_revision_operation"),
        CheckConstraint(
            "kind IN ('revise_scene','adjust_outline') AND "
            "((base_head IS NOT NULL AND base_head>0) OR "
            "(base_head IS NULL AND kind='adjust_outline'))",
            name="ck_fc_revision_kind",
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    base_head: Mapped[int | None] = mapped_column(Integer)
    instruction: Mapped[str] = mapped_column(String(4000), nullable=False)
    impact_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    impact_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class FreeCourseRevisionPlan(Identity, Base):
    __tablename__ = "free_course_revision_plans"
    __table_args__ = (
        owner_fk(
            "free_course_operations", "operation_id", "fk_fc_revision_plan_operation", cascade=True
        ),
        owner_fk("free_course_plans", "plan_id", "fk_fc_revision_plan_plan"),
        UniqueConstraint("operation_id", name="uq_fc_revision_plan_operation"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class FreeCourseRevisionStage(Identity, Base):
    __tablename__ = "free_course_revision_stages"
    __table_args__ = (
        owner_fk(
            "free_course_operations", "operation_id", "fk_fc_revision_stage_operation", cascade=True
        ),
        owner_fk("free_course_scenes", "scene_id", "fk_fc_revision_stage_scene"),
        owner_fk("free_course_scene_versions", "scene_version_id", "fk_fc_revision_stage_version"),
        owner_fk("free_course_scene_versions", "source_version_id", "fk_fc_revision_stage_source"),
        owner_fk(
            "free_course_scene_presentations",
            "presentation_id",
            "fk_fc_revision_stage_presentation",
        ),
        UniqueConstraint("operation_id", "scene_id", name="uq_fc_revision_stage_scene"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    presentation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
