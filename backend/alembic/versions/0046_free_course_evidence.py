"""Append-only generated practice audit and exact owner bindings."""

import sqlalchemy as sa

from alembic import op

revision = "0046_free_course_evidence"
down_revision = "0045_free_course_answers"
branch_labels = None
depends_on = None
TABLES = [
    """
CREATE TABLE free_course_attestations (
	course_id UUID NOT NULL,
	exercise_version_id UUID NOT NULL,
	kind VARCHAR(32) NOT NULL,
	decision_key VARCHAR(128) NOT NULL,
	request_digest VARCHAR(64) NOT NULL,
	content_digest VARCHAR(64) NOT NULL,
	context_digest VARCHAR(64) NOT NULL,
	node_id VARCHAR(64),
	graph_version VARCHAR(64),
	authority VARCHAR(64) NOT NULL,
	rule_version VARCHAR(64) NOT NULL,
	evidence_json JSONB NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_attest_exercise FOREIGN KEY(user_id, course_id, exercise_version_id)
REFERENCES free_course_exercise_versions (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
	CONSTRAINT uq_fc_attest_identity UNIQUE (user_id, course_id, id),
	CONSTRAINT uq_fc_attest_key UNIQUE (user_id, decision_key),
	CONSTRAINT ck_fc_attest_kind CHECK (kind IN ('answer_attestation','mapping_attestation'))
)

""",
    """
CREATE TABLE free_course_attestation_revocations (
	course_id UUID NOT NULL,
	attestation_id UUID NOT NULL,
	reason_json JSONB NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_attest_revoke FOREIGN KEY(user_id, course_id, attestation_id)
REFERENCES free_course_attestations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
	CONSTRAINT uq_fc_attest_revoke UNIQUE (attestation_id)
)

""",
    """
CREATE TABLE free_course_evidence_admissions (
	course_id UUID NOT NULL,
	attempt_id UUID NOT NULL,
	evidence_id UUID NOT NULL,
	answer_attestation_id UUID NOT NULL,
	mapping_attestation_id UUID NOT NULL,
	node_id VARCHAR(64) NOT NULL,
	rule_version VARCHAR(64) NOT NULL,
	binding_digest VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_admission_attempt FOREIGN KEY(user_id, course_id, attempt_id)
REFERENCES free_course_attempts_answers (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT fk_fc_admission_answer FOREIGN KEY(user_id, course_id, answer_attestation_id)
REFERENCES free_course_attestations (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT fk_fc_admission_mapping FOREIGN KEY(user_id, course_id,
mapping_attestation_id) REFERENCES free_course_attestations (user_id, course_id, id) DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT fk_fc_admission_evidence FOREIGN KEY(user_id, evidence_id) REFERENCES
learning_evidence (user_id, id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT uq_fc_admission_identity UNIQUE (user_id, course_id, id),
	CONSTRAINT uq_fc_admission_cycle UNIQUE (user_id, attempt_id, evidence_id),
	CONSTRAINT uq_fc_admission_attempt UNIQUE (attempt_id),
	CONSTRAINT uq_fc_admission_evidence UNIQUE (evidence_id)
)

""",
    """
CREATE TABLE free_course_evidence_revocations (
	course_id UUID NOT NULL,
	admission_id UUID NOT NULL,
	correction_evidence_id UUID NOT NULL,
	reason_json JSONB NOT NULL,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT fk_fc_evidence_revoke FOREIGN KEY(user_id, course_id, admission_id)
REFERENCES free_course_evidence_admissions (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE
INITIALLY DEFERRED,
        CONSTRAINT fk_fc_revoke_correction FOREIGN KEY(user_id, correction_evidence_id)
REFERENCES learning_evidence (user_id, id) DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT uq_fc_evidence_revoke UNIQUE (admission_id),
	CONSTRAINT uq_fc_correction_evidence UNIQUE (correction_evidence_id)
)

""",
]
NAMES = [
    "free_course_attestations",
    "free_course_attestation_revocations",
    "free_course_evidence_admissions",
    "free_course_evidence_revocations",
]


def upgrade() -> None:
    op.add_column("learning_evidence", sa.Column("source_protocol", sa.String(40)))
    op.add_column("learning_evidence", sa.Column("free_course_attempt_id", sa.UUID()))
    for ddl in TABLES:
        op.execute(ddl)
    for name in NAMES:
        op.execute(
            f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
        )
    op.execute("ALTER TABLE learning_evidence DROP CONSTRAINT ck_learning_evidence_type")
    op.execute(
        "ALTER TABLE learning_evidence ADD CONSTRAINT ck_learning_evidence_type CHECK "
        "(evidence_type IN ('quiz_attempt','hint_used','reexplanation_requested',"
        "'resource_selected','explicit_feedback','evidence_correction'))"
    )
    op.execute("""ALTER TABLE learning_evidence ADD CONSTRAINT ck_learning_evidence_source CHECK (
      (source_protocol IS NULL AND free_course_attempt_id IS NULL AND
evidence_type<>'evidence_correction')
      OR (source_protocol IS NOT NULL AND source_protocol='free-course-v1' AND
free_course_attempt_id IS NOT NULL
          AND evidence_type='quiz_attempt' AND resource_id IS NULL AND learning_unit_id IS NULL
          AND scene_id IS NULL AND resource_version IS NULL)
      OR (source_protocol IS NOT NULL AND source_protocol='free-course-correction-v1' AND
free_course_attempt_id IS NULL
          AND evidence_type='evidence_correction' AND corrects_evidence_id IS NOT NULL))""")
    op.execute("""ALTER TABLE learning_evidence ADD CONSTRAINT fk_learning_free_attempt
      FOREIGN KEY(user_id,free_course_attempt_id) REFERENCES
free_course_attempts_answers(user_id,id)
      DEFERRABLE INITIALLY DEFERRED""")
    op.execute("""ALTER TABLE learning_evidence ADD CONSTRAINT fk_learning_free_admission
      FOREIGN KEY(user_id,free_course_attempt_id,id)
      REFERENCES free_course_evidence_admissions(user_id,attempt_id,evidence_id)
      DEFERRABLE INITIALLY DEFERRED""")
    for statement in GUARDS.strip().split("\nCREATE "):
        op.execute(statement if statement.startswith("CREATE ") else "CREATE " + statement)


