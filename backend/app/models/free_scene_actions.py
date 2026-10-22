"""Immutable derived presentation data, distinct from media execution and publication."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity


class FreeScenePresentation(Identity, Base):
    __tablename__ = "free_course_scene_presentations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "course_id", "validation_id"],
            [
                "free_course_scene_validations.user_id",
                "free_course_scene_validations.course_id",
                "free_course_scene_validations.id",
            ],
            name="fk_fc_presentation_validation",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint(
            "user_id",
            "course_id",
            "validation_id",
            "rule_version",
            "fallback_key",
            name="uq_fc_presentation_version",
        ),
        CheckConstraint("presentation_digest ~ '^[0-9a-f]{64}$'", name="ck_fc_presentation_digest"),
        CheckConstraint(
            "fallback_key IN ('none','MEDIA_UNAVAILABLE','RENDERER_UNAVAILABLE',"
            "'ACTION_UNAVAILABLE')",
            name="ck_fc_presentation_fallback",
        ),
        CheckConstraint(
            "jsonb_typeof(presentation_json)='object'", name="ck_fc_presentation_payload"
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    validation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    fallback_key: Mapped[str] = mapped_column(String(64), nullable=False)
    presentation_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    presentation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
