"""Append-only owner/course-bound explicit operation lineage; legacy operation rows unchanged."""

from uuid import UUID

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity
from app.models.free_course_progress import owner_fk


class FreeCourseOperationSource(Identity, Base):
    __tablename__ = "free_course_operation_sources"
    __table_args__ = (
        owner_fk("free_course_operations", "operation_id", "fk_fc_source_operation", cascade=True),
        owner_fk("free_course_operations", "source_operation_id", "fk_fc_source_parent"),
        UniqueConstraint("operation_id", name="uq_fc_operation_source"),
        CheckConstraint("operation_id<>source_operation_id", name="ck_fc_source_distinct"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_operation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