GUARDS = """
CREATE FUNCTION fc_source_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' AND NOT EXISTS(SELECT 1 FROM users WHERE id=OLD.user_id) THEN RETURN OLD; END IF;
 IF OLD.source_protocol IS NOT NULL OR (TG_OP='UPDATE' AND NEW.source_protocol IS NOT NULL) THEN
   RAISE EXCEPTION 'source evidence is immutable' USING ERRCODE='23514';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
END; $$;
CREATE TRIGGER fc_source_evidence_immutable BEFORE UPDATE OR DELETE ON learning_evidence
 FOR EACH ROW EXECUTE FUNCTION fc_source_immutable();
CREATE FUNCTION fc_admission_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.user_id) THEN RETURN NEW; END IF;
 IF NOT EXISTS (
 SELECT 1 FROM free_course_attempts_answers at
 JOIN free_course_exercise_versions ex ON ex.id=at.exercise_version_id
 JOIN free_course_attestations aa ON aa.id=NEW.answer_attestation_id
 JOIN free_course_attestations ma ON ma.id=NEW.mapping_attestation_id
 JOIN learning_evidence ev ON ev.id=NEW.evidence_id
 WHERE at.id=NEW.attempt_id AND at.user_id=NEW.user_id AND at.course_id=NEW.course_id
 AND ex.user_id=NEW.user_id AND aa.user_id=NEW.user_id AND ma.user_id=NEW.user_id
 AND aa.exercise_version_id=ex.id AND ma.exercise_version_id=ex.id
 AND aa.kind='answer_attestation' AND ma.kind='mapping_attestation'
 AND aa.content_digest=ex.content_digest AND ma.content_digest=ex.content_digest
 AND aa.context_digest=ex.context_digest AND ma.context_digest=ex.context_digest
 AND aa.authority='Lee' AND ma.authority='Lee' AND ma.node_id=NEW.node_id
 AND aa.created_at<=at.created_at AND ma.created_at<=at.created_at
 AND at.completeness='complete' AND at.qualification_json->>'first_complete'='true'
 AND ev.user_id=NEW.user_id AND ev.source_protocol='free-course-v1'
 AND ev.free_course_attempt_id=at.id AND ev.knowledge_node_id=NEW.node_id
 AND NOT EXISTS(SELECT 1 FROM free_course_attestation_revocations ar
   WHERE ar.attestation_id IN (aa.id,ma.id))
 ) THEN RAISE EXCEPTION 'admission requires closed exact qualification' USING ERRCODE='23514';
END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER fc_admission_qualified AFTER INSERT ON free_course_evidence_admissions
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fc_admission_guard();
CREATE FUNCTION fc_correction_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.source_protocol='free-course-correction-v1' AND EXISTS(SELECT 1 FROM users WHERE
id=NEW.user_id)
 AND NOT EXISTS(SELECT 1 FROM free_course_evidence_revocations rv
 JOIN free_course_evidence_admissions ad ON ad.id=rv.admission_id
 WHERE rv.user_id=NEW.user_id AND rv.correction_evidence_id=NEW.id
 AND ad.evidence_id=NEW.corrects_evidence_id AND ad.node_id=NEW.knowledge_node_id) THEN
 RAISE EXCEPTION 'correction requires exact revocation' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER fc_correction_closed AFTER INSERT ON learning_evidence
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fc_correction_guard();
"""


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM learning_evidence WHERE source_protocol IS
NOT NULL)
      OR EXISTS(SELECT 1 FROM free_course_attestations) THEN
      RAISE EXCEPTION 'source evidence audit prevents downgrade'; END IF; END $$""")
    op.execute("DROP TRIGGER fc_correction_closed ON learning_evidence")
    op.execute("DROP FUNCTION fc_correction_guard()")
    op.execute("DROP TRIGGER fc_admission_qualified ON free_course_evidence_admissions")
    op.execute("DROP FUNCTION fc_admission_guard()")
    op.execute("DROP TRIGGER fc_source_evidence_immutable ON learning_evidence")
    op.execute("DROP FUNCTION fc_source_immutable()")
    for name in (
        "fk_learning_free_admission",
        "fk_learning_free_attempt",
        "ck_learning_evidence_source",
    ):
        op.drop_constraint(name, "learning_evidence")
    for name in reversed(NAMES):
        op.drop_table(name)
    op.execute("ALTER TABLE learning_evidence DROP CONSTRAINT ck_learning_evidence_type")
    op.execute(
        "ALTER TABLE learning_evidence ADD CONSTRAINT ck_learning_evidence_type CHECK "
        "(evidence_type IN ('quiz_attempt','hint_used','reexplanation_requested',"
        "'resource_selected','explicit_feedback'))"
    )
    op.drop_column("learning_evidence", "free_course_attempt_id")
    op.drop_column("learning_evidence", "source_protocol")
