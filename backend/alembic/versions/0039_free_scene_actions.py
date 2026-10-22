"""Persist source-bound non-executable presentations and static fallback diagnostics."""

from alembic import op

revision = "0039_free_scene_actions"
down_revision = "0038_free_scene_validation"
branch_labels = None
depends_on = None

TABLE_DDL = """
CREATE TABLE free_course_scene_presentations (
        course_id UUID NOT NULL,
        validation_id UUID NOT NULL,
        rule_version VARCHAR(64) NOT NULL,
        fallback_key VARCHAR(64) NOT NULL,
        presentation_json JSONB NOT NULL,
        presentation_digest VARCHAR(64) NOT NULL,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_fc_presentation_validation FOREIGN KEY(user_id, course_id, validation_id)
REFERENCES free_course_scene_validations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT uq_fc_presentation_version UNIQUE (user_id, course_id, validation_id,
rule_version, fallback_key),
        CONSTRAINT ck_fc_presentation_digest CHECK (presentation_digest ~ '^[0-9a-f]{64}$'),
        CONSTRAINT ck_fc_presentation_fallback CHECK (fallback_key IN
('none','MEDIA_UNAVAILABLE','RENDERER_UNAVAILABLE','ACTION_UNAVAILABLE')),
        CONSTRAINT ck_fc_presentation_payload CHECK (jsonb_typeof(presentation_json)='object')
)

"""


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_fc_validation_identity", "free_course_scene_validations", ["user_id", "course_id", "id"]
    )
    op.execute(TABLE_DDL)
    op.execute(
        "CREATE TRIGGER fc_presentation_immutable BEFORE UPDATE OR DELETE ON "
        "free_course_scene_presentations FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM free_course_scene_presentations) THEN
        RAISE EXCEPTION 'free course data prevents downgrade';
      END IF;
    END $$""")
    op.drop_table("free_course_scene_presentations")
    op.drop_constraint("uq_fc_validation_identity", "free_course_scene_validations", type_="unique")
