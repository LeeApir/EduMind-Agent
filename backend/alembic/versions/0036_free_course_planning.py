"""Append-only planning outcomes and clarification projection on durable operations."""

from alembic import op

revision = "0036_free_course_planning"
down_revision = "0035_free_course_repository"
branch_labels = None
depends_on = None

TABLE_DDL = """
CREATE TABLE free_course_planning_results (
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
	plan_id UUID,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT ck_fc_planning_epoch CHECK (lease_epoch >= 1 AND (expected_head IS NULL OR
expected_head>0)),
        CONSTRAINT ck_fc_planning_digests CHECK (input_digest ~ '^[0-9a-f]{64}$' AND
request_digest ~ '^[0-9a-f]{64}$' AND response_digest ~ '^[0-9a-f]{64}$'),
	CONSTRAINT uq_fc_planning_call UNIQUE (user_id, course_id, operation_id, call_key),
        CONSTRAINT fk_fc_planning_operation FOREIGN KEY(user_id, course_id, operation_id)
REFERENCES free_course_operations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT fk_fc_planning_request FOREIGN KEY(user_id, course_id, request_id)
REFERENCES free_course_requests (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_fc_planning_plan FOREIGN KEY(user_id, course_id, plan_id) REFERENCES
free_course_plans (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT ck_fc_planning_state CHECK (state IN ('ready','needs_clarification','failed')),
        CONSTRAINT ck_fc_planning_result CHECK ((state='ready' AND plan_id IS NOT NULL AND
reason_code IS NULL) OR (state='needs_clarification' AND plan_id IS NULL AND reason_code IS
NULL) OR (state='failed' AND plan_id IS NULL AND reason_code IS NOT NULL AND reason_code IN
('SCHEMA_INVALID','PROVIDER_REJECTED','OUTCOME_UNKNOWN')))
)
"""
OLD_GUARD = """
CREATE OR REPLACE FUNCTION fc_operation_protect() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN
        IF NOT EXISTS(SELECT 1 FROM users WHERE id=OLD.user_id) THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'operation audit cannot be deleted' USING ERRCODE='23514';
      END IF;
      IF (to_jsonb(NEW)-ARRAY['state','lease_epoch','lease_token','lease_expires_at',
           'cancel_requested_at']) IS DISTINCT FROM
         (to_jsonb(OLD)-ARRAY['state','lease_epoch','lease_token','lease_expires_at',
           'cancel_requested_at']) OR NEW.lease_epoch<OLD.lease_epoch THEN
        RAISE EXCEPTION 'immutable operation binding' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END; $$
"""
NEW_GUARD = """
CREATE OR REPLACE FUNCTION fc_operation_protect() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN
        IF NOT EXISTS(SELECT 1 FROM users WHERE id=OLD.user_id) THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'operation audit cannot be deleted' USING ERRCODE='23514';
      END IF;
      IF (to_jsonb(NEW)-ARRAY['state','lease_epoch','lease_token','lease_expires_at',
           'cancel_requested_at','reason_code','clarification_questions']) IS DISTINCT FROM
         (to_jsonb(OLD)-ARRAY['state','lease_epoch','lease_token','lease_expires_at',
           'cancel_requested_at','reason_code','clarification_questions'])
         OR NEW.lease_epoch<OLD.lease_epoch THEN
        RAISE EXCEPTION 'immutable operation binding' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END; $$
"""


def upgrade() -> None:
    op.execute(
        "ALTER TABLE free_course_operations ADD COLUMN reason_code varchar(64), "
        "ADD COLUMN clarification_questions jsonb NOT NULL DEFAULT '[]'::jsonb"
    )
    op.create_check_constraint(
        "ck_fc_operation_questions",
        "free_course_operations",
        "jsonb_typeof(clarification_questions)='array' AND "
        "jsonb_array_length(clarification_questions)<=3",
    )
    op.execute(NEW_GUARD)
    op.execute(TABLE_DDL)
    op.execute(
        "CREATE TRIGGER fc_planning_immutable BEFORE UPDATE OR DELETE ON "
        "free_course_planning_results FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM free_course_planning_results)
      OR EXISTS(SELECT 1 FROM free_course_operations WHERE reason_code IS NOT NULL
        OR clarification_questions<>'[]'::jsonb) THEN
        RAISE EXCEPTION 'free course data prevents downgrade';
      END IF;
    END $$""")
    op.drop_table("free_course_planning_results")
    op.execute(OLD_GUARD)
    op.drop_constraint("ck_fc_operation_questions", "free_course_operations", type_="check")
    op.execute(
        "ALTER TABLE free_course_operations DROP COLUMN reason_code, "
        "DROP COLUMN clarification_questions"
    )
