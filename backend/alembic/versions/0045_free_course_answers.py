"""Append-only generated practice audit and exact owner bindings."""

from alembic import op

revision = "0045_free_course_answers"
down_revision = "0044_free_course_quality"
branch_labels = None
depends_on = None
TABLES = [
    """
CREATE TABLE free_course_exercise_versions (
	course_id UUID NOT NULL,
	scene_version_id UUID NOT NULL,
	exercise_id UUID NOT NULL,
	anchor_id VARCHAR(128) NOT NULL,
	content_json JSONB NOT NULL,
	content_digest VARCHAR(64) NOT NULL,
	context_digest VARCHAR(64) NOT NULL,
	assessment_digest VARCHAR(64) NOT NULL,
	question_stem_digest VARCHAR(64) NOT NULL,
	rule_version VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_exercise_scene FOREIGN KEY(user_id, course_id, scene_version_id)
REFERENCES free_course_scene_versions (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
	CONSTRAINT uq_fc_exercise_identity UNIQUE (user_id, course_id, id),
	CONSTRAINT uq_fc_exercise_anchor UNIQUE (user_id, course_id, scene_version_id, anchor_id)
)

""",
    """
CREATE TABLE free_course_attempts_answers (
	course_id UUID NOT NULL,
	course_version_id UUID NOT NULL,
	exercise_version_id UUID NOT NULL,
	binding_json JSONB NOT NULL,
	answers_json JSONB NOT NULL,
	completeness VARCHAR(16) NOT NULL,
	feedback_json JSONB NOT NULL,
	qualification_json JSONB NOT NULL,
	request_digest VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_answers_manifest FOREIGN KEY(user_id, course_id, course_version_id)
REFERENCES free_course_versions (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY
DEFERRED,
        CONSTRAINT fk_fc_answers_exercise FOREIGN KEY(user_id, course_id, exercise_version_id)
REFERENCES free_course_exercise_versions (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT uq_fc_answers_identity UNIQUE (user_id, course_id, id),
	CONSTRAINT uq_fc_answers_owner UNIQUE (user_id, id),
	CONSTRAINT ck_fc_answers_completeness CHECK (completeness IN ('incomplete','complete'))
)

""",
    """
CREATE TABLE free_course_assessment_exposures (
	course_id UUID NOT NULL,
	exercise_version_id UUID NOT NULL,
	assessment_digest VARCHAR(64) NOT NULL,
	question_stem_digest VARCHAR(64) NOT NULL,
	kind VARCHAR(32) NOT NULL,
	binding_json JSONB NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_exposure_exercise FOREIGN KEY(user_id, course_id, exercise_version_id)
REFERENCES free_course_exercise_versions (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
	CONSTRAINT ck_fc_exposure_kind CHECK (kind IN ('help','solution','first_complete'))
)

""",
]
NAMES = [
    "free_course_exercise_versions",
    "free_course_attempts_answers",
    "free_course_assessment_exposures",
]


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
            "RAISE EXCEPTION 'practice audit prevents downgrade'; END IF; END $$"
        )
        op.drop_table(name)
