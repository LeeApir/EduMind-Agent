"""Exact-owner tutor context and append-only safe replies (ADR0026)."""

from alembic import op

revision = "0047_free_course_tutor"
down_revision = "0046_free_course_evidence"
branch_labels = None
depends_on = None
TABLES = [
    """
CREATE TABLE free_course_tutor_turns (
course_id UUID NOT NULL,
operation_id UUID NOT NULL,
course_version_id UUID NOT NULL,
scene_version_id UUID NOT NULL,
binding_json JSONB NOT NULL,
message TEXT NOT NULL,
context_json JSONB NOT NULL,
sources_json JSONB NOT NULL,
context_digest VARCHAR(64) NOT NULL,
id UUID NOT NULL,
user_id UUID NOT NULL,
created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
PRIMARY KEY (id),
CONSTRAINT fk_fc_tutor_operation FOREIGN KEY(user_id, course_id, operation_id) REFERENCES
free_course_operations (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
CONSTRAINT fk_fc_tutor_manifest FOREIGN KEY(user_id, course_id, course_version_id) REFERENCES
free_course_versions (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
CONSTRAINT fk_fc_tutor_scene FOREIGN KEY(user_id, course_id, scene_version_id) REFERENCES
free_course_scene_versions (user_id, course_id, id) DEFERRABLE INITIALLY DEFERRED,
CONSTRAINT uq_fc_tutor_identity UNIQUE (user_id, course_id, id),
CONSTRAINT uq_fc_tutor_operation UNIQUE (operation_id),
CONSTRAINT ck_fc_tutor_message CHECK (length(btrim(message)) BETWEEN 1 AND 2000),
CONSTRAINT ck_fc_tutor_digest CHECK (context_digest ~ '^[0-9a-f]{64}$')
)
""",
    """
CREATE TABLE free_course_tutor_replies (
course_id UUID NOT NULL,
turn_id UUID NOT NULL,
markdown TEXT NOT NULL,
anchor_refs JSONB NOT NULL,
reply_digest VARCHAR(64) NOT NULL,
id UUID NOT NULL,
user_id UUID NOT NULL,
created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
PRIMARY KEY (id),
CONSTRAINT fk_fc_tutor_reply_turn FOREIGN KEY(user_id, course_id, turn_id) REFERENCES
free_course_tutor_turns (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY
DEFERRED,
CONSTRAINT uq_fc_tutor_reply UNIQUE (turn_id),
CONSTRAINT ck_fc_tutor_reply_body CHECK (length(btrim(markdown)) BETWEEN 1 AND 6000),
CONSTRAINT ck_fc_tutor_reply_refs CHECK (jsonb_typeof(anchor_refs)='array' AND
jsonb_array_length(anchor_refs)<=32)
)
""",
]
NAMES = ["free_course_tutor_turns", "free_course_tutor_replies"]


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
            "RAISE EXCEPTION 'Tutor audit data exists'; END IF; END $$"
        )
    for name in reversed(NAMES):
        op.drop_table(name)
