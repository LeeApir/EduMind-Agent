"""Incremental ready steps and public-safe append-only event identities."""

from alembic import op

revision = "0040_free_scene_availability"
down_revision = "0039_free_scene_actions"
branch_labels = None
depends_on = None

TABLES = [
    """
CREATE TABLE free_course_steps (
        course_id UUID NOT NULL,
        operation_id UUID NOT NULL,
        plan_id UUID NOT NULL,
        scene_id UUID NOT NULL,
        step_key VARCHAR(128) NOT NULL,
        state VARCHAR(32) NOT NULL,
        reason_code VARCHAR(64),
        scene_version_id UUID,
        presentation_id UUID,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_fc_step_operation FOREIGN KEY(user_id, course_id, operation_id) REFERENCES
free_course_operations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_fc_step_plan FOREIGN KEY(user_id, course_id, plan_id) REFERENCES
free_course_plans (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_fc_step_scene FOREIGN KEY(user_id, course_id, scene_id) REFERENCES
free_course_scenes (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_fc_step_version FOREIGN KEY(user_id, course_id, scene_version_id) REFERENCES
free_course_scene_versions (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT uq_fc_step_key UNIQUE (user_id, course_id, operation_id, step_key),
        CONSTRAINT uq_fc_step_scene UNIQUE (user_id, course_id, operation_id, scene_id),
        CONSTRAINT ck_fc_step_state CHECK (state IN
('pending','blocked_dependency','running','ready','failed','invalidated','cancelled')),
        CONSTRAINT ck_fc_step_ready CHECK ((state='ready' AND scene_version_id IS NOT NULL AND
presentation_id IS NOT NULL AND reason_code IS NULL) OR state<>'ready'),
        CONSTRAINT fk_fc_step_presentation FOREIGN KEY(user_id, course_id, presentation_id)
REFERENCES free_course_scene_presentations (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED
)

""",
    """
CREATE TABLE free_course_events (
        course_id UUID NOT NULL,
        operation_id UUID NOT NULL,
        seq INTEGER NOT NULL,
        event_type VARCHAR(32) NOT NULL,
        course_version_id UUID,
        payload JSONB NOT NULL,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_fc_event_operation FOREIGN KEY(user_id, course_id, operation_id) REFERENCES
free_course_operations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_fc_event_version FOREIGN KEY(user_id, course_id, course_version_id)
REFERENCES free_course_versions (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT uq_fc_event_seq UNIQUE (operation_id, seq),
        CONSTRAINT ck_fc_event_seq CHECK (seq BETWEEN 1 AND 256),
        CONSTRAINT ck_fc_event_type CHECK (event_type IN
('queued','started','clarification_required','outline_ready','scene_started','scene_ready','first_scene_ready','progress','cancel_requested','error','done')),
        CONSTRAINT ck_fc_event_payload CHECK (jsonb_typeof(payload)='object')
)

""",
]
INDEXES = [
    "CREATE UNIQUE INDEX uq_fc_event_first_scene ON free_course_events (course_id) "
    "WHERE event_type='first_scene_ready'"
]

