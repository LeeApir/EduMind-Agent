"""Allow the already-approved tutor ready step/event, preserving existing scene checks."""

from alembic import op

revision = "0048_free_course_tutor_events"
down_revision = "0047_free_course_tutor"
branch_labels = None
depends_on = None
OLD_EVENTS = (
    "event_type IN ('queued','started','clarification_required','outline_ready',"
    "'scene_started','scene_ready','first_scene_ready','progress','cancel_requested','error','done')"
)
OLD_READY = (
    "(state='ready' AND reason_code IS NULL AND ((scene_id IS NULL AND step_key='plan' "
    "AND scene_version_id IS NULL AND presentation_id IS NULL) OR (scene_id IS NOT NULL "
    "AND scene_version_id IS NOT NULL AND presentation_id IS NOT NULL))) OR state<>'ready'"
)


OLD_STEP_GUARD = """

CREATE OR REPLACE FUNCTION fc_step_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
   IF NOT EXISTS(SELECT 1 FROM users WHERE id=OLD.user_id) THEN RETURN OLD; END IF;
   RAISE EXCEPTION 'step audit cannot be deleted' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' AND
(to_jsonb(NEW)-ARRAY['state','reason_code','scene_version_id',
'presentation_id','next_attempt_at','retry_purpose'])
   IS DISTINCT FROM
(to_jsonb(OLD)-ARRAY['state','reason_code','scene_version_id',
'presentation_id','next_attempt_at','retry_purpose'])
THEN
   RAISE EXCEPTION 'immutable step binding' USING ERRCODE='23514';
 END IF;
 IF NEW.state='ready' AND EXISTS(
 SELECT 1 FROM free_course_revision_stages st
 JOIN free_course_revisions re ON re.operation_id=st.operation_id
 JOIN free_course_scene_versions nv ON nv.id=st.scene_version_id
 JOIN free_course_scene_versions ov ON ov.id=st.source_version_id
 JOIN free_course_steps os ON os.scene_version_id=ov.id AND os.state='ready'
 JOIN free_course_versions base ON base.course_id=re.course_id AND base.version=re.base_head
 JOIN free_course_plans np ON np.id=nv.plan_id
 JOIN free_course_plans op ON op.id=ov.plan_id
 JOIN free_courses c ON c.id=NEW.course_id AND c.user_id=NEW.user_id
 JOIN free_course_versions head ON head.id=c.head_version_id
 WHERE st.user_id=NEW.user_id AND st.course_id=NEW.course_id
 AND st.operation_id=NEW.operation_id AND st.scene_id=NEW.scene_id
 AND st.scene_version_id=NEW.scene_version_id AND st.presentation_id=NEW.presentation_id
 AND os.presentation_id=st.presentation_id AND nv.origin_operation_id=NEW.operation_id
 AND nv.user_id=NEW.user_id AND ov.user_id=NEW.user_id
 AND nv.course_id=NEW.course_id AND ov.course_id=NEW.course_id
 AND nv.scene_id=ov.scene_id AND nv.plan_id=NEW.plan_id
 AND nv.content_json=ov.content_json AND nv.actions_json=ov.actions_json
 AND np.plan_json->'candidate'=op.plan_json->'candidate'
 AND base.manifest_json->'scenes' @> jsonb_build_array(jsonb_build_object(
 'scene_id',ov.scene_id::text,'scene_version_id',ov.id::text))
 AND head.manifest_json->'scenes' @> jsonb_build_array(jsonb_build_object(
 'scene_id',nv.scene_id::text,'scene_version_id',nv.id::text))
 ) THEN RETURN NEW; END IF;
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
STEP_GUARD = """

CREATE OR REPLACE FUNCTION fc_step_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
   IF NOT EXISTS(SELECT 1 FROM users WHERE id=OLD.user_id) THEN RETURN OLD; END IF;
   RAISE EXCEPTION 'step audit cannot be deleted' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' AND
(to_jsonb(NEW)-ARRAY['state','reason_code','scene_version_id',
'presentation_id','next_attempt_at','retry_purpose'])
   IS DISTINCT FROM
