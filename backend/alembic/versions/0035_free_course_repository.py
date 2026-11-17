"""Durable snapshot fences/receipts and corrected complete graph identifiers."""

from alembic import op

revision = "0035_free_course_repository"
down_revision = "0034_free_course_snapshots"
branch_labels = None
depends_on = None

NEW_NODE_CHECK = (
    "(graph_version = 'mvp-0.2.0' AND node_id IN ('array', 'c-pointer', "
    "'circular-queue', 'linked-list-concept', 'linked-list-deletion', "
    "'linked-list-insertion', 'linked-list-traversal', 'queue', 'single-linked-list', "
    "'stack')) OR (graph_version = 'phase-1.1.0' AND node_id IN ('array', "
    "'array-stack', 'balanced-binary-search-tree', 'binary-heap', "
    "'binary-search-tree', 'binary-tree', 'binary-tree-traversal', "
    "'breadth-first-search', 'bubble-sort', 'c-pointer', 'circular-linked-list', "
    "'circular-queue', 'depth-first-search', 'doubly-linked-list', "
    "'graph-representation', 'heap-sort', 'insertion-sort', 'linked-list-concept', "
    "'linked-list-deletion', 'linked-list-insertion', 'linked-list-traversal', "
    "'linked-stack', 'merge-sort', 'queue', 'quick-sort', 'selection-sort', "
    "'single-linked-list', 'sorting-comparison', 'stack', 'tree-concept'))"
)
OLD_NODE_CHECK = (
    "(graph_version = 'mvp-0.2.0' AND node_id IN     ('array', 'c-pointer', "
    "'circular- queue', 'linked-list-concept', 'linked-list-deletion', "
    "'linked-list- insertion', 'linked-list-traversal', 'queue', "
    "'single-linked-list',     'stack')) OR (graph_version = 'phase-1.1.0' AND "
    "node_id IN ('array', 'array-stack',     'balanced-binary-search-tree', "
    "'binary-heap', 'binary-search-tree', 'binary- tree', "
    "'binary-tree-traversal', 'breadth-first-search', 'bubble-sort', 'c-pointer', "
    "'circular-linked-list', 'circular-queue', 'depth-first-search', "
    "'doubly-linked-list',     'graph-representation', 'heap-sort', "
    "'insertion-sort', 'linked-list-concept',     'linked-list-deletion', "
    "'linked-list-insertion', 'linked-list-traversal', 'linked-stack', "
    "'merge-sort', 'queue', 'quick-sort', 'selection-sort', 'single-linked-list', "
    "'sorting-comparison', 'stack', 'tree- concept'))"
)

TABLE_DDL = [
    """CREATE TABLE free_course_operations (
	course_id UUID NOT NULL,
	request_id UUID NOT NULL,
	kind VARCHAR(32) NOT NULL,
	base_head_version INTEGER,
	state VARCHAR(32) DEFAULT 'queued' NOT NULL,
	deadline_at TIMESTAMP WITH TIME ZONE DEFAULT now() + interval '600 seconds' NOT NULL,
	config_snapshot JSONB NOT NULL,
	policy_snapshot JSONB NOT NULL,
	lease_epoch INTEGER DEFAULT '0' NOT NULL,
	lease_token UUID,
	lease_expires_at TIMESTAMP WITH TIME ZONE,
	cancel_requested_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_fc_operation_identity UNIQUE (user_id, course_id, id),
        CONSTRAINT fk_fc_operation_request FOREIGN KEY(user_id, course_id, request_id)
REFERENCES free_course_requests (user_id, course_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY
DEFERRED,
        CONSTRAINT ck_fc_operation_kind CHECK (kind IN
('create','clarify','resume','adjust_outline','revise_scene','tutor_turn')),
        CONSTRAINT ck_fc_operation_state CHECK (state IN
('queued','running','cancel_requested','succeeded','partially_succeeded','awaiting_clarification','failed','cancelled','timed_out')),
        CONSTRAINT ck_fc_operation_versions CHECK (lease_epoch >= 0 AND (base_head_version IS
NULL OR base_head_version>0))
)""",
    """CREATE UNIQUE INDEX uq_fc_operation_course_active ON free_course_operations (course_id)
WHERE state IN ('queued','running','cancel_requested')""",
    """CREATE UNIQUE INDEX uq_fc_operation_owner_active ON free_course_operations (user_id)
WHERE state IN ('queued','running','cancel_requested')""",
    """CREATE TABLE free_course_receipts (
	user_id UUID NOT NULL,
	route VARCHAR(256) NOT NULL,
	idempotency_key VARCHAR(128) NOT NULL,
	course_id UUID NOT NULL,
	request_digest VARCHAR(64) NOT NULL,
	status_code INTEGER NOT NULL,
	response_json JSONB NOT NULL,
	PRIMARY KEY (user_id, route, idempotency_key),
        CONSTRAINT fk_fc_receipt_course FOREIGN KEY(user_id, course_id) REFERENCES free_courses
(user_id, id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
	CONSTRAINT ck_fc_receipt_digest CHECK (request_digest ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_fc_receipt_status CHECK (status_code BETWEEN 200 AND 299)
)""",
]


