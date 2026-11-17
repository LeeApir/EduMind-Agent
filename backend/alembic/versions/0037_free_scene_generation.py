"""Retain private scene candidates and failed bounded responses, never publish them."""

from alembic import op

revision = "0037_free_scene_generation"
down_revision = "0036_free_course_planning"
branch_labels = None
depends_on = None

TABLE_DDL = """

CREATE TABLE free_course_scene_generation_results (
        course_id UUID NOT NULL,
        operation_id UUID NOT NULL,
        request_id UUID NOT NULL,
        lease_epoch INTEGER NOT NULL,
        call_key VARCHAR(128) NOT NULL,
        expected_head INTEGER,
        input_digest VARCHAR(64) NOT NULL,
        request_digest VARCHAR(64) NOT NULL,
        response_digest VARCHAR(64) NOT NULL,
        prompt_version VARCHAR(64) NOT NULL,
        schema_version VARCHAR(64) NOT NULL,
        state VARCHAR(32) NOT NULL,
        reason_code VARCHAR(64),
        input_snapshot JSONB NOT NULL,
        response_json JSONB,
        plan_id UUID NOT NULL,
        scene_id UUID NOT NULL,
        sent_attempts INTEGER NOT NULL,
        usage_json JSONB,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_fc_scene_gen_epoch CHECK (lease_epoch >= 1 AND (expected_head IS NULL OR
expected_head>0)),
        CONSTRAINT ck_fc_scene_gen_digests CHECK (input_digest ~ '^[0-9a-f]{64}$' AND
request_digest ~ '^[0-9a-f]{64}$' AND response_digest ~ '^[0-9a-f]{64}$'),
        CONSTRAINT uq_fc_scene_gen_call UNIQUE (user_id, course_id, operation_id, scene_id,
call_key),
        CONSTRAINT fk_fc_scene_gen_operation FOREIGN KEY(user_id, course_id, operation_id)
REFERENCES free_course_operations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY
DEFERRED,
        CONSTRAINT fk_fc_scene_gen_request FOREIGN KEY(user_id, course_id, request_id) REFERENCES
free_course_requests (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_fc_scene_gen_plan FOREIGN KEY(user_id, course_id, plan_id) REFERENCES
free_course_plans (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_fc_scene_gen_scene FOREIGN KEY(user_id, course_id, scene_id) REFERENCES
free_course_scenes (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT ck_fc_scene_gen_sent CHECK (sent_attempts=1),
        CONSTRAINT ck_fc_scene_gen_state CHECK (state IN ('candidate','failed')),
        CONSTRAINT ck_fc_scene_gen_result CHECK ((state='candidate' AND reason_code IS NULL) OR
(state='failed' AND reason_code IS NOT NULL AND reason_code IN
('SCHEMA_INVALID','PROVIDER_REJECTED','OUTCOME_UNKNOWN')))
)

"""


def upgrade() -> None:
    op.execute(TABLE_DDL)
    op.execute(
        "CREATE TRIGGER fc_scene_gen_immutable BEFORE UPDATE OR DELETE ON "
        "free_course_scene_generation_results FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM free_course_scene_generation_results) THEN
        RAISE EXCEPTION 'free course data prevents downgrade';
      END IF;
    END $$""")
    op.drop_table("free_course_scene_generation_results")
