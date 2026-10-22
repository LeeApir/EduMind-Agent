"""Private revision staging and provenance-bound unchanged scene copies."""

from alembic import op

revision = "0043_free_course_revision"
down_revision = "0042_free_course_recovery"
branch_labels = None
depends_on = None

TABLES = [
    """

CREATE TABLE free_course_revisions (
        course_id UUID NOT NULL,
        operation_id UUID NOT NULL,
        kind VARCHAR(32) NOT NULL,
        base_head INTEGER,
        instruction VARCHAR(4000) NOT NULL,
        impact_json JSONB NOT NULL,
        impact_digest VARCHAR(64) NOT NULL,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_fc_revision_operation FOREIGN KEY(user_id, course_id, operation_id)
REFERENCES free_course_operations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT uq_fc_revision_operation UNIQUE (operation_id),
        CONSTRAINT ck_fc_revision_kind CHECK (kind IN ('revise_scene','adjust_outline') AND
((base_head IS NOT NULL AND base_head>0) OR
(base_head IS NULL AND kind='adjust_outline')))
)

""",
    """

CREATE TABLE free_course_revision_plans (
        course_id UUID NOT NULL,
        operation_id UUID NOT NULL,
        plan_id UUID NOT NULL,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_fc_revision_plan_operation FOREIGN KEY(user_id, course_id, operation_id)
REFERENCES free_course_operations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT fk_fc_revision_plan_plan FOREIGN KEY(user_id, course_id, plan_id) REFERENCES
free_course_plans (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT uq_fc_revision_plan_operation UNIQUE (operation_id)
)

""",
    """

CREATE TABLE free_course_revision_stages (
        course_id UUID NOT NULL,
        operation_id UUID NOT NULL,
        scene_id UUID NOT NULL,
        scene_version_id UUID NOT NULL,
        presentation_id UUID NOT NULL,
        source_version_id UUID,
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_fc_revision_stage_operation FOREIGN KEY(user_id, course_id, operation_id)
REFERENCES free_course_operations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT fk_fc_revision_stage_scene FOREIGN KEY(user_id, course_id, scene_id)
REFERENCES free_course_scenes (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_fc_revision_stage_version FOREIGN KEY(user_id, course_id,
scene_version_id) REFERENCES free_course_scene_versions (user_id, course_id, id) DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT fk_fc_revision_stage_source FOREIGN KEY(user_id, course_id,
source_version_id) REFERENCES free_course_scene_versions (user_id, course_id, id) DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT fk_fc_revision_stage_presentation FOREIGN KEY(user_id, course_id,
presentation_id) REFERENCES free_course_scene_presentations (user_id, course_id, id) DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT uq_fc_revision_stage_scene UNIQUE (operation_id, scene_id)
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
OLD_GUARD = """

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
    for ddl in TABLES:
        op.execute(ddl)
    for name in (
        "free_course_revisions",
        "free_course_revision_plans",
        "free_course_revision_stages",
    ):
        op.execute(
            f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
        )
    op.execute(STEP_GUARD)


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM free_course_revisions) THEN
        RAISE EXCEPTION 'revision audit prevents downgrade'; END IF; END $$""")
    op.execute(OLD_GUARD)
    for table in (
        "free_course_revision_stages",
        "free_course_revision_plans",
        "free_course_revisions",
    ):
        op.drop_table(table)
