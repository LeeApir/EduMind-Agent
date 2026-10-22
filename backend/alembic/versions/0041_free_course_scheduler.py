"""Durable conservative attempts and two-slot PG progressive scheduling."""

from alembic import op

revision = "0041_free_course_scheduler"
down_revision = "0040_free_scene_availability"
branch_labels = None
depends_on = None

TABLES = [
    """

CREATE TABLE free_course_attempts (
        course_id UUID NOT NULL,
        operation_id UUID NOT NULL,
        step_id UUID NOT NULL,
        purpose VARCHAR(32) NOT NULL,
        lease_epoch INTEGER NOT NULL,
        input_tokens INTEGER NOT NULL,
        output_tokens INTEGER NOT NULL,
        fee_micros INTEGER NOT NULL,
        sent_at TIMESTAMP WITH TIME ZONE NOT NULL,
        request_digest VARCHAR(64) NOT NULL,
        input_snapshot JSONB NOT NULL,
        request_json JSONB NOT NULL,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_fc_attempt_operation FOREIGN KEY(user_id, course_id, operation_id)
REFERENCES free_course_operations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT fk_fc_attempt_step FOREIGN KEY(user_id, course_id, step_id) REFERENCES
free_course_steps (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT uq_fc_attempt_identity UNIQUE (user_id, course_id, id),
        CONSTRAINT uq_fc_attempt_purpose UNIQUE (operation_id, step_id, purpose),
        CONSTRAINT ck_fc_attempt_purpose CHECK (purpose IN
('primary','transport_retry','format_repair')),
        CONSTRAINT ck_fc_attempt_tokens CHECK (input_tokens BETWEEN 1 AND 32000 AND
output_tokens BETWEEN 1 AND 8000),
        CONSTRAINT ck_fc_attempt_reservation CHECK (lease_epoch>0 AND fee_micros>=0)
)

""",
    """

CREATE TABLE free_course_settlements (
        course_id UUID NOT NULL,
        attempt_id UUID NOT NULL,
        evidence VARCHAR(32) NOT NULL,
        evidence_digest VARCHAR(64) NOT NULL,
        input_tokens INTEGER,
        output_tokens INTEGER,
        outcome_json JSONB NOT NULL,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_fc_settlement_attempt FOREIGN KEY(user_id, course_id, attempt_id)
REFERENCES free_course_attempts (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY
DEFERRED,
        CONSTRAINT uq_fc_settlement_attempt UNIQUE (attempt_id),
        CONSTRAINT ck_fc_settlement_evidence CHECK (evidence IN
('complete_response','not_executed','stopped')),
        CONSTRAINT ck_fc_settlement_tokens CHECK ((input_tokens IS NULL AND output_tokens IS
NULL) OR (input_tokens>=0 AND output_tokens>=0))
)

""",
    """

CREATE TABLE free_course_dispatches (
        course_id UUID NOT NULL,
        attempt_id UUID NOT NULL,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_fc_dispatch_attempt FOREIGN KEY(user_id, course_id, attempt_id) REFERENCES
free_course_attempts (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT uq_fc_dispatch_attempt UNIQUE (attempt_id)
)

""",
    """

CREATE TABLE free_course_capacity (
        slot SERIAL NOT NULL,
        user_id UUID,
        course_id UUID,
        operation_id UUID,
        state VARCHAR(32) NOT NULL,
        epoch INTEGER,
        expires_at TIMESTAMP WITH TIME ZONE,
        pending_attempt_id UUID,
        PRIMARY KEY (slot),
        CONSTRAINT ck_fc_capacity_slot CHECK (slot IN (1,2)),
        CONSTRAINT ck_fc_capacity_state CHECK (state IN ('free','held','quarantined')),
        CONSTRAINT ck_fc_capacity_binding CHECK ((state='free' AND operation_id IS NULL AND
user_id IS NULL AND course_id IS NULL AND pending_attempt_id IS NULL AND epoch IS NULL AND
expires_at IS NULL) OR (state<>'free' AND operation_id IS NOT NULL AND user_id IS NOT NULL AND
course_id IS NOT NULL AND epoch>0 AND expires_at IS NOT NULL)),
        CONSTRAINT uq_fc_capacity_operation UNIQUE (operation_id),
        CONSTRAINT fk_fc_capacity_operation FOREIGN KEY(user_id, course_id, operation_id)
REFERENCES free_course_operations (user_id, course_id, id)
)

""",
]

