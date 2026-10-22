"""Owner-private free-course identities and append-only, exact-version snapshots."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Constraint

from app.models.auth import Base


class Identity:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CourseSnapshot(Identity):
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)


def snapshot_constraints(prefix: str) -> tuple[Constraint, ...]:
    return (
        UniqueConstraint("user_id", "course_id", "id", name=f"uq_{prefix}_identity"),
        UniqueConstraint("user_id", "course_id", "version", name=f"uq_{prefix}_version"),
        ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["free_courses.user_id", "free_courses.id"],
            ondelete="CASCADE",
            name=f"fk_{prefix}_course",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("version >= 1", name=f"ck_{prefix}_positive"),
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name=f"ck_{prefix}_digest"),
    )


class FreeCourse(Identity, Base):
    __tablename__ = "free_courses"
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_free_course_owner"),
        ForeignKeyConstraint(
            ["user_id", "id", "head_version_id"],
            [
                "free_course_versions.user_id",
                "free_course_versions.course_id",
                "free_course_versions.id",
            ],
            name="fk_free_course_head",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "length(btrim(original_goal)) BETWEEN 1 AND 4000", name="ck_free_course_goal"
        ),
        CheckConstraint(
            "teaching_language = 'zh-CN' AND (code_language IS NULL OR code_language = 'C')",
            name="ck_free_course_language",
        ),
        CheckConstraint(
            "course_kind = 'ai_draft' AND endorsement = 'unendorsed'", name="ck_free_course_draft"
        ),
        Index("ix_free_course_owner_created", "user_id", "created_at", "id"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    original_goal: Mapped[str] = mapped_column(Text, nullable=False)
    teaching_language: Mapped[str] = mapped_column(String(16), server_default="zh-CN")
    code_language: Mapped[str | None] = mapped_column(String(16))
    head_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    course_kind: Mapped[str] = mapped_column(String(24), server_default="ai_draft")
    endorsement: Mapped[str] = mapped_column(String(24), server_default="unendorsed")


class FreeCourseRequest(CourseSnapshot, Base):
    __tablename__ = "free_course_requests"
    __table_args__ = (
        *snapshot_constraints("fc_request"),
        ForeignKeyConstraint(
            ["user_id", "course_id", "parent_request_id"],
            [
                "free_course_requests.user_id",
                "free_course_requests.course_id",
                "free_course_requests.id",
            ],
            name="fk_fc_request_parent",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["user_id", "profile_id", "profile_version"],
            ["student_profiles.user_id", "student_profiles.id", "student_profiles.version"],
            name="fk_fc_request_profile",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "(profile_id IS NULL) = (profile_version IS NULL)", name="ck_fc_request_profile_pair"
        ),
        CheckConstraint(
            "(kind = 'original' AND version = 1 AND parent_request_id IS NULL) OR "
            "(kind = 'adjustment' AND version > 1 AND parent_request_id IS NOT NULL)",
            name="ck_fc_request_kind",
        ),
    )
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_request_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    profile_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    profile_version: Mapped[int | None] = mapped_column(Integer)
    evidence_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    nonsecret_config_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class FreeCoursePlan(CourseSnapshot, Base):
    __tablename__ = "free_course_plans"
    __table_args__ = (
        *snapshot_constraints("fc_plan"),
        ForeignKeyConstraint(
            ["user_id", "course_id", "request_id"],
            [
                "free_course_requests.user_id",
                "free_course_requests.course_id",
                "free_course_requests.id",
            ],
            name="fk_fc_plan_request",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class FreeCourseScene(Identity, Base):
    __tablename__ = "free_course_scenes"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_scene_identity"),
        ForeignKeyConstraint(
            ["user_id", "course_id"],
            ["free_courses.user_id", "free_courses.id"],
            ondelete="CASCADE",
            name="fk_fc_scene_course",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class FreeCourseSceneVersion(CourseSnapshot, Base):
    __tablename__ = "free_course_scene_versions"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", "id", name="uq_fc_scene_version_identity"),
        UniqueConstraint(
            "user_id", "course_id", "scene_id", "version", name="uq_fc_scene_version_number"
        ),
        CheckConstraint("version >= 1", name="ck_fc_scene_version_positive"),
        CheckConstraint("content_digest ~ '^[0-9a-f]{64}$'", name="ck_fc_scene_content_digest"),
        ForeignKeyConstraint(
            ["user_id", "course_id", "scene_id"],
            ["free_course_scenes.user_id", "free_course_scenes.course_id", "free_course_scenes.id"],
            ondelete="CASCADE",
            name="fk_fc_scene_version_scene",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["user_id", "course_id", "plan_id"],
            ["free_course_plans.user_id", "free_course_plans.course_id", "free_course_plans.id"],
            name="fk_fc_scene_version_plan",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    scene_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    content_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    actions_json: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    dependency_bindings: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class FreeCourseVersion(CourseSnapshot, Base):
    __tablename__ = "free_course_versions"
    __table_args__ = (
        *snapshot_constraints("fc_version"),
        ForeignKeyConstraint(
            ["user_id", "course_id", "plan_id"],
            ["free_course_plans.user_id", "free_course_plans.course_id", "free_course_plans.id"],
            name="fk_fc_version_plan",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class FreeCourseNodeLink(Base):
    __tablename__ = "free_course_node_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "course_id", "course_version_id"],
            [
                "free_course_versions.user_id",
                "free_course_versions.course_id",
                "free_course_versions.id",
            ],
            ondelete="CASCADE",
            name="fk_fc_link_version",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["user_id", "course_id", "scene_id"],
            ["free_course_scenes.user_id", "free_course_scenes.course_id", "free_course_scenes.id"],
            name="fk_fc_link_scene",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index(
            "uq_fc_link_course_node",
            "user_id",
            "course_version_id",
            "node_id",
            unique=True,
            postgresql_where="scene_id IS NULL",
        ),
        Index(
            "uq_fc_link_scene_node",
            "user_id",
            "course_version_id",
            "scene_id",
            "node_id",
            unique=True,
            postgresql_where="scene_id IS NOT NULL",
        ),
        CheckConstraint(
            "(graph_version = 'mvp-0.2.0' AND node_id IN ('array', 'c-pointer', 'circular- "
            "queue', 'linked-list-concept', 'linked-list-deletion', 'linked-list- "
            "insertion', 'linked-list-traversal', 'queue', 'single-linked-list', 'stack')) "
            "OR (graph_version = 'phase-1.1.0' AND node_id IN ('array', 'array-stack', "
            "'balanced-binary-search-tree', 'binary-heap', 'binary-search-tree', 'binary- "
            "tree', 'binary-tree-traversal', 'breadth-first-search', 'bubble-sort', "
            "'c-pointer', 'circular-linked-list', 'circular-queue', 'depth-first-search', "
            "'doubly-linked-list', 'graph-representation', 'heap-sort', 'insertion-sort', "
            "'linked-list-concept', 'linked-list-deletion', 'linked-list-insertion', "
            "'linked-list-traversal', 'linked-stack', 'merge-sort', 'queue', 'quick-sort', "
            "'selection-sort', 'single-linked-list', 'sorting-comparison', 'stack', 'tree- "
            "concept'))",
            name="ck_fc_link_known_node",
        ),
        CheckConstraint("relation IN ('target','supporting')", name="ck_fc_link_relation"),
        CheckConstraint(
            "source IN ('user_selected','planner_suggestion')", name="ck_fc_link_source"
        ),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    course_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    course_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scene_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(64), nullable=False)
    relation: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_refs: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
