"""Append-only accurate feedback, maintenance decisions and visibility audit."""

from alembic import op

revision = "0044_free_course_quality"
down_revision = "0043_free_course_revision"
branch_labels = None
depends_on = None
TABLES = [
    """
CREATE TABLE free_course_feedback (
	course_id UUID NOT NULL,
	course_version_id UUID NOT NULL,
	scene_version_id UUID NOT NULL,
	location_json JSONB NOT NULL,
	description VARCHAR(2000) NOT NULL,
	source VARCHAR(32) NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_feedback_manifest FOREIGN KEY(user_id, course_id, course_version_id)
REFERENCES free_course_versions (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY
DEFERRED,
        CONSTRAINT fk_fc_feedback_scene FOREIGN KEY(user_id, course_id, scene_version_id)
REFERENCES free_course_scene_versions (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT uq_fc_feedback_identity UNIQUE (user_id, course_id, id)
)

""",
    """
CREATE TABLE free_course_quality_decisions (
	course_id UUID NOT NULL,
	course_version_id UUID NOT NULL,
	scene_version_id UUID NOT NULL,
	decision_key VARCHAR(128) NOT NULL,
	request_digest VARCHAR(64) NOT NULL,
	action VARCHAR(32) NOT NULL,
	authority VARCHAR(64) NOT NULL,
	rule_version VARCHAR(64) NOT NULL,
	evidence_json JSONB NOT NULL,
	impact_json JSONB NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_decision_manifest FOREIGN KEY(user_id, course_id, course_version_id)
REFERENCES free_course_versions (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY
DEFERRED,
        CONSTRAINT fk_fc_decision_scene FOREIGN KEY(user_id, course_id, scene_version_id)
REFERENCES free_course_scene_versions (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT uq_fc_decision_identity UNIQUE (user_id, course_id, id),
	CONSTRAINT uq_fc_decision_key UNIQUE (user_id, decision_key),
        CONSTRAINT ck_fc_decision_action CHECK (action IN
('confirm_defect','not_confirmed','decision_correction','restore'))
)

""",
    """
CREATE TABLE free_course_visibility_facts (
	course_id UUID NOT NULL,
	decision_id UUID NOT NULL,
	scene_version_id UUID NOT NULL,
	scope VARCHAR(16) NOT NULL,
	anchor_id VARCHAR(128),
	action VARCHAR(16) NOT NULL,
	reason_code VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_visibility_decision FOREIGN KEY(user_id, course_id, decision_id)
REFERENCES free_course_quality_decisions (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT fk_fc_visibility_scene FOREIGN KEY(user_id, course_id, scene_version_id)
REFERENCES free_course_scene_versions (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT ck_fc_visibility_action CHECK (action IN ('disable','restore') AND scope IN
('scene','exercise'))
)

""",
]
NAMES = ["free_course_feedback", "free_course_quality_decisions", "free_course_visibility_facts"]


def upgrade() -> None:
    for ddl in TABLES:
        op.execute(ddl)
    for name in NAMES:
        op.execute(
            f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
        )


def downgrade() -> None:
    for name in reversed(NAMES):
        op.execute(
            f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM {name}) THEN "
            "RAISE EXCEPTION 'quality audit prevents downgrade'; END IF; END $$"
        )
        op.drop_table(name)