GUARDS = """
CREATE FUNCTION fc_step_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
   IF NOT EXISTS(SELECT 1 FROM users WHERE id=OLD.user_id) THEN RETURN OLD; END IF;
   RAISE EXCEPTION 'step audit cannot be deleted' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' AND
   (to_jsonb(NEW)-ARRAY['state','reason_code','scene_version_id','presentation_id'])
   IS DISTINCT FROM
   (to_jsonb(OLD)-ARRAY['state','reason_code','scene_version_id','presentation_id']) THEN
   RAISE EXCEPTION 'immutable step binding' USING ERRCODE='23514';
 END IF;
 IF NEW.state='ready' AND NOT EXISTS(
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
     AND ge.operation_id=NEW.operation_id AND ge.scene_id=NEW.scene_id AND ge.plan_id=NEW.plan_id
     AND cv.manifest_json->'scenes' @> jsonb_build_array(jsonb_build_object(
       'scene_id',NEW.scene_id::text,'scene_version_id',NEW.scene_version_id::text))
 ) THEN
   RAISE EXCEPTION 'ready step requires exact admitted head content' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$;
CREATE FUNCTION fc_event_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected integer; first_id text;
BEGIN
 PERFORM 1 FROM free_course_operations WHERE id=NEW.operation_id FOR UPDATE;
 SELECT coalesce(max(seq),0)+1 INTO expected FROM free_course_events
 WHERE operation_id=NEW.operation_id;
 IF NEW.seq<>expected OR octet_length(NEW.payload::text)>4096 OR EXISTS(
   SELECT 1 FROM jsonb_object_keys(NEW.payload) k WHERE k NOT IN
     ('scene_id','scene_version_id','state','reason_code','questions')
 ) THEN
   RAISE EXCEPTION 'invalid bounded contiguous event' USING ERRCODE='23514';
 END IF;
 IF NEW.event_type IN ('scene_ready','first_scene_ready') THEN
   IF NOT EXISTS(
     SELECT 1 FROM free_course_versions cv JOIN free_course_steps st
       ON st.user_id=NEW.user_id AND st.course_id=NEW.course_id
       AND st.operation_id=NEW.operation_id AND st.state='ready'
     WHERE cv.id=NEW.course_version_id AND cv.user_id=NEW.user_id
       AND cv.course_id=NEW.course_id AND st.scene_id::text=NEW.payload->>'scene_id'
       AND st.scene_version_id::text=NEW.payload->>'scene_version_id'
       AND cv.manifest_json->'scenes' @> jsonb_build_array(jsonb_build_object(
         'scene_id',st.scene_id::text,'scene_version_id',st.scene_version_id::text))
   ) THEN RAISE EXCEPTION 'ready event binding invalid' USING ERRCODE='23514'; END IF;
 END IF;
 IF NEW.event_type='first_scene_ready' THEN
   SELECT manifest_json->'scenes'->0->>'scene_id' INTO first_id FROM free_course_versions
   WHERE id=NEW.course_version_id;
   IF first_id IS DISTINCT FROM NEW.payload->>'scene_id' THEN
     RAISE EXCEPTION 'first scene is the plan first scene' USING ERRCODE='23514';
   END IF;
 END IF;
 RETURN NEW;
END; $$;
"""


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_fc_presentation_identity",
        "free_course_scene_presentations",
        ["user_id", "course_id", "id"],
    )
    for ddl in TABLES + INDEXES:
        op.execute(ddl)
    # asyncpg requires one command per prepared statement.
    for function in GUARDS.strip().split("CREATE FUNCTION ")[1:]:
        op.execute("CREATE FUNCTION " + function.strip())
    op.execute(
        "CREATE TRIGGER fc_step_protect BEFORE INSERT OR UPDATE OR DELETE ON "
        "free_course_steps FOR EACH ROW EXECUTE FUNCTION fc_step_guard()"
    )
    op.execute(
        "CREATE TRIGGER fc_event_insert BEFORE INSERT ON free_course_events "
        "FOR EACH ROW EXECUTE FUNCTION fc_event_guard()"
    )
    op.execute(
        "CREATE TRIGGER fc_event_immutable BEFORE UPDATE OR DELETE ON free_course_events "
        "FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM free_course_steps) OR EXISTS(SELECT 1 FROM free_course_events) THEN
        RAISE EXCEPTION 'free course data prevents downgrade';
      END IF;
    END $$""")
    op.drop_table("free_course_events")
    op.drop_table("free_course_steps")
    op.execute("DROP FUNCTION fc_event_guard()")
    op.execute("DROP FUNCTION fc_step_guard()")
    op.drop_constraint(
        "uq_fc_presentation_identity", "free_course_scene_presentations", type_="unique"
    )
