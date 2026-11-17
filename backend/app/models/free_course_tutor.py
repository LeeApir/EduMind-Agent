"""Immutable exact-version tutor inputs and separately append-only reply facts."""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity
from app.models.free_course_progress import owner_fk


class FreeCourseTutorTurn(Identity, Base):
    __tablename__ = "free_course_tutor_turns"
    __table_args__ = (
        owner_fk("free_course_operations", "operation_id", "fk_fc_tutor_operation", cascade=True),
        owner_fk("free_course_versions", "course_version_id", "fk_fc_tutor_manifest"),
        owner_fk("free_course_scene_versions", "scene_version_id", "fk_fc_tutor_scene"),
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_tutor_identity"),
        UniqueConstraint("operation_id", name="uq_fc_tutor_operation"),
        CheckConstraint("length(btrim(message)) BETWEEN 1 AND 2000", name="ck_fc_tutor_message"),
        CheckConstraint("context_digest ~ '^[0-9a-f]{64}$'", name="ck_fc_tutor_digest"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    course_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    binding_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sources_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    context_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class FreeCourseTutorReply(Identity, Base):
    __tablename__ = "free_course_tutor_replies"
    __table_args__ = (
        owner_fk("free_course_tutor_turns", "turn_id", "fk_fc_tutor_reply_turn", cascade=True),
        UniqueConstraint("turn_id", name="uq_fc_tutor_reply"),
        CheckConstraint(
            "length(btrim(markdown)) BETWEEN 1 AND 6000", name="ck_fc_tutor_reply_body"
        ),
        CheckConstraint(
            "jsonb_typeof(anchor_refs)='array' AND jsonb_array_length(anchor_refs)<=32",
            name="ck_fc_tutor_reply_refs",
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    turn_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_refs: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    reply_digest: Mapped[str] = mapped_column(String(64), nullable=False)
