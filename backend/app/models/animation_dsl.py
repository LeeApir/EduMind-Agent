"""Immutable owner-scoped DSL candidates, safe review audits and append-only revocations."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.learning import utc_now


class DSLPolicy(Base):
    __tablename__ = "animation_dsl_policies"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DSLPolicyRevocation(Base):
    __tablename__ = "animation_dsl_policy_revocations"
    __table_args__ = (ForeignKeyConstraint(["policy_id"], ["animation_dsl_policies.id"]),)
    policy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DSLReviewRecord(Base):
    __tablename__ = "animation_dsl_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["learning_unit_id", "scene_id", "scene_version"],
            ["learning_scenes.learning_unit_id", "learning_scenes.id", "learning_scenes.version"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "user_id",
            "learning_unit_id",
            "scene_id",
            "scene_version",
            "id",
            "verdict",
            "binding_sha256",
            name="uq_dsl_review_bound_pass",
        ),
        CheckConstraint(
            "verdict IN ('pass','revise','reject','unavailable')", name="ck_dsl_review_verdict"
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_version: Mapped[int] = mapped_column(nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    binding_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    review_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    issue_positions: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DSLCandidate(Base):
    __tablename__ = "animation_dsl_candidates"
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_dsl_candidate_owner_id"),
        UniqueConstraint(
            "user_id",
            "learning_unit_id",
            "scene_id",
            "scene_version",
            "id",
            name="uq_dsl_candidate_owner_target",
        ),
        ForeignKeyConstraint(
            [
                "user_id",
                "learning_unit_id",
                "scene_id",
                "scene_version",
                "review_id",
                "verdict",
                "binding_sha256",
            ],
            [
                "animation_dsl_reviews.user_id",
                "animation_dsl_reviews.learning_unit_id",
                "animation_dsl_reviews.scene_id",
                "animation_dsl_reviews.scene_version",
                "animation_dsl_reviews.id",
                "animation_dsl_reviews.verdict",
                "animation_dsl_reviews.binding_sha256",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["policy_id"], ["animation_dsl_policies.id"]),
        CheckConstraint("verdict = 'pass'", name="ck_dsl_candidate_pass"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    learning_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_version: Mapped[int] = mapped_column(nullable=False)
    review_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False, default="pass")
    binding_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_dsl: Mapped[str] = mapped_column(Text, nullable=False)
    trace_json: Mapped[str] = mapped_column(Text, nullable=False)
    dsl_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DSLCandidateRevocation(Base):
    __tablename__ = "animation_dsl_candidate_revocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "candidate_id"],
            ["animation_dsl_candidates.user_id", "animation_dsl_candidates.id"],
            ondelete="CASCADE",
        ),
    )
    candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