STEP_GUARD = """
CREATE OR REPLACE FUNCTION fc_step_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
   IF NOT EXISTS(SELECT 1 FROM users WHERE id=OLD.user_id) THEN RETURN OLD; END IF;
   RAISE EXCEPTION 'step audit cannot be deleted' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' AND
(to_jsonb(NEW)-ARRAY['state','reason_code','scene_version_id','presentation_id','next_attempt_at','retry_purpose'])
   IS DISTINCT FROM
(to_jsonb(OLD)-ARRAY['state','reason_code','scene_version_id','presentation_id','next_attempt_at','retry_purpose'])
THEN
   RAISE EXCEPTION 'immutable step binding' USING ERRCODE='23514';
 END IF;
 IF NEW.state='ready' AND NEW.scene_id IS NULL AND NOT EXISTS(
   SELECT 1 FROM free_course_planning_results p WHERE p.operation_id=NEW.operation_id
   AND p.user_id=NEW.user_id AND p.course_id=NEW.course_id AND p.state='ready'
   AND p.plan_id IS NOT NULL AND NEW.step_key='plan'
 ) THEN RAISE EXCEPTION 'ready plan requires actual completed planning'; END IF;
 IF NEW.state='ready' AND NEW.scene_id IS NOT NULL AND NOT EXISTS(
   SELECT 1 FROM free_course_scene_versions sv
   JOIN free_course_scene_presentations pr ON pr.id=NEW.presentation_id
     AND pr.user_id=NEW.user_id AND pr.course_id=NEW.course_id
   JOIN free_course_scene_validations va ON va.id=pr.validation_id AND va.state='accepted'
   JOIN free_course_scene_generation_results ge ON ge.id=va.generation_result_id
   JOIN free_courses c ON c.id=NEW.course_id AND c.user_id=NEW.user_id
   JOIN free_course_versions cv ON cv.id=c.head_version_id
   WHERE sv.id=NEW.scene_version_id AND sv.user_id=NEW.user_id
     AND sv.course_id=NEW.course_id AND sv.scene_id=NEW.scene_id AND sv.plan_id=NEW.plan_id
     AND sv.origin_operation_id=NEW.operation_id
     AND ge.operation_id=NEW.operation_id AND ge.scene_id=NEW.scene_id AND
ge.plan_id=NEW.plan_id
     AND cv.manifest_json->'scenes' @> jsonb_build_array(jsonb_build_object(
       'scene_id',NEW.scene_id::text,'scene_version_id',NEW.scene_version_id::text))
 ) THEN
   RAISE EXCEPTION 'ready step requires exact admitted head content' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
"""


def upgrade() -> None:
    op.alter_column("free_course_steps", "plan_id", nullable=True)
    op.alter_column("free_course_steps", "scene_id", nullable=True)
    op.execute(
        "ALTER TABLE free_course_steps ADD COLUMN next_attempt_at TIMESTAMPTZ, "
        "ADD COLUMN retry_purpose VARCHAR(32)"
    )
    op.create_unique_constraint(
        "uq_fc_step_identity", "free_course_steps", ["user_id", "course_id", "id"]
    )
    op.drop_constraint("ck_fc_step_ready", "free_course_steps", type_="check")
    op.create_check_constraint(
        "ck_fc_step_ready",
        "free_course_steps",
        "(state='ready' AND reason_code IS NULL AND ((scene_id IS NULL AND step_key='plan' "
        "AND scene_version_id IS NULL AND presentation_id IS NULL) OR (scene_id IS NOT NULL "
        "AND scene_version_id IS NOT NULL AND presentation_id IS NOT NULL))) OR state<>'ready'",
    )
    op.execute(STEP_GUARD)
    for ddl in TABLES:
        op.execute(ddl)
    for name in ("free_course_attempts", "free_course_settlements", "free_course_dispatches"):
        op.execute(
            f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
        )
    op.execute("INSERT INTO free_course_capacity(slot,state) VALUES (1,'free'),(2,'free')")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM free_course_attempts)
      OR EXISTS(SELECT 1 FROM free_course_steps WHERE scene_id IS NULL)
      OR EXISTS(SELECT 1 FROM free_course_capacity WHERE state<>'free') THEN
        RAISE EXCEPTION 'scheduler audit prevents downgrade';
      END IF;
    END $$""")
    op.drop_table("free_course_capacity")
    op.drop_table("free_course_dispatches")
    op.drop_table("free_course_settlements")
    op.drop_table("free_course_attempts")
    op.drop_constraint("ck_fc_step_ready", "free_course_steps", type_="check")
    op.create_check_constraint(
        "ck_fc_step_ready",
        "free_course_steps",
        "(state='ready' AND scene_version_id IS NOT NULL AND presentation_id IS NOT NULL "
        "AND reason_code IS NULL) OR state<>'ready'",
    )
    op.drop_constraint("uq_fc_step_identity", "free_course_steps", type_="unique")
    op.execute(
        "ALTER TABLE free_course_steps DROP COLUMN next_attempt_at, DROP COLUMN retry_purpose"
    )
    op.alter_column("free_course_steps", "plan_id", nullable=False)
    op.alter_column("free_course_steps", "scene_id", nullable=False)
    # jsonb subtraction tolerates absent fields; guard retains 0040 semantics after rollback.
