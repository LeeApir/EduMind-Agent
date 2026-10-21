"""Explicit private DSL media/job provenance; preserve every legacy template row."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0025_animation_dsl_media"
down_revision = "0024_animation_preparations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("animation_jobs", "animation_media"):
        op.add_column(
            table,
            sa.Column("render_kind", sa.String(16), nullable=False, server_default="template"),
        )
        op.add_column(table, sa.Column("candidate_id", pg.UUID(as_uuid=True)))
        op.alter_column(table, "template_id", existing_type=sa.String(64), nullable=True)
        op.alter_column(table, "template_version", existing_type=sa.String(40), nullable=True)
    op.add_column(
        "animation_media",
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_animation_media_dsl_user"),
        ),
    )
    op.add_column(
        "animation_media",
        sa.Column(
            "source_versions", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.add_column("animation_jobs", sa.Column("generation_id", pg.UUID(as_uuid=True)))
    op.add_column("animation_jobs", sa.Column("fallback_of", pg.UUID(as_uuid=True)))
    op.add_column("animation_jobs", sa.Column("fallback_reason_code", sa.String(64)))
    op.create_unique_constraint(
        "uq_animation_preparation_owner_target",
        "animation_preparations",
        ["user_id", "learning_unit_id", "scene_id", "scene_version", "id"],
    )
    op.create_foreign_key(
        "fk_animation_job_generation_target",
        "animation_jobs",
        "animation_preparations",
        ["user_id", "learning_unit_id", "scene_id", "scene_version", "generation_id"],
        ["user_id", "learning_unit_id", "scene_id", "scene_version", "id"],
    )
    op.create_unique_constraint(
        "uq_animation_media_dsl_owner", "animation_media", ["id", "user_id", "candidate_id"]
    )
    op.create_foreign_key(
        "fk_animation_media_dsl_owner",
        "animation_media",
        "animation_dsl_candidates",
        ["user_id", "candidate_id"],
        ["user_id", "id"],
    )
    op.create_foreign_key(
        "fk_animation_job_dsl_target",
        "animation_jobs",
        "animation_dsl_candidates",
        ["user_id", "learning_unit_id", "scene_id", "scene_version", "candidate_id"],
        ["user_id", "learning_unit_id", "scene_id", "scene_version", "id"],
    )
    op.create_foreign_key(
        "fk_animation_job_dsl_media",
        "animation_jobs",
        "animation_media",
        ["media_id", "user_id", "candidate_id"],
        ["id", "user_id", "candidate_id"],
    )
    op.create_foreign_key(
        "fk_animation_job_fallback_owner",
        "animation_jobs",
        "animation_jobs",
        ["user_id", "fallback_of"],
        ["user_id", "id"],
    )
    op.create_unique_constraint(
        "uq_animation_job_fallback_kind", "animation_jobs", ["fallback_of", "render_kind"]
    )
    op.create_check_constraint(
        "ck_animation_job_render_kind",
        "animation_jobs",
        "(render_kind='template' AND template_id IS NOT NULL AND template_version IS NOT NULL "
        "AND candidate_id IS NULL) OR (render_kind='dsl' AND template_id IS NULL "
        "AND template_version IS NULL AND candidate_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_animation_media_render_kind",
        "animation_media",
        "(render_kind='template' AND template_id IS NOT NULL AND template_version IS NOT NULL "
        "AND user_id IS NULL AND candidate_id IS NULL) OR "
        "(render_kind='dsl' AND template_id IS NULL AND template_version IS NULL "
        "AND user_id IS NOT NULL AND candidate_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_animation_job_fallback",
        "animation_jobs",
        "fallback_of IS NULL OR (render_kind='template' AND generation_id IS NOT NULL "
        "AND fallback_reason_code='DSL_RENDER_FAILED' AND retry_of IS NULL)",
    )
    op.create_check_constraint(
        "ck_animation_media_source_versions",
        "animation_media",
        "jsonb_typeof(source_versions)='object' AND octet_length(source_versions::text)<=8192",
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS (
        SELECT 1 FROM animation_jobs WHERE render_kind='dsl' OR generation_id IS NOT NULL
        OR fallback_of IS NOT NULL UNION ALL
        SELECT 1 FROM animation_media WHERE render_kind='dsl')
        THEN RAISE EXCEPTION 'Cannot downgrade retained DSL job/media provenance';
        END IF; END $$""")
    for table, constraints in (
        (
            "animation_jobs",
            [
                ("ck_animation_job_fallback", "check"),
                ("ck_animation_job_render_kind", "check"),
                ("uq_animation_job_fallback_kind", "unique"),
                ("fk_animation_job_fallback_owner", "foreignkey"),
                ("fk_animation_job_dsl_media", "foreignkey"),
                ("fk_animation_job_dsl_target", "foreignkey"),
            ],
        ),
        (
            "animation_media",
            [
                ("ck_animation_media_source_versions", "check"),
                ("ck_animation_media_render_kind", "check"),
                ("fk_animation_media_dsl_owner", "foreignkey"),
                ("fk_animation_media_dsl_user", "foreignkey"),
                ("uq_animation_media_dsl_owner", "unique"),
            ],
        ),
    ):
        for name, kind in constraints:
            op.drop_constraint(name, table, type_=kind)
    op.drop_constraint("fk_animation_job_generation_target", "animation_jobs", type_="foreignkey")
    op.drop_constraint(
        "uq_animation_preparation_owner_target", "animation_preparations", type_="unique"
    )
    for column in ("generation_id", "fallback_of", "fallback_reason_code"):
        op.drop_column("animation_jobs", column)
    for column in ("source_versions", "user_id"):
        op.drop_column("animation_media", column)
    for table in ("animation_jobs", "animation_media"):
        op.drop_column(table, "candidate_id")
        op.drop_column(table, "render_kind")
        op.alter_column(table, "template_id", existing_type=sa.String(64), nullable=False)
        op.alter_column(table, "template_version", existing_type=sa.String(40), nullable=False)
