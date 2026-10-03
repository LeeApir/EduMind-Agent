"""Persist reviewed animation jobs, local event cursors and owner media bindings."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010_animation_jobs"
down_revision = "0009_path_commands"
branch_labels = None
depends_on = None


def _uuid(name: str, *, nullable: bool = False, primary_key: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable,
                     primary_key=primary_key)


def upgrade() -> None:
    op.create_unique_constraint("uq_learning_units_owner_id", "learning_units", ["user_id", "id"])
    op.create_unique_constraint(
        "uq_learning_scenes_unit_id_version", "learning_scenes",
        ["learning_unit_id", "id", "version"],
    )
    op.create_table(
        "animation_media",
        _uuid("id", primary_key=True),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(40), nullable=False),
        sa.Column("review_rule_version", sa.String(64), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("image_digest", sa.String(71), nullable=False),
        sa.Column("font_digest", sa.String(64), nullable=False),
        sa.Column("renderer_config_sha256", sa.String(64), nullable=False),
        sa.Column("subtitle_version", sa.String(40), nullable=False),
        sa.Column("mp4_sha256", sa.String(64), nullable=False),
        sa.Column("srt_sha256", sa.String(64), nullable=False),
        sa.Column("mp4_size", sa.Integer(), nullable=False),
        sa.Column("srt_size", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False,
                  server_default="passed"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("cache_key", name="uq_animation_media_cache_key"),
        sa.CheckConstraint("review_status = 'passed'", name="ck_animation_media_review_passed"),
        sa.CheckConstraint("duration_seconds BETWEEN 30 AND 90",
                           name="ck_animation_media_duration"),
        sa.CheckConstraint("mp4_size > 0 AND mp4_size <= 67108864",
                           name="ck_animation_media_mp4_size"),
        sa.CheckConstraint("srt_size > 0 AND srt_size <= 67108864",
                           name="ck_animation_media_srt_size"),
    )
    op.create_table(
        "animation_jobs",
        _uuid("id", primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        _uuid("learning_unit_id"),
        _uuid("scene_id"),
        sa.Column("scene_version", sa.Integer(), nullable=False),
        sa.Column("action_kind", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("parameters_digest", sa.String(64), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(40), nullable=False),
        sa.Column("review_rule_version", sa.String(64), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("image_digest", sa.String(71), nullable=False),
        sa.Column("font_digest", sa.String(64), nullable=False),
        sa.Column("renderer_config_sha256", sa.String(64), nullable=False),
        sa.Column("subtitle_version", sa.String(40), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_event_id", sa.Integer(), nullable=False, server_default="0"),
        _uuid("lease_token", nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        _uuid("retry_of", nullable=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("animation_media.id")),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "action_kind", "idempotency_key",
                            name="uq_animation_job_owner_action_key"),
        sa.UniqueConstraint("user_id", "id", name="uq_animation_job_owner_id"),
        sa.UniqueConstraint("user_id", "id", "media_id",
                            name="uq_animation_job_owner_id_media"),
        sa.UniqueConstraint(
            "user_id", "learning_unit_id", "scene_id", "scene_version", "id",
            name="uq_animation_job_owner_target_id",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id"], ["learning_units.user_id", "learning_units.id"],
            name="fk_animation_job_unit_owner",
        ),
        sa.ForeignKeyConstraint(
            ["learning_unit_id", "scene_id", "scene_version"],
            ["learning_scenes.learning_unit_id", "learning_scenes.id", "learning_scenes.version"],
            name="fk_animation_job_scene_version",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "retry_of"], ["animation_jobs.user_id", "animation_jobs.id"],
            name="fk_animation_job_retry_owner",
        ),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')",
                           name="ck_animation_job_status"),
        sa.CheckConstraint("action_kind IN ('request','retry')", name="ck_animation_job_action"),
        sa.CheckConstraint("attempt BETWEEN 0 AND 2", name="ck_animation_job_attempt"),
        sa.CheckConstraint("progress BETWEEN 0 AND 1", name="ck_animation_job_progress"),
        sa.CheckConstraint("last_event_id >= 0", name="ck_animation_job_event_watermark"),
        sa.CheckConstraint("scene_version >= 1", name="ck_animation_job_scene_version"),
        sa.CheckConstraint("status != 'running' OR (lease_token IS NOT NULL AND "
                           "lease_expires_at IS NOT NULL AND attempt >= 1)",
                           name="ck_animation_job_running_lease"),
        sa.CheckConstraint("status != 'succeeded' OR media_id IS NOT NULL",
                           name="ck_animation_job_succeeded_media"),
    )
    op.create_index("ix_animation_jobs_claim", "animation_jobs",
                    ["status", "created_at"])
    op.create_index("ix_animation_jobs_lease", "animation_jobs",
                    ["status", "lease_expires_at"])
    op.create_table(
        "animation_job_events",
        _uuid("job_id", primary_key=True),
        sa.Column("event_id", sa.Integer(), primary_key=True),
        _uuid("user_id"),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id", "job_id"], ["animation_jobs.user_id", "animation_jobs.id"],
            ondelete="CASCADE", name="fk_animation_job_event_owner",
        ),
        sa.CheckConstraint("event_id >= 1", name="ck_animation_job_event_id_positive"),
        sa.CheckConstraint(
            "event_type IN ('queued','running','progress','succeeded','failed','cancelled',"
            "'recovered')", name="ck_animation_job_event_type",
        ),
    )
    op.create_table(
        "animation_resource_bindings",
        _uuid("id", primary_key=True),
        _uuid("user_id"),
        _uuid("job_id"),
        _uuid("media_id"),
        _uuid("learning_unit_id"),
        _uuid("scene_id"),
        sa.Column("scene_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "job_id", name="uq_animation_binding_owner_job"),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "scene_id", "scene_version", "job_id"],
            ["animation_jobs.user_id", "animation_jobs.learning_unit_id",
             "animation_jobs.scene_id", "animation_jobs.scene_version", "animation_jobs.id"],
            ondelete="CASCADE", name="fk_animation_binding_job_target_owner",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "job_id", "media_id"],
            ["animation_jobs.user_id", "animation_jobs.id", "animation_jobs.media_id"],
            name="fk_animation_binding_job_media_owner",
        ),
        sa.CheckConstraint("scene_version >= 1", name="ck_animation_binding_scene_version"),
    )


def downgrade() -> None:
    op.drop_table("animation_resource_bindings")
    op.drop_table("animation_job_events")
    op.drop_index("ix_animation_jobs_lease", table_name="animation_jobs")
    op.drop_index("ix_animation_jobs_claim", table_name="animation_jobs")
    op.drop_table("animation_jobs")
    op.drop_table("animation_media")
    op.drop_constraint("uq_learning_scenes_unit_id_version", "learning_scenes", type_="unique")
    op.drop_constraint("uq_learning_units_owner_id", "learning_units", type_="unique")
