"""Trusted exact attestations, coupled evidence admissions and append-only revocations."""

from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.free_course import Identity
from app.models.free_course_progress import owner_fk


class FreeCourseAttestation(Identity, Base):
    __tablename__ = "free_course_attestations"
    __table_args__ = (
        owner_fk(
            "free_course_exercise_versions",
            "exercise_version_id",
            "fk_fc_attest_exercise",
            cascade=True,
        ),
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_attest_identity"),
        UniqueConstraint("user_id", "decision_key", name="uq_fc_attest_key"),
        CheckConstraint(
            "kind IN ('answer_attestation','mapping_attestation')", name="ck_fc_attest_kind"
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    exercise_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    context_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    node_id: Mapped[str | None] = mapped_column(String(64))
    graph_version: Mapped[str | None] = mapped_column(String(64))
    authority: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class FreeCourseAttestationRevocation(Identity, Base):
    __tablename__ = "free_course_attestation_revocations"
    __table_args__ = (
        owner_fk("free_course_attestations", "attestation_id", "fk_fc_attest_revoke", cascade=True),
        UniqueConstraint("attestation_id", name="uq_fc_attest_revoke"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    attestation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reason_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class FreeCourseEvidenceAdmission(Identity, Base):
    __tablename__ = "free_course_evidence_admissions"
    __table_args__ = (
        owner_fk(
            "free_course_attempts_answers", "attempt_id", "fk_fc_admission_attempt", cascade=True
        ),
        owner_fk("free_course_attestations", "answer_attestation_id", "fk_fc_admission_answer"),
        owner_fk("free_course_attestations", "mapping_attestation_id", "fk_fc_admission_mapping"),
        ForeignKeyConstraint(
            ["user_id", "evidence_id"],
            ["learning_evidence.user_id", "learning_evidence.id"],
            name="fk_fc_admission_evidence",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_admission_identity"),
        UniqueConstraint("user_id", "attempt_id", "evidence_id", name="uq_fc_admission_cycle"),
        UniqueConstraint("attempt_id", name="uq_fc_admission_attempt"),
        UniqueConstraint("evidence_id", name="uq_fc_admission_evidence"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    answer_attestation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    mapping_attestation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    binding_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class FreeCourseEvidenceRevocation(Identity, Base):
    __tablename__ = "free_course_evidence_revocations"
    __table_args__ = (
        owner_fk(
            "free_course_evidence_admissions", "admission_id", "fk_fc_evidence_revoke", cascade=True
        ),
        ForeignKeyConstraint(
            ["user_id", "correction_evidence_id"],
            ["learning_evidence.user_id", "learning_evidence.id"],
            name="fk_fc_revoke_correction",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("admission_id", name="uq_fc_evidence_revoke"),
        UniqueConstraint("correction_evidence_id", name="uq_fc_correction_evidence"),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    admission_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    correction_evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reason_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
