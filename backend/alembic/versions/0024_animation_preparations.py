"""API preparation receipts with immutable session/deadline identity (ADR-0010)."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0024_animation_preparations"
down_revision = "0023_animation_dsl_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "animation_preparations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("learning_unit_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("scene_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("scene_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("intent", pg.JSONB(), nullable=False),
        sa.Column("reference_sha256", sa.String(64), nullable=False),
        sa.Column("originating_session_hash", sa.String(64), nullable=False),
        sa.Column("originating_session_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execution_token", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("allow_template_fallback", sa.Boolean(), nullable=False),
        sa.Column("generation_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("job_id", pg.UUID(as_uuid=True)),
        sa.Column("source_kind", sa.String(32)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("cancel_idempotency_key", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_animation_preparation_owner_key"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id"],
            ["learning_units.user_id", "learning_units.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["learning_unit_id", "scene_id", "scene_version"],
            ["learning_scenes.learning_unit_id", "learning_scenes.id", "learning_scenes.version"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "learning_unit_id", "scene_id", "scene_version", "job_id"],
            [
                "animation_jobs.user_id",
                "animation_jobs.learning_unit_id",
                "animation_jobs.scene_id",
                "animation_jobs.scene_version",
                "animation_jobs.id",
            ],
            name="fk_animation_preparation_job_target",
        ),
        sa.CheckConstraint(
            "generation_attempts BETWEEN 0 AND 3 AND "
            "review_attempts BETWEEN 0 AND generation_attempts",
            name="ck_animation_preparation_attempts",
        ),
        sa.CheckConstraint("scene_version >= 1", name="ck_animation_preparation_version"),
        sa.CheckConstraint(
            "stage IN ('reserved','generating','reviewing','compiled',"
            "'handed_off','failed','cancelled')",
            name="ck_animation_preparation_stage",
        ),
        sa.CheckConstraint(
            "stage != 'handed_off' OR job_id IS NOT NULL", name="ck_animation_preparation_handoff"
        ),
        sa.CheckConstraint(
            "deadline > created_at AND deadline <= created_at + interval '180 seconds' "
            "AND deadline <= originating_session_expires_at",
            name="ck_animation_preparation_deadline",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^[0-9a-f]{64}$' AND reference_sha256 ~ '^[0-9a-f]{64}$' "
            "AND originating_session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_animation_preparation_hashes",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(intent)='object' AND octet_length(intent::text)<=2048",
            name="ck_animation_preparation_intent",
        ),
        sa.CheckConstraint(
            "source_kind IS NULL OR source_kind IN ('reviewed_cache','parameterized_template',"
            "'generated_dsl','reviewed_dsl_cache','template_fallback','unavailable')",
            name="ck_animation_preparation_source",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code ~ '^[A-Z0-9_]{1,64}$'",
            name="ck_animation_preparation_error",
        ),
    )
    op.execute("""CREATE FUNCTION edumind_preparation_immutable() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN
        IF (to_jsonb(NEW) - ARRAY['stage','job_id','source_kind','error_code',
                'cancel_idempotency_key','generation_attempts','review_attempts'])
           IS DISTINCT FROM
           (to_jsonb(OLD) - ARRAY['stage','job_id','source_kind','error_code',
                'cancel_idempotency_key','generation_attempts','review_attempts'])
        THEN RAISE EXCEPTION 'preparation identity is immutable'; END IF;
        IF OLD.stage IN ('handed_off','failed','cancelled') AND NEW IS DISTINCT FROM OLD
        THEN RAISE EXCEPTION 'preparation outcome is immutable'; END IF;
        IF NEW.generation_attempts < OLD.generation_attempts OR
           NEW.review_attempts < OLD.review_attempts OR
           NEW.generation_attempts > OLD.generation_attempts + 1 OR
           NEW.review_attempts > OLD.review_attempts + 1
        THEN RAISE EXCEPTION 'preparation attempts must advance one at a time'; END IF;
        IF OLD.stage='compiled' AND NEW.stage NOT IN ('compiled','handed_off','failed','cancelled')
        THEN RAISE EXCEPTION 'compiled preparation cannot send again'; END IF;
        IF NEW.stage='reserved' AND OLD.stage != 'reserved'
        THEN RAISE EXCEPTION 'preparation cannot return to reservation'; END IF;
        IF OLD.stage='reviewing' AND NEW.stage='generating' AND
           (NEW.generation_attempts != OLD.generation_attempts + 1 OR
            OLD.generation_attempts != OLD.review_attempts)
        THEN RAISE EXCEPTION 'correction must follow independent review'; END IF;
        RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER animation_preparation_immutable BEFORE UPDATE ON
        animation_preparations FOR EACH ROW EXECUTE FUNCTION edumind_preparation_immutable()""")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM animation_preparations)
        THEN RAISE EXCEPTION 'Cannot downgrade preparation receipts with retained data';
        END IF; END $$""")
    op.drop_table("animation_preparations")
    op.execute("DROP FUNCTION edumind_preparation_immutable()")
