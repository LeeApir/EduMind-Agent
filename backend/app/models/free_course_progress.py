"""Durable incremental scene steps and append-only public-safe event identifiers."""

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
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


def owner_fk(table: str, column: str, name: str, *, cascade: bool = False) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["user_id", "course_id", column],
        [f"{table}.user_id", f"{table}.course_id", f"{table}.id"],
        name=name,
        ondelete="CASCADE" if cascade else None,
        deferrable=True,
        initially="DEFERRED",
    )


class FreeCourseStep(Identity, Base):
    __tablename__ = "free_course_steps"
    __table_args__ = (
        owner_fk("free_course_operations", "operation_id", "fk_fc_step_operation", cascade=True),
        owner_fk("free_course_plans", "plan_id", "fk_fc_step_plan"),
        owner_fk("free_course_scenes", "scene_id", "fk_fc_step_scene"),
        owner_fk("free_course_scene_versions", "scene_version_id", "fk_fc_step_version"),
        UniqueConstraint("user_id", "course_id", "operation_id", "step_key", name="uq_fc_step_key"),
        UniqueConstraint(
            "user_id", "course_id", "operation_id", "scene_id", name="uq_fc_step_scene"
        ),
        CheckConstraint(
            "state IN ('pending','blocked_dependency','running','ready','failed',"
            "'invalidated','cancelled')",
            name="ck_fc_step_state",
        ),
        CheckConstraint(
            "(state='ready' AND scene_version_id IS NOT NULL AND presentation_id IS NOT NULL "
            "AND reason_code IS NULL) OR state<>'ready'",
            name="ck_fc_step_ready",
        ),
        owner_fk("free_course_scene_presentations", "presentation_id", "fk_fc_step_presentation"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    scene_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    presentation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class FreeCourseEvent(Identity, Base):
    __tablename__ = "free_course_events"
    __table_args__ = (
        owner_fk("free_course_operations", "operation_id", "fk_fc_event_operation", cascade=True),
        owner_fk("free_course_versions", "course_version_id", "fk_fc_event_version"),
        UniqueConstraint("operation_id", "seq", name="uq_fc_event_seq"),
        Index(
            "uq_fc_event_first_scene",
            "course_id",
            unique=True,
            postgresql_where=text("event_type='first_scene_ready'"),
        ),
        CheckConstraint("seq BETWEEN 1 AND 256", name="ck_fc_event_seq"),
        CheckConstraint(
            "event_type IN ('queued','started','clarification_required','outline_ready',"
            "'scene_started','scene_ready','first_scene_ready','progress',"
            "'cancel_requested','error','done')",
            name="ck_fc_event_type",
        ),
        CheckConstraint("jsonb_typeof(payload)='object'", name="ck_fc_event_payload"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    course_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
