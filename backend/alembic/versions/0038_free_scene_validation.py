"""Add immutable deterministic scene checks; preserve candidates and legacy decisions."""

from alembic import op

revision = "0038_free_scene_validation"
down_revision = "0037_free_scene_generation"
branch_labels = None
depends_on = None

TABLE_DDL = """
CREATE TABLE free_course_scene_validations (
        course_id UUID NOT NULL,
        generation_result_id UUID NOT NULL,
        rule_version VARCHAR(64) NOT NULL,
        state VARCHAR(32) NOT NULL,
        reason_code VARCHAR(64),
        findings JSONB NOT NULL,
        raw_digest VARCHAR(64) NOT NULL,
        cleaned_digest VARCHAR(64),
        cleaned_json JSONB,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_fc_validation_candidate FOREIGN KEY(user_id, course_id,
generation_result_id) REFERENCES free_course_scene_generation_results (user_id, course_id, id) ON
DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT uq_fc_validation_rule UNIQUE (user_id, course_id, generation_result_id,
rule_version),
        CONSTRAINT ck_fc_validation_state CHECK (state IN ('accepted','rejected')),
        CONSTRAINT ck_fc_validation_raw CHECK (raw_digest ~ '^[0-9a-f]{64}$'),
        CONSTRAINT ck_fc_validation_result CHECK ((state='accepted' AND reason_code IS NULL AND
cleaned_digest IS NOT NULL AND cleaned_digest ~ '^[0-9a-f]{64}$' AND cleaned_json IS NOT NULL AND
jsonb_typeof(cleaned_json)='object') OR (state='rejected' AND reason_code IS NOT NULL AND
cleaned_digest IS NULL AND (cleaned_json IS NULL OR jsonb_typeof(cleaned_json)='null'))),
        CONSTRAINT ck_fc_validation_findings CHECK (jsonb_typeof(findings)='array')
)

"""


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_fc_scene_gen_identity",
        "free_course_scene_generation_results",
        ["user_id", "course_id", "id"],
    )
    op.execute(TABLE_DDL)
    op.execute(
        "CREATE TRIGGER fc_validation_immutable BEFORE UPDATE OR DELETE ON "
        "free_course_scene_validations FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM free_course_scene_validations) THEN
        RAISE EXCEPTION 'free course data prevents downgrade';
      END IF;
    END $$""")
    op.drop_table("free_course_scene_validations")
    op.drop_constraint(
        "uq_fc_scene_gen_identity", "free_course_scene_generation_results", type_="unique"
    )
