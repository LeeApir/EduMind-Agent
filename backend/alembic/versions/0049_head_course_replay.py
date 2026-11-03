"""Explicit zero-call existing candidate replay origin (ADR0051)."""

import sqlalchemy as sa

from alembic import op

revision = "0049_head_course_replay"
down_revision = "0048_free_course_tutor_events"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "free_course_scene_generation_results",
        sa.Column("origin_type", sa.String(40), nullable=False, server_default="model_generation"),
    )
    op.drop_constraint(
        "ck_fc_scene_gen_sent", "free_course_scene_generation_results", type_="check"
    )
    op.create_check_constraint(
        "ck_fc_scene_gen_sent",
        "free_course_scene_generation_results",
        "(origin_type='model_generation' AND sent_attempts=1) OR "
        "(origin_type='existing_real_candidate_replay' AND sent_attempts=0 AND usage_json IS NULL)",
    )


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM free_course_scene_generation_results "
        "WHERE origin_type<>'model_generation') THEN RAISE EXCEPTION "
        "'Replay audit exists; retain origin'; END IF; END $$"
    )
    op.drop_constraint(
        "ck_fc_scene_gen_sent", "free_course_scene_generation_results", type_="check"
    )
    op.create_check_constraint(
        "ck_fc_scene_gen_sent", "free_course_scene_generation_results", "sent_attempts=1"
    )
    op.drop_column("free_course_scene_generation_results", "origin_type")