(to_jsonb(OLD)-ARRAY['state','reason_code','scene_version_id',
'presentation_id','next_attempt_at','retry_purpose'])
THEN
   RAISE EXCEPTION 'immutable step binding' USING ERRCODE='23514';
 END IF;
 IF NEW.state='ready' AND NEW.step_key='tutor' THEN
   IF NEW.scene_id IS NOT NULL OR NEW.scene_version_id IS NOT NULL
      OR NEW.presentation_id IS NOT NULL OR NOT EXISTS(
     SELECT 1 FROM free_course_tutor_turns t
     JOIN free_course_tutor_replies r ON r.turn_id=t.id AND r.user_id=t.user_id
       AND r.course_id=t.course_id
     JOIN free_course_operations o ON o.id=t.operation_id AND o.user_id=t.user_id
       AND o.course_id=t.course_id AND o.kind='tutor_turn'
     JOIN free_course_attempts a ON a.operation_id=o.id AND a.step_id=NEW.id
       AND a.user_id=t.user_id AND a.course_id=t.course_id AND a.purpose='primary'
     JOIN free_course_dispatches d ON d.attempt_id=a.id
     JOIN free_course_settlements se ON se.attempt_id=a.id
       AND se.evidence='complete_response'
     JOIN free_courses c ON c.id=t.course_id AND c.user_id=t.user_id
     WHERE t.operation_id=NEW.operation_id AND t.user_id=NEW.user_id
       AND t.course_id=NEW.course_id AND c.head_version_id=t.course_version_id
       AND o.state='running' AND o.cancel_requested_at IS NULL
       AND o.lease_epoch=a.lease_epoch AND o.deadline_at>clock_timestamp()
       AND o.lease_expires_at>clock_timestamp()
       AND a.input_snapshot->>'turn_id'=t.id::text
       AND a.input_snapshot->>'context_digest'=t.context_digest
   ) THEN RAISE EXCEPTION 'ready tutor requires exact dispatched settled reply'
     USING ERRCODE='23514'; END IF;
   RETURN NEW;
 END IF;
 IF NEW.state='ready' AND EXISTS(
 SELECT 1 FROM free_course_revision_stages st
 JOIN free_course_revisions re ON re.operation_id=st.operation_id
 JOIN free_course_scene_versions nv ON nv.id=st.scene_version_id
 JOIN free_course_scene_versions ov ON ov.id=st.source_version_id
 JOIN free_course_steps os ON os.scene_version_id=ov.id AND os.state='ready'
 JOIN free_course_versions base ON base.course_id=re.course_id AND base.version=re.base_head
 JOIN free_course_plans np ON np.id=nv.plan_id
 JOIN free_course_plans op ON op.id=ov.plan_id
 JOIN free_courses c ON c.id=NEW.course_id AND c.user_id=NEW.user_id
 JOIN free_course_versions head ON head.id=c.head_version_id
 WHERE st.user_id=NEW.user_id AND st.course_id=NEW.course_id
 AND st.operation_id=NEW.operation_id AND st.scene_id=NEW.scene_id
 AND st.scene_version_id=NEW.scene_version_id AND st.presentation_id=NEW.presentation_id
 AND os.presentation_id=st.presentation_id AND nv.origin_operation_id=NEW.operation_id
 AND nv.user_id=NEW.user_id AND ov.user_id=NEW.user_id
 AND nv.course_id=NEW.course_id AND ov.course_id=NEW.course_id
 AND nv.scene_id=ov.scene_id AND nv.plan_id=NEW.plan_id
 AND nv.content_json=ov.content_json AND nv.actions_json=ov.actions_json
 AND np.plan_json->'candidate'=op.plan_json->'candidate'
 AND base.manifest_json->'scenes' @> jsonb_build_array(jsonb_build_object(
 'scene_id',ov.scene_id::text,'scene_version_id',ov.id::text))
 AND head.manifest_json->'scenes' @> jsonb_build_array(jsonb_build_object(
 'scene_id',nv.scene_id::text,'scene_version_id',nv.id::text))
 ) THEN RETURN NEW; END IF;
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


OLD_EVENT_GUARD = """
CREATE OR REPLACE FUNCTION fc_event_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
EVENT_GUARD = """
CREATE OR REPLACE FUNCTION fc_event_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected integer; first_id text;
BEGIN
 PERFORM 1 FROM free_course_operations WHERE id=NEW.operation_id FOR UPDATE;
 SELECT coalesce(max(seq),0)+1 INTO expected FROM free_course_events
 WHERE operation_id=NEW.operation_id;
 IF NEW.seq<>expected OR octet_length(NEW.payload::text)>4096 OR EXISTS(
   SELECT 1 FROM jsonb_object_keys(NEW.payload) k WHERE k NOT IN
     ('scene_id','scene_version_id','state','reason_code','questions')
     AND NOT (NEW.event_type='tutor_ready' AND k='turn_id')
 ) THEN
   RAISE EXCEPTION 'invalid bounded contiguous event' USING ERRCODE='23514';
 END IF;
 IF NEW.event_type='tutor_ready' THEN
   IF (SELECT count(*) FROM jsonb_object_keys(NEW.payload))<>1 OR NOT EXISTS(
     SELECT 1 FROM free_course_tutor_turns t
     JOIN free_course_tutor_replies r ON r.turn_id=t.id AND r.user_id=t.user_id
       AND r.course_id=t.course_id
     JOIN free_course_steps st ON st.operation_id=t.operation_id AND st.user_id=t.user_id
       AND st.course_id=t.course_id AND st.step_key='tutor' AND st.state='ready'
     WHERE t.id::text=NEW.payload->>'turn_id' AND t.operation_id=NEW.operation_id
       AND t.user_id=NEW.user_id AND t.course_id=NEW.course_id
       AND t.course_version_id=NEW.course_version_id
   ) THEN RAISE EXCEPTION 'tutor ready event binding invalid' USING ERRCODE='23514'; END IF;
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
    op.execute(STEP_GUARD)
    op.execute(EVENT_GUARD)
    op.drop_constraint("ck_fc_event_type", "free_course_events", type_="check")
    op.create_check_constraint(
        "ck_fc_event_type", "free_course_events", OLD_EVENTS[:-1] + ",'tutor_ready')"
    )
    op.drop_constraint("ck_fc_step_ready", "free_course_steps", type_="check")
    op.create_check_constraint(
        "ck_fc_step_ready",
        "free_course_steps",
        OLD_READY.replace("step_key='plan'", "step_key IN ('plan','tutor')"),
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM free_course_events WHERE event_type='tutor_ready') "
        "OR EXISTS(SELECT 1 FROM free_course_steps WHERE step_key='tutor' AND state='ready') "
        "THEN RAISE EXCEPTION 'Tutor completion audit data exists'; END IF; END $$"
    )
    op.execute(OLD_STEP_GUARD)
    op.execute(OLD_EVENT_GUARD)
    op.drop_constraint("ck_fc_event_type", "free_course_events", type_="check")
    op.create_check_constraint("ck_fc_event_type", "free_course_events", OLD_EVENTS)
    op.drop_constraint("ck_fc_step_ready", "free_course_steps", type_="check")
    op.create_check_constraint("ck_fc_step_ready", "free_course_steps", OLD_READY)
