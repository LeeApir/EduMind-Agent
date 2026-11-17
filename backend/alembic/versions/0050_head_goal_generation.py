"""Distinct finite head-goal model origin; retain all existing frozen/replay audits."""

from alembic import op

revision = "0050_head_goal_generation"
down_revision = "0049_head_course_replay"
branch_labels = None
depends_on = None

OLD = (
    "(origin_type='model_generation' AND sent_attempts=1) OR "
    "(origin_type='existing_real_candidate_replay' AND "
    "sent_attempts=0 AND usage_json IS NULL)"
)
NEW = (
    "(origin_type IN ('model_generation','head_goal_model_generat"
    "ion') AND sent_attempts=1) OR "
    "(origin_type='existing_real_candidate_replay' AND "
    "sent_attempts=0 AND usage_json IS NULL)"
)


def constraint(value):
    op.drop_constraint(
        "ck_fc_scene_gen_sent", "free_course_scene_generation_results", type_="check"
    )
    op.create_check_constraint(
        "ck_fc_scene_gen_sent", "free_course_scene_generation_results", value
    )


def upgrade():
    constraint(NEW)


def downgrade():
    op.execute(
        (
            "DO $$ BEGIN IF EXISTS(SELECT 1 FROM "
            "free_course_scene_generation_results WHERE "
            "origin_type='head_goal_model_generation') THEN RAISE EXCEPTION "
            "'New generation audit exists; retain origin'; END IF; END $$"
        )
    )
    constraint(OLD)