OLD_NODE_GUARD = """
CREATE OR REPLACE FUNCTION fc_node_link_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE manifest jsonb; version_xid text;
BEGIN
 SELECT manifest_json,xmin::text INTO manifest,version_xid FROM free_course_versions
 WHERE id=NEW.course_version_id AND user_id=NEW.user_id AND course_id=NEW.course_id;
 IF manifest IS NULL OR version_xid IS DISTINCT FROM
   mod(pg_current_xact_id()::text::numeric,4294967296)::text THEN
   RAISE EXCEPTION 'links must be written with new manifest' USING ERRCODE='23514';
 END IF;
 IF NEW.scene_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(manifest->'scenes')
   WHERE value->>'scene_id'=NEW.scene_id::text) THEN
   RAISE EXCEPTION 'linked scene absent from manifest' USING ERRCODE='23514';
 END IF;
 IF jsonb_typeof(NEW.evidence_refs) IS DISTINCT FROM 'array' THEN
   RAISE EXCEPTION 'invalid link evidence' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$"""
NEW_NODE_GUARD = """
CREATE OR REPLACE FUNCTION fc_node_link_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE manifest jsonb; version_xid text;
BEGIN
 SELECT manifest_json,creation_txid::text INTO manifest,version_xid FROM free_course_versions
 WHERE id=NEW.course_version_id AND user_id=NEW.user_id AND course_id=NEW.course_id;
 IF manifest IS NULL OR version_xid IS DISTINCT FROM
   pg_current_xact_id()::text THEN
   RAISE EXCEPTION 'links must be written with new manifest' USING ERRCODE='23514';
 END IF;
 IF NEW.scene_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(manifest->'scenes')
   WHERE value->>'scene_id'=NEW.scene_id::text) THEN
   RAISE EXCEPTION 'linked scene absent from manifest' USING ERRCODE='23514';
 END IF;
 IF jsonb_typeof(NEW.evidence_refs) IS DISTINCT FROM 'array' THEN
   RAISE EXCEPTION 'invalid link evidence' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END; $$"""


def upgrade() -> None:
    op.drop_constraint("ck_fc_link_known_node", "free_course_node_links", type_="check")
    op.create_check_constraint("ck_fc_link_known_node", "free_course_node_links", NEW_NODE_CHECK)
    for ddl in TABLE_DDL:
        op.execute(ddl)
    op.execute("ALTER TABLE free_course_versions ADD COLUMN creation_txid bigint")
    op.execute(
        "ALTER TABLE free_course_versions ALTER COLUMN creation_txid "
        "SET DEFAULT pg_current_xact_id()::text::bigint"
    )
    op.execute(NEW_NODE_GUARD)
    for table in ["free_course_plans", "free_course_scene_versions"]:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN origin_operation_id uuid, "
            "ADD COLUMN origin_lease_epoch integer"
        )
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_operation "
            "FOREIGN KEY(user_id,course_id,origin_operation_id) "
            "REFERENCES free_course_operations(user_id,course_id,id) "
            "DEFERRABLE INITIALLY DEFERRED"
        )
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_origin "
            "CHECK ((origin_operation_id IS NULL) = (origin_lease_epoch IS NULL))"
        )
    op.execute(
        "CREATE TRIGGER fc_receipt_immutable BEFORE UPDATE OR DELETE ON "
        "free_course_receipts FOR EACH ROW EXECUTE FUNCTION fc_immutable()"
    )
    op.execute("""CREATE FUNCTION fc_operation_protect() RETURNS trigger LANGUAGE plpgsql AS $$
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
    END; $$""")
    op.execute(
        "CREATE TRIGGER fc_operation_protect BEFORE UPDATE OR DELETE ON "
        "free_course_operations FOR EACH ROW EXECUTE FUNCTION fc_operation_protect()"
    )


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM free_course_operations)
      OR EXISTS(SELECT 1 FROM free_course_receipts)
      OR EXISTS(SELECT 1 FROM free_course_node_links) THEN
        RAISE EXCEPTION 'free course data prevents downgrade';
      END IF;
    END $$""")
    op.execute(OLD_NODE_GUARD)
    op.execute("ALTER TABLE free_course_versions DROP COLUMN creation_txid")
    for table in ["free_course_plans", "free_course_scene_versions"]:
        op.execute(
            f"ALTER TABLE {table} DROP COLUMN origin_operation_id, DROP COLUMN origin_lease_epoch"
        )
    op.drop_table("free_course_receipts")
    op.drop_table("free_course_operations")
    op.execute("DROP FUNCTION fc_operation_protect()")
    op.drop_constraint("ck_fc_link_known_node", "free_course_node_links", type_="check")
    op.create_check_constraint("ck_fc_link_known_node", "free_course_node_links", OLD_NODE_CHECK)
