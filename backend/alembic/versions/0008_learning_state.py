"""Create owner-scoped learning evidence, mastery, and path state.

Revision ID: 0008_learning_state
Revises: 0007_profile_provenance
Create Date: 2026-09-25
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_learning_state"
down_revision = "0007_profile_provenance"
branch_labels = None
depends_on = None


def _owner_column(*, primary_key: bool = False) -> sa.Column:
    return sa.Column(
        "user_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=primary_key,
    )


def upgrade() -> None:
    op.create_table(
        "learning_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _owner_column(),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("knowledge_node_id", sa.String(64), nullable=False),
        sa.Column(
            "learning_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning_units.id")
        ),
        sa.Column("scene_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learning_scenes.id")),
        sa.Column(
            "resource_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("generated_resources.id")
        ),
        sa.Column("resource_version", sa.Integer()),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "corrects_evidence_id",
            postgresql.UUID(as_uuid=True),
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_learning_evidence_user_key"),
        sa.UniqueConstraint("user_id", "id", name="uq_learning_evidence_user_id"),
        sa.ForeignKeyConstraint(
            ["user_id", "corrects_evidence_id"],
            ["learning_evidence.user_id", "learning_evidence.id"],
            name="fk_learning_evidence_corrects_owner",
        ),
        sa.CheckConstraint("schema_version >= 1", name="ck_learning_evidence_schema_positive"),
        sa.CheckConstraint(
            "resource_version IS NULL OR resource_version >= 1",
            name="ck_learning_evidence_resource_version_positive",
        ),
        sa.CheckConstraint(
            "evidence_type IN ('quiz_attempt', 'hint_used', 'reexplanation_requested', "
            "'resource_selected', 'explicit_feedback')",
            name="ck_learning_evidence_type",
        ),
    )
    op.create_index(
        "ix_learning_evidence_owner_node_time",
        "learning_evidence",
        ["user_id", "knowledge_node_id", "created_at"],
    )

    op.create_table(
        "node_mastery_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _owner_column(),
        sa.Column("knowledge_node_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_score", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column(
            "evidence_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "recomputed_from_id",
            postgresql.UUID(as_uuid=True),
        ),
        sa.Column("evidence_summary", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "user_id", "knowledge_node_id", "revision", name="uq_node_mastery_owner_node_revision"
        ),
        sa.UniqueConstraint(
            "user_id", "knowledge_node_id", "id", name="uq_node_mastery_owner_node_id"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "evidence_id"],
            ["learning_evidence.user_id", "learning_evidence.id"],
            name="fk_node_mastery_evidence_owner",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "knowledge_node_id", "recomputed_from_id"],
            [
                "node_mastery_revisions.user_id",
                "node_mastery_revisions.knowledge_node_id",
                "node_mastery_revisions.id",
            ],
            name="fk_node_mastery_recomputed_owner_node",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_node_mastery_revision_positive"),
        sa.CheckConstraint(
            "previous_score BETWEEN 0 AND 1", name="ck_node_mastery_previous_score_range"
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="ck_node_mastery_revision_score_range"),
        sa.CheckConstraint(
            "status IN ('unseen', 'learning', 'weak', 'mastered')",
            name="ck_node_mastery_revision_status",
        ),
    )

    op.create_table(
        "node_mastery_current",
        _owner_column(primary_key=True),
        sa.Column("knowledge_node_id", sa.String(64), primary_key=True),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "knowledge_node_id", "revision_id"],
            [
                "node_mastery_revisions.user_id",
                "node_mastery_revisions.knowledge_node_id",
                "node_mastery_revisions.id",
            ],
            name="fk_node_mastery_current_owner_node_revision",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_node_mastery_current_revision_positive"),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="ck_node_mastery_current_score_range"),
        sa.CheckConstraint(
            "status IN ('unseen', 'learning', 'weak', 'mastered')",
            name="ck_node_mastery_current_status",
        ),
    )

    op.create_table(
        "learning_path_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _owner_column(),
        sa.Column("target_node_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("graph_version", sa.String(64), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("mastery_revision_watermark", sa.Integer(), nullable=False),
        sa.Column("planner_rule_version", sa.String(64), nullable=False),
        sa.Column("nodes", postgresql.JSONB(), nullable=False),
        sa.Column("current_node_id", sa.String(64)),
        sa.Column("prerequisite_node_ids", postgresql.JSONB(), nullable=False),
        sa.Column("next_node_id", sa.String(64)),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column(
            "previous_path_id",
            postgresql.UUID(as_uuid=True),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "user_id", "target_node_id", "version", name="uq_learning_path_owner_target_version"
        ),
        sa.UniqueConstraint(
            "user_id", "target_node_id", "id", name="uq_learning_path_owner_target_id"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "target_node_id", "previous_path_id"],
            [
                "learning_path_versions.user_id",
                "learning_path_versions.target_node_id",
                "learning_path_versions.id",
            ],
            name="fk_learning_path_previous_owner_target",
        ),
        sa.CheckConstraint("version >= 1", name="ck_learning_path_version_positive"),
        sa.CheckConstraint(
            "profile_version >= 1", name="ck_learning_path_profile_version_positive"
        ),
        sa.CheckConstraint(
            "mastery_revision_watermark >= 0", name="ck_learning_path_watermark_nonnegative"
        ),
    )

    op.create_table(
        "learning_path_current",
        _owner_column(primary_key=True),
        sa.Column("target_node_id", sa.String(64), primary_key=True),
        sa.Column(
            "path_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("replan_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "target_node_id", "path_version_id"],
            [
                "learning_path_versions.user_id",
                "learning_path_versions.target_node_id",
                "learning_path_versions.id",
            ],
            name="fk_learning_path_current_owner_target_version",
        ),
    )


def downgrade() -> None:
    op.drop_table("learning_path_current")
    op.drop_table("learning_path_versions")
    op.drop_table("node_mastery_current")
    op.drop_table("node_mastery_revisions")
    op.drop_index("ix_learning_evidence_owner_node_time", table_name="learning_evidence")
    op.drop_table("learning_evidence")
